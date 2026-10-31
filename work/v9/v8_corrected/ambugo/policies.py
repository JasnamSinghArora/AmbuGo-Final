"""Ambulance signal-priority policies.

P0  no priority (Webster fixed-time baseline)
P1  classic EVP as in v7: queue-blind ETA trigger, green extension (cap 10 s),
    truncation of conflicting greens to the 8 s minimum, NO phase skipping
P2  preemption: P1 + phase skip (jump to the ambulance approach after the current
    clearance; pedestrian stage only skipped if its wait clock allows) + hold
    until the ambulance has crossed (cap 60 s)
P3  queue-aware preemption (proposed): P2, but the trigger subtracts the estimated
    time to discharge the queue ahead of the ambulance (and adds upstream queue
    delays), so the green starts early enough to flush that queue; hold cap 90 s
P3C P3 + service-deficit compensation after the ambulance crosses: every arm that
    was short-changed during priority gets its deficit back on its next green
P4  P3C + queue-aware ambulance re-routing at every link entry

All parameters are explicit; tuned values are chosen on TRAINING replications only.
"""
import heapq
from .network import MEAN_PCU, MIN_GREEN, MAX_GREEN, simple_paths

PED_SKIP_LIMIT = 120     # s since last walk start after which the walk stage cannot be skipped
PED_LIMIT = 180          # hard cap on pedestrian wait between walk starts (v7 design value)
RED_LIMIT = 180          # hard cap on any ordinary vehicle's stop-line wait (v7 max_vehicle_wait_design_s)
GUARD_BUFFER = 10        # s safety buffer for the guard look-ahead
JUNCTION_PENALTY = 5.0   # s, routing cost per signalised junction under priority


class NoPriority:
    """Base controller shared by ALL policies: Webster fixed-time plan plus an
    earliest-deadline-first wait guard (no ordinary vehicle waits > 180 s at a stop
    line, no pedestrian waits > 180 s between walk stages, where feasible).
    Priority policies differ from P0 only in the ambulance logic."""
    name = "P0"
    compensate = False

    def __init__(self, **kw):
        self.params = kw
        self.guard_hits = 0

    def attach(self, sim):
        self.sim = sim

    def initial_amb_route(self, sim, amb):
        return simple_paths(sim.net, amb["origin"], amb["dest"], slack=1.0, kmax=1)[0][1]

    def on_tick(self, sim, t):
        pass

    def stage_entered(self, sim, J, t):
        pass

    def on_amb_link_enter(self, sim, t, e):
        pass

    def _deadlines(self, sim, J, t, cand, extra=0):
        """Walk the stage sequence starting with `cand` at time t (base durations,
        `extra` seconds added to the first stage if it is a green) and return
        [(slack, deadline, stage_index)] for the pedestrian stage and every arm with
        waiting vehicles; slack < 0 means the wait limit would be broken."""
        n = len(J.stages)
        i, clock = cand, t
        start = {}
        for step in range(n + 1):
            kind, arm, dur = J.stages[i]
            key = "PED" if kind == "W" else (arm if kind == "G" else None)
            if key is not None and key not in start:
                start[key] = clock
            if step == 0 and kind == "G":
                dur += extra
            clock += dur
            i = (i + 1) % n
        out = []
        if "PED" in start:
            dl = J.last_ped + PED_LIMIT
            out.append((dl - GUARD_BUFFER - start["PED"], dl, next(k for k, s in enumerate(J.stages) if s[0] == "W")))
        for b in J.arms:
            w0 = sim.head_wait_start(b, t)          # stop-line presence detector
            if b in start and w0 is not None:
                dl = w0 + RED_LIMIT
                out.append((dl - GUARD_BUFFER - start[b], dl, J.stage_of_green[b]))
        return out

    def choose_next(self, sim, J, t, cand):
        """Earliest-deadline-first guard at every stage-selection point."""
        late = [(dl, idx) for slack, dl, idx in self._deadlines(sim, J, t, cand) if slack < 0]
        if not late:
            return cand
        self.guard_hits += 1
        return min(late)[1]


class Priority(NoPriority):
    def __init__(self, name, H=30, skip=False, queue_aware=False, margin=0.0, ext_cap=10, hold_cap=60,
                 compensate=False, reroute=False, horizon_junctions=4):
        self.name = name
        self.H, self.skip, self.qa, self.margin = H, skip, queue_aware, margin
        self.ext_cap, self.hold_cap, self.compensate, self.reroute = ext_cap, hold_cap, compensate, reroute
        self.horizon_j = horizon_junctions
        self.params = dict(H=H, skip=skip, queue_aware=queue_aware, margin=margin, ext_cap=ext_cap,
                           hold_cap=hold_cap, compensate=compensate, reroute=reroute)
        self.active = {}        # junction -> dict(arm, t0, served{arm:s})
        self.done = set()
        self.decision_calls = 0
        self.guard_hits = 0
        self.recovering = {}    # junction -> release time; guard stays on for 2 cycles after release

    # ------------------------------------------------------------------ estimation helpers
    def _tclear(self, sim, e, ahead):
        return ahead * MEAN_PCU / sim.net.edges[e]["s"]

    def _upcoming(self, sim, t):
        """(junction, approach edge, metric) for the next junctions on the ambulance route."""
        e = sim.amb_edge()
        if e is None:
            return []
        k = sim.pos[sim.amb]
        route = sim.amb_route
        edges = sim.net.edges
        eta = max(0.0, sim.ready[sim.amb] - t)
        qup = 0.0
        out = []
        for m in range(k, len(route)):
            a = route[m]
            if m > k:
                eta += edges[a]["tt"]
            j = edges[a]["v"]
            if sim.net.nodes[j]["kind"] != "J":
                break
            ahead = sim.amb_ahead_est() if m == k else sim.count_est(a)
            tc = self._tclear(sim, a, ahead)
            metric = (eta + qup - tc - self.margin) if self.qa else eta
            out.append((j, a, metric, eta + qup))
            qup += tc
            if len(out) >= self.horizon_j:
                break
        return out

    # ------------------------------------------------------------------ control
    def on_tick(self, sim, t):
        self.decision_calls += 1
        # junctions the ambulance has crossed -> release
        for j in list(self.active):
            if j in sim.amb_cross or sim.amb_arrival is not None or j not in self._route_junctions(sim):
                self._release(sim, sim.junc[j], t)
        for j in list(self.recovering):
            J = sim.junc[j]
            if t - self.recovering[j] > 2 * sum(x[2] for x in J.stages):
                del self.recovering[j]
                continue
            forced = self._guard(sim, J, {"arm": None}, t)
            if forced is not None and J.override_next is None:
                self.guard_hits += 1
                J.override_next = forced
        if sim.amb_edge() is None:
            return
        for j, a, metric, eta in self._upcoming(sim, t):
            if j in self.done or j in sim.amb_cross:
                continue
            if j not in self.active and metric <= self.H:
                self.active[j] = dict(arm=a, t0=t, served={b: 0 for b in sim.junc[j].arms}, eta=eta)
            if j in self.active:
                self.active[j]["eta"] = eta
                self._control(sim, sim.junc[j], self.active[j], t)

    def _route_junctions(self, sim):
        k = sim.pos[sim.amb]
        return {sim.net.edges[e]["v"] for e in sim.amb_route[k:]}

    def _guard(self, sim, J, st, t):
        """Hard protection layer (applies to every priority policy).
        Returns the stage index that MUST be served next, or None.
        A red-starved arm (with vehicles waiting) or the pedestrian stage is forced
        once the wait it would accumulate by the end of the current stage plus
        clearance reaches the limit minus a safety buffer."""
        remaining = max(0, J.dur - J.elapsed)
        if J.kind == "G":
            remaining += 5
        horizon = t + remaining + GUARD_BUFFER
        if J.kind not in ("W", "PC", "PR") and horizon - J.last_ped >= PED_LIMIT:
            return next(i for i, s in enumerate(J.stages) if s[0] == "W")
        worst, arm = 0, None
        for b in J.arms:
            if b == st["arm"] or (J.kind == "G" and J.arm == b):
                continue
            w0 = sim.head_wait_start(b, t)
            if w0 is None:
                continue
            red = horizon - w0
            if red >= RED_LIMIT and red > worst:
                worst, arm = red, b
        return None if arm is None else J.stage_of_green[arm]

    def _control(self, sim, J, st, t):
        a = st["arm"]
        k = J.kind
        forced = self._guard(sim, J, st, t)
        if forced is not None:
            self.guard_hits += 1
            # stop holding the ambulance green, serve the protected stage next
            if k == "G" and J.arm == a:
                J.dur = max(J.elapsed + 1, min(J.dur, MIN_GREEN))
            elif k == "G":
                st["served"][J.arm] += 1
            J.override_next = forced
            return
        if k == "G":
            st["served"][J.arm] += 1
            if J.arm == a:
                if self.skip:
                    cap = self.hold_cap
                    J.dur = min(max(J.dur, J.elapsed + 2), max(cap, J.dur))
                else:  # classic extension: only if the ambulance can make it within the cap
                    base = J.base()
                    remaining = J.dur - J.elapsed
                    if st["eta"] <= remaining + self.ext_cap:
                        J.dur = min(max(J.dur, J.elapsed + int(st["eta"]) + 2), base + self.ext_cap)
            else:
                newdur = max(MIN_GREEN, J.elapsed + 1)
                if J.dur > newdur:
                    J.dur = newdur
        if self.skip:
            gi = J.stage_of_green[a]
            ped_due = (t - J.last_ped) > PED_SKIP_LIMIT
            if k in ("W", "PC", "PR"):
                J.override_next = gi
            elif k in ("G", "Y", "R"):
                if ped_due:
                    J.override_next = next(i for i, s in enumerate(J.stages) if s[0] == "W")
                else:
                    J.override_next = gi

    def stage_entered(self, sim, J, t):
        st = self.active.get(J.id)
        if st is not None and J.kind == "G" and J.arm != st["arm"]:
            J.dur = MIN_GREEN                         # minimal service while ambulance pending
        elif st is None and self.compensate and J.kind == "G" and J.comp[J.arm] > 0:
            want = min(int(round(J.comp[J.arm])), MAX_GREEN - J.base())
            slack = min([sl for sl, _, idx in self._deadlines(sim, J, t, J.idx) if idx != J.idx] or [want])
            extra = max(0, min(want, int(slack)))
            J.dur = J.base() + extra
            J.comp[J.arm] = 0

    def _release(self, sim, J, t):
        st = self.active.pop(J.id)
        self.done.add(J.id)
        self.recovering[J.id] = t
        J.override_next = None
        if J.kind == "G" and J.arm == st["arm"]:
            J.dur = max(J.elapsed + 1, min(J.dur, J.base()))
        if self.compensate:
            T = max(1, t - st["t0"])
            cyc = sum(s[2] for s in J.stages)
            for b in J.arms:
                if b == st["arm"]:
                    continue
                base_b = J.stages[J.stage_of_green[b]][2]
                deficit = base_b * T / cyc - st["served"][b]
                if deficit > 0:
                    J.comp[b] += deficit

    # ------------------------------------------------------------------ routing
    def on_amb_link_enter(self, sim, t, e):
        if not self.reroute:
            return
        net = sim.net
        dest = sim.sc["amb"]["dest"]
        k = sim.pos[sim.amb]
        cur = sim.amb_route[k:]

        def cost(x):
            return net.edges[x]["tt"] + self._tclear(sim, x, sim.count_est(x)) + (
                JUNCTION_PENALTY if net.nodes[net.edges[x]["v"]]["kind"] == "J" else 0)

        # Dijkstra over edges (state = edge) to respect no-U-turn movements
        dist = {e: 0.0}
        prev = {}
        pq = [(0.0, e)]
        best = None
        while pq:
            d, x = heapq.heappop(pq)
            if d > dist.get(x, 1e18):
                continue
            if net.edges[x]["v"] == dest:
                best = x
                break
            for y in net.out[net.edges[x]["v"]]:
                if not net.allowed(x, y):
                    continue
                v = net.edges[y]["v"]
                if net.nodes[v]["kind"] == "B" and v != dest:
                    continue
                nd = d + cost(y)
                if nd < dist.get(y, 1e18):
                    dist[y] = nd
                    prev[y] = x
                    heapq.heappush(pq, (nd, y))
        if best is None:
            return
        path = [best]
        while path[-1] != e:
            path.append(prev[path[-1]])
        path.reverse()
        old = sum(cost(x) for x in cur[1:])
        new = dist[best]
        if tuple(path) != tuple(cur) and new < old - 10.0:   # hysteresis: switch only for >10 s gain
            del sim.amb_route[k:]
            sim.amb_route.extend(path)


def make_policy(name, **over):
    presets = {
        "P0": None,
        "P1": dict(H=30, skip=False),
        "P2": dict(H=30, skip=True, hold_cap=60),
        "P3": dict(H=15, skip=True, queue_aware=True, margin=10, hold_cap=90),
        "P3C": dict(H=15, skip=True, queue_aware=True, margin=10, hold_cap=90, compensate=True),
        "P4": dict(H=15, skip=True, queue_aware=True, margin=10, hold_cap=90, compensate=True, reroute=True),
    }
    if name == "P0":
        return NoPriority()
    p = dict(presets[name]); p.update(over)
    return Priority(name, **p)
