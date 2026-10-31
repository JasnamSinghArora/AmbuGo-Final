"""Verification suite for the AmbuGo v8 simulator and controllers.

  python3 tests/run_tests.py            # writes results/verification.json

T1  reproducibility and common random numbers
T2  runtime invariants under stress (conservation, storage, signal legality,
    ambulance never crosses on red, minimum greens)
T3  validation against Webster's (1958) delay formula on an isolated junction
T4  priority-cost check against an independent fluid (cumulative-curve) model
T5  1/(1-X) law for the cost of lost green
"""
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ambugo.network import Network, AMBER_S, ALLRED_S, PED_STAGES      # noqa: E402
from ambugo.design import Design                                       # noqa: E402
from ambugo.scenario import make_scenario                              # noqa: E402
from ambugo.sim import Simulator                                       # noqa: E402
from ambugo.policies import make_policy, NoPriority                    # noqa: E402

REPORT = {}


def check(name, cond, **info):
    REPORT[name] = dict(passed=bool(cond), **info)
    print(("PASS " if cond else "FAIL ") + name, info if info else "")
    return cond


# --------------------------------------------------------------------------- toy network
class ToyDesign:
    """Isolated junction J with test arm A (B_in->J) and a dummy conflicting arm D."""

    def __init__(self, s=0.5, g=30, g_dummy=30, ped=False, seed=1):
        nodes = {"B_in": dict(x=0, y=0, kind="B"), "J": dict(x=500, y=0, kind="J"),
                 "B_out": dict(x=1000, y=0, kind="B"), "B_d": dict(x=500, y=-500, kind="B"),
                 "B_d2": dict(x=500, y=500, kind="B")}
        edges = [dict(id="A", u="B_in", v="J", L=500, lanes=1, vff=10.0, s=s),
                 dict(id="OUT", u="J", v="B_out", L=500, lanes=1, vff=10.0, s=1.0),
                 dict(id="D", u="B_d", v="J", L=500, lanes=1, vff=10.0, s=s),
                 dict(id="DOUT", u="J", v="B_d2", L=500, lanes=1, vff=10.0, s=1.0)]
        for e in edges:
            e["L"] = float(e["L"])
        self.net = Network(nodes, edges)
        self.net.edges[0]["storage"] = 10 ** 6          # isolate queueing from spillback
        self.seed = seed
        A, D = self.net.eid["A"], self.net.eid["D"]
        stages = [("G", D, g_dummy), ("Y", D, AMBER_S), ("R", D, ALLRED_S),
                  ("G", A, g), ("Y", A, AMBER_S), ("R", A, ALLRED_S)]
        if ped:
            stages += [(k, None, d) for k, d in PED_STAGES]
        self.plans = {"J": dict(stages=stages, offset=0, cycle=sum(x[2] for x in stages))}
        self.cycle = self.plans["J"]["cycle"]
        self.g_eff = g + 1

    def scenario(self, q, horizon, rep=0, deterministic=False):
        r = random.Random(rep)
        A = self.net.eid["A"]
        OUT = self.net.eid["OUT"]
        vs, t = [], 0.0
        while True:
            t += (1.0 / q) if deterministic else r.expovariate(q)
            if t >= horizon - 600:
                break
            vs.append(dict(t=t, o="B_in", d="B_out", route=(A, OUT), cls="car", pcu=1.0, occ=1))
        return dict(rep=rep, vehicles=vs, shocks=[], incidents=[], horizon=horizon,
                    amb=dict(origin="B_in", dest="B_out", dispatch=10 ** 9, insert_pos_m=20.0, pcu=1.5, occ=3))


def webster_delay(C, g_eff, s, q):
    lam = g_eff / C
    X = q * C / (s * g_eff)
    return (C * (1 - lam) ** 2 / (2 * (1 - lam * X)) + X ** 2 / (2 * q * (1 - X))
            - 0.65 * (C / q ** 2) ** (1 / 3) * X ** (2 + 5 * lam))


# --------------------------------------------------------------------------- T1
def t1_reproducibility():
    net = Network.from_v7_geometry()
    d = Design(net, target_x=0.85)
    sc1, sc2 = make_scenario(d, 7), make_scenario(d, 7)
    same_scen = json.dumps(sc1, sort_keys=True, default=str) == json.dumps(sc2, sort_keys=True, default=str)
    r1 = Simulator(d, sc1, make_policy("P3C")).run()
    r2 = Simulator(d, make_scenario(d, 7), make_policy("P3C")).run()
    h = lambda r: hashlib.sha256(json.dumps([r["amb_tt"], r["N"], r["max_wait"]]).encode()).hexdigest()
    check("T1a_identical_rerun", same_scen and h(r1) == h(r2), hash=h(r1)[:16])
    # CRN: incident namespace change must not change demand realisation
    sc_noinc = make_scenario(d, 7, incident_prob=0.0)
    check("T1b_namespace_independence",
          [v["t"] for v in sc_noinc["vehicles"]] == [v["t"] for v in sc1["vehicles"]] and sc_noinc["amb"] == sc1["amb"])
    # replications differ
    check("T1c_replications_differ", make_scenario(d, 8)["vehicles"][0]["t"] != sc1["vehicles"][0]["t"])


# --------------------------------------------------------------------------- T2
def t2_invariants():
    net = Network.from_v7_geometry()
    viol, runs, cross_ok = [], 0, True
    for X in (0.8, 0.95):
        d = Design(net, target_x=X)
        for rep in range(3):
            sc = make_scenario(d, rep, horizon=1800, dispatch_window=(600, 700), incident_prob=1.0)
            for pol in ("P0", "P1", "P3C", "P4"):
                sim = Simulator(d, sc, make_policy(pol), rho_yield=0.5, audit=True)
                r = sim.run()
                viol += r["violations"]
                runs += 1
    kinds = sorted({v[0] for v in viol})
    check("T2_runtime_invariants", not viol, runs=runs, audited_ticks=runs * 1800, violation_kinds=kinds,
          checked=["exact vehicle conservation every tick", "PCU occupancy bookkeeping", "link storage never exceeded",
                   "ambulance never discharged outside green/amber", "minimum green 8 s at every green start",
                   "no green longer than 90 s", "single active stage per junction (by construction)"])


# --------------------------------------------------------------------------- T3
def t3_webster():
    rows, ok = [], True
    s = 0.5
    for X_target in (0.5, 0.7, 0.85):
        td = ToyDesign(s=s, g=30, g_dummy=30)
        q = X_target * s * td.g_eff / td.cycle
        waits = []
        for rep in range(12):
            sc = td.scenario(q, horizon=7800, rep=rep)
            r = Simulator(td, sc, NoPriority()).run()
            waits.append(r["mean_stopline_wait"])
        sim_d = sum(waits) / len(waits) - 0.5          # remove the 0.5 s mean discretisation lag (1 s ticks)
        w = webster_delay(td.cycle, td.g_eff, s, q)
        err = (sim_d - w) / w
        rows.append(dict(X=X_target, cycle=td.cycle, sim_delay_s=round(sim_d, 2), webster_s=round(w, 2), rel_err=round(err, 3)))
        ok &= abs(err) < 0.15
    check("T3_webster_validation", ok, tolerance="15%", rows=rows)
    return rows


# --------------------------------------------------------------------------- T4/T5
def fluid_extra_delay(C, g_eff, s, q, delta, t_cut, horizon, dt=0.01):
    """Independent fluid cumulative-curve model: area between departures with and
    without `delta` seconds of lost green in the cycle starting at t_cut."""
    def run(lost):
        Q, area, t = 0.0, 0.0, 0.0
        while t < horizon:
            phase = t % C
            green = phase < g_eff
            if lost and t_cut <= t < t_cut + delta:
                green = False
            Q += q * dt
            if green:
                Q = max(0.0, Q - s * dt)
            area += Q * dt
            t += dt
        return area
    return run(True) - run(False)


def t4_t5_priority_cost():
    s, rows, ok = 0.5, [], True
    for X_target in (0.5, 0.7, 0.8, 0.9):
        td = ToyDesign(s=s, g=40, g_dummy=30)
        C, ge = td.cycle, td.g_eff
        q = X_target * s * ge / C
        horizon = 7200
        delta = 10
        # simulator: truncate test-arm green by delta once at cycle k=10 (deterministic arrivals)
        class Cut(NoPriority):
            # truncate the test-arm green by delta once and give the seconds to the
            # conflicting arm, so the cycle clock (and arrivals' phase) is unchanged
            pending = [False]

            def stage_entered(self, sim, J, t):
                if J.kind == "G" and J.arm == td.net.eid["A"] and 10 * C <= t < 11 * C:
                    J.dur = J.base() - delta
                    self.pending[0] = True
                elif J.kind == "G" and J.arm == td.net.eid["D"] and self.pending[0]:
                    J.dur = J.base() + delta
                    self.pending[0] = False
        sc = td.scenario(q, horizon=horizon, deterministic=True)
        base = Simulator(td, sc, NoPriority()).run()
        cut = Simulator(td, sc, Cut()).run()
        sim_extra = sum(cut["N"]) - sum(base["N"])
        # fluid model: test-arm green occupies [33+... ] -> align: test green starts at g_dummy+5 within cycle
        g_start = 30 + AMBER_S + ALLRED_S + 2       # +2 s start-up loss
        # shift time so test green is at phase 0 in the fluid model
        t_cut = 10 * C + (ge - delta)                # last delta seconds of that green are lost
        fl = fluid_extra_delay(C, ge, s, q, delta, t_cut - 0, horizon=horizon)
        closed = (s * delta) ** 2 / (2 * s * ge / C * (1 - X_target))
        err = (sim_extra - fl) / fl
        rows.append(dict(X=X_target, sim_extra_veh_s=round(sim_extra, 1), fluid_extra_veh_s=round(fl, 1),
                         closed_form_veh_s=round(closed, 1), rel_err_vs_fluid=round(err, 3)))
        ok &= abs(err) < 0.2
    check("T4_priority_cost_vs_fluid_model", ok, tolerance="20%", rows=rows)
    # T5: extra delay * (1-X) roughly constant (1/(1-X) law)
    k = [r["fluid_extra_veh_s"] * (1 - r["X"]) for r in rows]
    spread = (max(k) - min(k)) / (sum(k) / len(k))
    check("T5_inverse_one_minus_X_law", spread < 0.35, scaled_values=[round(x, 1) for x in k], relative_spread=round(spread, 3))
    return rows


def t6_information_boundary():
    """Public fixture files must not depend on the plant replication (no leakage of hidden truth)."""
    import tempfile
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_fixture import export
    with tempfile.TemporaryDirectory() as tmp:
        ms = [export(0.85, rep, Path(tmp) / f"r{rep}") for rep in (0, 1, 2)]
    hs = [{f["file"]: f["sha256"] for f in m["files"]} for m in ms]
    pub = [f for f in hs[0] if f.startswith("public/")]
    same = all(h[f] == hs[0][f] for h in hs[1:] for f in pub)
    differ = all(any(h[f] != hs[0][f] for h in hs[1:]) for f in hs[0] if f.startswith("hidden/") and all(f in h for h in hs))
    check("T6_public_files_independent_of_plant_truth", same and differ, public_files=len(pub))


if __name__ == "__main__":
    t0 = time.time()
    t1_reproducibility()
    t2_invariants()
    t3_webster()
    t4_t5_priority_cost()
    t6_information_boundary()
    REPORT["_runtime_s"] = round(time.time() - t0, 1)
    out = ROOT / "results" / "verification.json"
    out.write_text(json.dumps(REPORT, indent=2))
    n_fail = sum(1 for k, v in REPORT.items() if isinstance(v, dict) and not v["passed"])
    print(f"\n{len(REPORT) - 1 - n_fail}/{len(REPORT) - 1} checks passed -> {out}")
    sys.exit(1 if n_fail else 0)
