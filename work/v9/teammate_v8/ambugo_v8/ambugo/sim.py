"""Mesoscopic spatial-queue network simulator (1 s step).

Model (declared, deliberately simple, verified in tests/):
* Each directed link is a FIFO.  A vehicle entering at t becomes 'ready' at the
  stop line at t + L/v_ff (x speed multiplier during incidents); afterwards it
  queues.  Multi-lane approaches expose `lanes` heads so one blocked turn does
  not block the other lane.
* Finite storage in PCU: a vehicle may only enter a link whose PCU occupancy plus
  its own PCU fits within floor((L-5) * lanes * 0.16)  -> spillback & gridlock
  emerge endogenously.
* Signals: protected one-approach stages (green, 3 s amber, 2 s all-red) plus an
  exclusive pedestrian stage (7 walk, 16 clearance, 2 all-red).  Discharge at the
  approach saturation flow (PCU/s) during green after 2 s start-up loss and during
  amber -> effective green = g + 1 s.
* Boundary demand waits in an unbounded external queue and is admitted at the
  entry-link saturation flow when storage allows.  Time in the external queue
  counts as delay.
* Ambulance: obeys the executed signal, no speed privilege, enters at the
  dispatch time 20 m downstream of the origin link start.  Optional yielding:
  when it reaches a queue each vehicle ahead independently pulls aside with
  probability rho * w_class (motorcycles most, buses least).
* Sensors: per approach link count camera every 5 s, bounded integer noise
  {-2..2}, two-state Markov dropout and one correlated outage cluster.
"""
from collections import deque
from .network import CLASSES, MIN_GREEN
from .rng import stream

SENSOR_PERIOD = 5
NOISE = (-2, -1, 0, 0, 0, 1, 2)
P_AM, P_MA = 0.015, 0.25


class Junction:
    __slots__ = ("id", "stages", "idx", "elapsed", "dur", "arms", "stage_of_green", "last_green_end",
                 "last_green_start", "max_red", "red_over", "last_ped", "max_ped_wait", "served_green",
                 "override_next", "lost", "comp")

    def __init__(self, jid, plan, arms):
        self.id, self.stages, self.arms = jid, plan["stages"], arms
        self.stage_of_green = {a: i for i, (k, a, _) in enumerate(self.stages) if k == "G"}
        rem = plan["offset"]
        self.idx = 0
        while rem >= self.stages[self.idx][2]:
            rem -= self.stages[self.idx][2]
            self.idx += 1
        self.elapsed, self.dur = rem, self.stages[self.idx][2]
        self.last_green_end = {a: 0 for a in arms}
        self.last_green_start = {a: 0 for a in arms}
        self.max_red = {a: 0 for a in arms}
        self.red_over = 0
        self.last_ped = 0
        self.max_ped_wait = 0
        self.served_green = 0
        self.override_next = None
        self.lost = {a: 0 for a in arms}
        self.comp = {a: 0 for a in arms}

    @property
    def kind(self):
        return self.stages[self.idx][0]

    @property
    def arm(self):
        return self.stages[self.idx][1]

    def base(self, i=None):
        return self.stages[self.idx if i is None else i][2]


class Simulator:
    def __init__(self, design, scenario, policy, rho_yield=0.0, perfect_info=False, record=True,
                 audit=False, demand_scale=1.0):
        self.d, self.net, self.sc, self.policy = design, design.net, scenario, policy
        self.rho = rho_yield
        self.perfect = perfect_info
        self.audit = audit
        net = self.net
        E = len(net.edges)
        self.dq = [deque() for _ in range(E)]
        self.occ = [0.0] * E
        self.credit = [0.0] * E
        self.disch = [0] * E                       # stop-line discharge counters (exact detector)
        self.junc = {j: Junction(j, design.plans[j], net.arms[j]) for j in net.junctions}
        self.T = scenario["horizon"]
        # vehicles
        vs = scenario["vehicles"]
        self.route = [v["route"] for v in vs]
        self.pcu = [v["pcu"] for v in vs]
        self.occp = [v["occ"] for v in vs]
        self.trel = [v["t"] for v in vs]
        self.ycls = [CLASSES[v["cls"]]["yield_w"] for v in vs]
        n = len(vs)
        self.pos = [0] * n
        self.ready = [0.0] * n
        self.done = [None] * n
        # ambulance appended as last vehicle
        a = scenario["amb"]
        self.amb = n
        self.amb_route = list(self.policy.initial_amb_route(self, a))
        self.route.append(self.amb_route)
        self.pcu.append(a["pcu"]); self.occp.append(a["occ"]); self.trel.append(a["dispatch"])
        self.ycls.append(0.0); self.pos.append(0); self.ready.append(0.0); self.done.append(None)
        self.amb_dispatch = a["dispatch"]
        self.amb_in = False
        self.amb_arrival = None
        self.amb_cross = {}
        self.amb_yield_done = set()
        self.amb_entry_snapshot = None
        self.amb_entry_disch = 0
        self.amb_link_enter_t = None
        # external origin queues
        self.ext = {o: deque() for o in net.boundaries}
        self.ext_credit = {o: 0.0 for o in net.boundaries}
        # incidents
        self.inc = scenario["incidents"]
        # sensors
        self.approaches = [i for i, e in enumerate(net.edges) if not e["is_exit"]]
        rs = stream(design.seed, "sensor", scenario["rep"])
        self.rs = rs
        self.sens_up = {e: True for e in self.approaches}
        self.est = {e: 0.0 for e in self.approaches}
        self.est_age = {e: 1e9 for e in self.approaches}
        self.outage = None
        if rs.random() < 0.5:
            j0 = rs.choice(net.junctions)
            near = [j for j in net.junctions
                    if abs(net.nodes[j]["x"] - net.nodes[j0]["x"]) + abs(net.nodes[j]["y"] - net.nodes[j0]["y"]) < 800]
            st = a["dispatch"] + rs.randint(-240, 60)
            self.outage = (set(e for j in near for e in net.arms[j]), st, st + rs.randint(180, 420))
        self.ryield = stream(design.seed, "yield", scenario["rep"])
        self.record = record
        self.N = [0] * self.T
        self.P = [0] * self.T
        self.completions = [0] * (self.T + 4000)
        self.comp_persons = [0] * (self.T + 4000)
        self.released = 0
        self.released_persons = 0
        self.violations = []
        self.max_wait = 0.0
        self.wait_sum = 0.0
        self.wait_n = 0
        self.n_wait_over = 0
        self.moves_last = 0
        self.gridlock_t = None
        self.policy.attach(self)

    # ------------------------------------------------------------ helpers
    def cap(self, e, t):
        s = self.net.edges[e]["s"]
        for inc in self.inc:
            if inc["edge"] == e and inc["start"] <= t < inc["end"]:
                s *= inc["cap_mult"]
        return s

    def tt(self, e, t):
        tt = self.net.edges[e]["tt"]
        for inc in self.inc:
            if inc["edge"] == e and inc["start"] <= t < inc["end"]:
                tt /= inc["speed_mult"]
        return tt

    def enter(self, vid, e, t, offset_m=0.0):
        self.dq[e].append(vid)
        self.occ[e] += self.pcu[vid]
        edge = self.net.edges[e]
        self.ready[vid] = t + self.tt(e, t) * (edge["L"] - offset_m) / edge["L"]
        if edge["is_exit"]:
            # leaves the network when it reaches the boundary node
            self.dq[e].pop(); self.occ[e] -= self.pcu[vid]
            tdone = self.ready[vid]
            self.done[vid] = tdone
            k = int(tdone) + 1
            if vid == self.amb:
                self.amb_arrival = tdone          # the ambulance is not part of ordinary-traffic accounting
            else:
                self.completions[k] += 1
                self.comp_persons[k] += self.occp[vid]
        if vid == self.amb:
            self.amb_link_enter_t = t
            self.amb_entry_snapshot = (len(self.dq[e]) - 1) if self.perfect else self.est.get(e, 0.0)
            self.amb_entry_disch = self.disch[e]
            if not edge["is_exit"]:
                self.policy.on_amb_link_enter(self, t, e)

    def has_space(self, e, vid):
        edge = self.net.edges[e]
        return edge["is_exit"] or vid == self.amb or self.occ[e] + self.pcu[vid] <= edge["storage"] + 1e-9

    def head_wait_start(self, e, t):
        """Time since which the first queued (non-ambulance) vehicle on approach e has
        been waiting at the stop line, or None.  Models a stop-line presence detector."""
        for v in self.dq[e]:
            if self.ready[v] > t:
                return None
            if v != self.amb:
                return self.ready[v]
        return None

    def amb_edge(self):
        if not self.amb_in or self.amb_arrival is not None:
            return None
        return self.amb_route[self.pos[self.amb]]

    def amb_ahead_true(self):
        e = self.amb_edge()
        q = self.dq[e]
        return q.index(self.amb)

    def amb_ahead_est(self):
        """Vehicles ahead of the ambulance on its current link as the controller
        sees it: camera count snapshot at link entry minus exact stop-line discharges."""
        if self.perfect:
            return self.amb_ahead_true()
        e = self.amb_edge()
        return max(0.0, self.amb_entry_snapshot - (self.disch[e] - self.amb_entry_disch))

    def count_est(self, e):
        if self.net.edges[e]["is_exit"]:
            return 0.0                      # exit links never queue (no downstream signal)
        return float(len(self.dq[e])) if self.perfect else self.est[e]

    # ------------------------------------------------------------ main loop
    def run(self):
        net, edges = self.net, self.net.edges
        dq, occ, credit, ready, route, pos, pcu = self.dq, self.occ, self.credit, self.ready, self.route, self.pos, self.pcu
        nveh = len(self.trel) - 1
        order = sorted(range(nveh), key=lambda i: self.trel[i])
        ptr = 0
        first_edge = {o: net.first_edge(o) for o in net.boundaries if net.out[o]}
        completed = 0
        persons_done = 0
        idle = 0
        for t in range(self.T):
            # releases into external queues
            while ptr < nveh and self.trel[order[ptr]] <= t:
                v = order[ptr]
                o = edges[route[v][0]]["u"]
                self.ext[o].append(v)
                self.released += 1
                self.released_persons += self.occp[v]
                ptr += 1
            if not self.amb_in and t >= self.amb_dispatch:
                self.amb_in = True
                self.enter(self.amb, self.amb_route[0], t, offset_m=self.sc["amb"]["insert_pos_m"])
            # sensors
            if t % SENSOR_PERIOD == 0:
                self._sense(t)
            # control
            self.policy.on_tick(self, t)
            # ambulance yielding when it reaches the back of a queue
            ae = self.amb_edge()
            if ae is not None and self.rho > 0 and ready[self.amb] <= t and (ae, self.pos[self.amb]) not in self.amb_yield_done:
                self.amb_yield_done.add((ae, self.pos[self.amb]))
                q = dq[ae]
                i = q.index(self.amb)
                stay, go = [], []
                for k in range(i):
                    v = q[k]
                    if ready[v] <= t and self.ryield.random() < self.rho * self.ycls[v]:
                        go.append(v)
                    else:
                        stay.append(v)
                rest = list(q)[i + 1:]
                dq[ae] = q = deque(stay + [self.amb] + go + rest)
            # discharge
            moves = 0
            for j, J in self.junc.items():
                k, a = J.stages[J.idx][0], J.stages[J.idx][1]
                active = None
                if (k == "G" and J.elapsed >= 2) or k == "Y":
                    active = a
                for arm in J.arms:
                    if arm != active:
                        credit[arm] = 0.0
                        continue
                    q = dq[arm]
                    if not q:
                        credit[arm] = 0.0
                        continue
                    s = self.cap(arm, t)
                    credit[arm] += s
                    lanes = edges[arm]["lanes"]
                    while q:
                        cand = None
                        for i in range(min(lanes, len(q))):
                            v = q[i]
                            if ready[v] > t:
                                break
                            nxt = route[v][pos[v] + 1]
                            if self.has_space(nxt, v):
                                cand = i
                                break
                        if cand is None:
                            credit[arm] = min(credit[arm], s)
                            break
                        v = q[cand]
                        if credit[arm] < pcu[v] and v != self.amb:
                            break
                        if v != self.amb:
                            credit[arm] -= pcu[v]
                        del q[cand]
                        if v != self.amb:
                            w = t - ready[v]
                            self.wait_sum += w
                            self.wait_n += 1
                            if w > self.max_wait:
                                self.max_wait = w
                            if w > 180:
                                self.n_wait_over += 1
                        occ[arm] -= pcu[v]
                        self.disch[arm] += 1
                        pos[v] += 1
                        if v == self.amb:
                            self.amb_cross[j] = t
                            if self.audit and k not in ("G", "Y"):
                                self.violations.append(("amb_red", t, j))
                        self.enter(v, route[v][pos[v]], t)
                        moves += 1
            # admissions from external queues
            for o, xq in self.ext.items():
                if o not in first_edge:
                    continue
                e0 = first_edge[o]
                if not xq:
                    self.ext_credit[o] = 0.0
                    continue
                s = self.cap(e0, t)
                self.ext_credit[o] += s
                while xq:
                    v = xq[0]
                    if not self.has_space(e0, v) or self.ext_credit[o] < pcu[v]:
                        break
                    self.ext_credit[o] -= pcu[v]
                    xq.popleft()
                    self.enter(v, e0, t)
                    moves += 1
                if xq:
                    self.ext_credit[o] = min(self.ext_credit[o], max(s, pcu[xq[0]]))
            # bookkeeping
            completed += self.completions[t]
            persons_done += self.comp_persons[t]
            n_sys = self.released - completed + (1 if self.amb_in and self.amb_arrival is None else 0)
            self.N[t] = self.released - completed
            self.P[t] = self.released_persons - persons_done
            if self.audit:
                self._audit(t)
            idle = idle + 1 if (moves == 0 and n_sys > 0) else 0
            if idle >= 300 and self.gridlock_t is None:
                self.gridlock_t = t
            # advance signals
            for J in self.junc.values():
                self._advance(J, t)
        return self.results()

    # ------------------------------------------------------------ signals
    def _advance(self, J, t):
        J.elapsed += 1
        if J.kind == "G":
            J.served_green += 1
        if J.elapsed < J.dur:
            return
        k, a = J.kind, J.arm
        if k == "G":
            J.last_green_end[a] = t + 1
        nxt = (J.idx + 1) % len(J.stages)
        if k in ("R", "PR"):
            if J.override_next is not None:
                nxt = J.override_next
                J.override_next = None
            nxt = self.policy.choose_next(self, J, t + 1, nxt)
        J.idx, J.elapsed = nxt, 0
        J.dur = J.base()
        nk, na = J.kind, J.arm
        if nk == "G":
            red = t + 1 - J.last_green_end[na]
            if self.dq[na] and self.ready[self.dq[na][0]] <= t:      # 'demanded red': vehicles were waiting
                J.max_red[na] = max(J.max_red[na], red)
            J.last_green_start[na] = t + 1
            J.served_green = 0
        elif nk == "W":
            J.max_ped_wait = max(J.max_ped_wait, t + 1 - J.last_ped)
            J.last_ped = t + 1
        self.policy.stage_entered(self, J, t + 1)

    # ------------------------------------------------------------ sensors
    def _sense(self, t):
        rs = self.rs
        for e in self.approaches:
            up = self.sens_up[e]
            up = (rs.random() >= P_AM) if up else (rs.random() < P_MA)
            self.sens_up[e] = up
            if self.outage and e in self.outage[0] and self.outage[1] <= t < self.outage[2]:
                up = False
            noise = rs.choice(NOISE)
            if up:
                self.est[e] = max(0, len(self.dq[e]) + noise)
                self.est_age[e] = 0
            else:
                self.est_age[e] += SENSOR_PERIOD

    # ------------------------------------------------------------ audit (tests)
    def _audit(self, t):
        edges = self.net.edges
        for e, q in enumerate(self.dq):
            occ = sum(self.pcu[v] for v in q)
            if abs(occ - self.occ[e]) > 1e-6:
                self.violations.append(("occ_mismatch", t, e))
            amb_here = self.amb in q
            if occ > edges[e]["storage"] + (self.pcu[self.amb] if amb_here else 0) + 1e-6:
                self.violations.append(("storage", t, e))
        in_links = sum(len(q) for q in self.dq)
        in_ext = sum(len(q) for q in self.ext.values())
        amb_links = 1 if any(self.amb in q for q in self.dq) else 0
        n = len(self.done) - 1
        completed = sum(1 for i in range(n) if self.done[i] is not None and int(self.done[i]) + 1 <= t)
        in_transit = sum(1 for i in range(n) if self.done[i] is not None and int(self.done[i]) + 1 > t)
        # exact conservation: released = on links + external queues + on exit links + completed
        if self.released != in_links - amb_links + in_ext + in_transit + completed:
            self.violations.append(("conservation", t, self.released, in_links - amb_links, in_ext, in_transit, completed))
        if self.N[t] != self.released - completed:
            self.violations.append(("N_bookkeeping", t))
        for J in self.junc.values():
            k = J.kind
            if k == "G" and J.dur > 90:
                self.violations.append(("green_too_long", t, J.id, J.dur))
            if k == "G" and J.elapsed == 0 and J.dur < MIN_GREEN:
                self.violations.append(("min_green", t, J.id, J.dur))

    # ------------------------------------------------------------ results
    def results(self):
        juncs = self.junc.values()
        return dict(
            amb_tt=(self.amb_arrival - self.amb_dispatch) if self.amb_arrival is not None else None,
            amb_arrival=self.amb_arrival, dispatch=self.amb_dispatch,
            N=self.N, P=self.P,
            max_red=max(max(J.max_red.values()) for J in juncs),
            max_ped_wait=max(J.max_ped_wait for J in juncs),
            max_wait=self.max_wait, n_wait_over=self.n_wait_over,
            mean_stopline_wait=self.wait_sum / max(1, self.wait_n), n_discharged=self.wait_n,
            gridlock_t=self.gridlock_t,
            released=self.released,
            unfinished=self.N[-1],
            violations=self.violations,
            amb_route=[self.net.edges[e]["id"] for e in self.amb_route],
        )
