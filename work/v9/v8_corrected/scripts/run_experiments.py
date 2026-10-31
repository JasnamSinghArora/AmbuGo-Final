"""Pre-registered experiment pipeline for AmbuGo v8.

Phase T  tuning      training replications 5000-5039 only
Phase E  evaluation  held-out replications 0-199, X x rho x policy, paired CRN
Phase V  value of information (perfect vs noisy state) for the proposed policy
Phase N  noise floor / placebo (how big is a 'difference' produced by a trivial perturbation?)
Phase B  v7 baseline vs v8 baseline at the same demand

Usage: python3 scripts/run_experiments.py [T|E|V|N|B|all] [--reps 200] [--procs 2]
"""
import argparse
import csv
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ambugo.network import Network                     # noqa: E402
from ambugo.design import Design                       # noqa: E402
from ambugo.scenario import make_scenario              # noqa: E402
from ambugo.sim import Simulator                       # noqa: E402
from ambugo.policies import make_policy, NoPriority    # noqa: E402

RES = ROOT / "results"
X_LEVELS = (0.6, 0.7, 0.8, 0.85, 0.9, 0.95)
RHO_LEVELS = (0.0, 0.5)
POLICIES = ("P1", "P2", "P3", "P3C", "P4")
ALIGN = (-60, 2000)          # window for dispatch-aligned Delta N curves

_DES = {}


def design(X):
    if X not in _DES:
        _DES[X] = Design(Network.from_v7_geometry(), target_x=X)
    return _DES[X]


def recovery_time(dN, arrival_idx, thresh=3.0, win=60):
    """Seconds after ambulance arrival until the 60 s rolling mean of |Delta N| stays below thresh.
    Returns (value, censored)."""
    a = np.abs(np.asarray(dN, float))
    if len(a) < win:
        return 0.0, False
    roll = np.convolve(a, np.ones(win) / win, mode="same")
    above = np.nonzero(roll[arrival_idx:] >= thresh)[0]
    if len(above) == 0:
        return 0.0, False
    last = above[-1]
    censored = last >= len(roll) - arrival_idx - win // 2 - 1
    return float(last), bool(censored)


def summarise(r, base, d):
    t0 = r["dispatch"]
    N, P = np.asarray(r["N"]), np.asarray(r["P"])
    out = dict(amb_tt=r["amb_tt"], delay_vh=float(N[t0:].sum() / 3600), delay_ph=float(P[t0:].sum() / 3600),
               max_wait=r["max_wait"], n_wait_over=r["n_wait_over"], max_ped_wait=r["max_ped_wait"],
               gridlock=r["gridlock_t"] is not None, unfinished=r["unfinished"])
    if base is not None:
        N0, P0 = np.asarray(base["N"]), np.asarray(base["P"])
        dN = N - N0
        out["d_delay_vh"] = float(dN[t0:].sum() / 3600)
        out["d_delay_ph"] = float((P - P0)[t0:].sum() / 3600)
        out["d_unfinished"] = int(dN[-1])
        arr = int(r["amb_arrival"]) if r["amb_arrival"] is not None else len(N) - 1
        out["recovery_s"], out["recovery_censored"] = recovery_time(dN, min(arr, len(N) - 1))
        seg = np.full(ALIGN[1] - ALIGN[0], np.nan)
        lo, hi = t0 + ALIGN[0], min(len(N), t0 + ALIGN[1])
        seg[: hi - lo] = dN[lo:hi]
        out["_dN"] = seg
    return out


def run_cell(job):
    X, rho, rep, pols, perfect = job["X"], job["rho"], job["rep"], job["pols"], job.get("perfect", False)
    d = design(X)
    sc = make_scenario(d, rep)
    base = Simulator(d, sc, NoPriority(), rho_yield=rho).run()
    rows = []
    b = summarise(base, None, d)
    rows.append(dict(X=X, rho=rho, rep=rep, policy="P0", perfect=perfect, origin=sc["amb"]["origin"],
                     dispatch=sc["amb"]["dispatch"], incident=bool(sc["incidents"]), **b))
    for label, (name, params) in pols.items():
        pol = make_policy(name, **params)
        r = Simulator(d, sc, pol, rho_yield=rho, perfect_info=perfect).run()
        s = summarise(r, base, d)
        rows.append(dict(X=X, rho=rho, rep=rep, policy=label, perfect=perfect, origin=sc["amb"]["origin"],
                         dispatch=sc["amb"]["dispatch"], incident=bool(sc["incidents"]),
                         guard_hits=pol.guard_hits, **s))
    return rows


def run_jobs(jobs, procs, tag):
    t = time.time()
    rows = []
    with Pool(procs) as pool:
        for i, rr in enumerate(pool.imap_unordered(run_cell, jobs, chunksize=4)):
            rows += rr
            if (i + 1) % 200 == 0:
                print(f"  [{tag}] {i + 1}/{len(jobs)} scenarios, {time.time() - t:.0f}s", flush=True)
    print(f"  [{tag}] done {len(jobs)} scenarios in {time.time() - t:.0f}s", flush=True)
    return rows


def write_rows(rows, path):
    curves = {}
    flat = []
    for r in rows:
        r = dict(r)
        dN = r.pop("_dN", None)
        if dN is not None:
            curves.setdefault((r["X"], r["rho"], r["policy"], r["perfect"]), []).append(dN)
        flat.append(r)
    keys = sorted({k for r in flat for k in r})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(flat)
    return curves


# ----------------------------------------------------------------------------- phases
def phase_T(procs, reps=40):
    grid = {}
    for H in (20, 30, 60):
        grid[f"P1_H{H}"] = ("P1", dict(H=H))
        grid[f"P2_H{H}"] = ("P2", dict(H=H))
    for m in (0, 10, 20, 30):
        grid[f"P3_m{m}"] = ("P3", dict(margin=m))
    jobs = [dict(X=X, rho=rho, rep=5000 + k, pols=grid) for X in (0.8, 0.9) for rho in RHO_LEVELS for k in range(reps)]
    rows = run_jobs(jobs, procs, "tune")
    write_rows(rows, RES / "tuning_runs.csv")
    # selection rule (pre-declared): minimise mean ambulance time; among candidates within one
    # paired standard error of the best, pick the one with the smallest mean ordinary-delay change.
    import pandas as pd
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_dN"} for r in rows])
    tuned, table = {}, []
    for fam in ("P1", "P2", "P3"):
        cands = [c for c in grid if c.startswith(fam + "_")]
        stats = {}
        for c in cands:
            sub = df[df.policy == c].sort_values(["X", "rho", "rep"])
            stats[c] = (sub.amb_tt.mean(), sub.d_delay_vh.mean(), sub.amb_tt.values)
        best = min(stats, key=lambda c: stats[c][0])
        ok = []
        for c in cands:
            diff = stats[c][2] - stats[best][2]
            se = diff.std(ddof=1) / np.sqrt(len(diff)) if c != best else 0.0
            if diff.mean() <= se:
                ok.append(c)
        pick = min(ok, key=lambda c: stats[c][1])
        tuned[fam] = grid[pick][1]
        for c in cands:
            table.append(dict(family=fam, candidate=c, mean_amb_tt=round(stats[c][0], 2),
                              mean_d_delay_vh=round(stats[c][1], 3), within_1se_of_best=c in ok, selected=c == pick))
    json.dump(dict(tuned=tuned, table=table, training_reps=[5000, 5000 + reps - 1],
                   rule="min mean ambulance time; ties within 1 paired SE broken by min mean ordinary delay"),
              open(RES / "tuned_parameters.json", "w"), indent=2)
    print("tuned:", tuned)
    return tuned


def tuned_policies():
    t = json.load(open(RES / "tuned_parameters.json"))["tuned"]
    p3 = t["P3"]
    return {"P1": ("P1", t["P1"]), "P2": ("P2", t["P2"]), "P3": ("P3", p3),
            "P3C": ("P3C", p3), "P4": ("P4", p3)}


def phase_E(procs, reps):
    pols = tuned_policies()
    jobs = [dict(X=X, rho=rho, rep=k, pols=pols) for X in X_LEVELS for rho in RHO_LEVELS for k in range(reps)]
    rows = run_jobs(jobs, procs, "eval")
    curves = write_rows(rows, RES / "eval_runs.csv")
    np.savez_compressed(RES / "eval_dN_curves.npz",
                        **{f"{X}|{rho}|{p}": np.nanmean(np.vstack(v), axis=0) for (X, rho, p, _), v in curves.items()})


def phase_V(procs, reps):
    p3 = tuned_policies()["P3"]
    rows = []
    for perfect in (False, True):
        jobs = [dict(X=X, rho=0.0, rep=k, pols={"P3": p3}, perfect=perfect) for X in (0.8, 0.9, 0.95) for k in range(reps)]
        rows += run_jobs(jobs, procs, f"voi-{perfect}")
    write_rows(rows, RES / "voi_runs.csv")


class PureFixedTime(NoPriority):
    """Fixed-time plan with NO wait guard (as specified in v7)."""
    name = "fixed"

    def choose_next(self, sim, J, t, cand):
        return cand


class OffsetNudge(NoPriority):
    """Placebo: P0 with the stage clock of ONE junction off the ambulance route nudged by 1 s
    at the dispatch time.  Any 'effect' is pure chaotic divergence."""
    name = "placebo"

    def __init__(self, junction):
        super().__init__()
        self.j, self.done = junction, False

    def on_tick(self, sim, t):
        if not self.done and t >= sim.amb_dispatch:
            J = sim.junc[self.j]
            J.dur += 1
            self.done = True


def _placebo_cell(job):
    d = design(job["X"])
    sc = make_scenario(d, job["rep"])
    base = Simulator(d, sc, NoPriority()).run()
    route_j = {d.net.edges[e]["v"] for e in Simulator(d, sc, NoPriority()).amb_route}
    off = sorted(j for j in d.net.junctions if j not in route_j)
    j = off[job["rep"] % len(off)]
    r = Simulator(d, sc, OffsetNudge(j)).run()
    t0 = sc["amb"]["dispatch"]
    dN = np.asarray(r["N"]) - np.asarray(base["N"])
    return dict(X=job["X"], rep=job["rep"], junction=j, d_delay_vh=float(dN[t0:].sum() / 3600),
                max_abs_dN=int(np.abs(dN).max()))


def phase_N(procs, reps):
    jobs = [dict(X=X, rep=k) for X in (0.7, 0.9, 0.95) for k in range(reps)]
    with Pool(procs) as pool:
        rows = list(pool.imap_unordered(_placebo_cell, jobs, chunksize=4))
    with open(RES / "placebo_runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("  [placebo] done", len(rows))


def phase_B():
    """Same demand (kappa = 1, the v7 level), v7 random signal plan vs v8 Webster plan."""
    import pandas as pd
    net = Network.from_v7_geometry()
    v8 = Design(net, target_x=0.85)
    v8.kappa = 1.0
    v8.plans = v8.webster(1.0)
    v7 = Design(net, target_x=0.85)
    v7.kappa = 1.0
    sp = pd.read_csv(ROOT / "data" / "v7_signal_plans.csv")
    plans = {}
    for _, row in sp.iterrows():
        j = row.junction_id
        arms = net.arms[j]
        stages = []
        for name, dur in zip(row.phase_order.split("|"), map(int, str(row.stage_durations_s).split("|"))):
            if "_PED_" in name:
                kind = {"WALK": "W", "CLEARANCE": "PC", "ALLRED": "PR"}[name.split("_")[-1]]
                stages.append((kind, None, dur))
            else:
                parts = name.split("_")
                arm = arms[int(parts[1][1:])]
                kind = "G" if len(parts) == 2 else ("Y" if parts[2] == "AMBER" else "R")
                stages.append((kind, arm, dur))
        X = {a: v8.unit_load[a] * row.cycle_s / (net.edges[a]["s"] * (g + 1))
             for (k, a, g) in stages if k == "G"}
        plans[j] = dict(stages=stages, cycle=int(row.cycle_s), offset=int(row.offset_s), X=X)
    v7.plans = plans
    out = {}
    H = 7200
    for name, d, ctl in (("v7_random_plan", v7, NoPriority), ("v8_webster_plan", v8, NoPriority),
                         ("v7_random_plan_pure_fixed_time", v7, PureFixedTime), ("v8_webster_plan_pure_fixed_time", v8, PureFixedTime)):
        Ns, ext, waits = [], [], []
        for rep in range(20):
            sc = make_scenario(d, 9000 + rep, horizon=H, dispatch_window=(10 ** 6, 10 ** 6))
            sim = Simulator(d, sc, ctl())
            r = sim.run()
            Ns.append(r["N"]); waits.append(r["mean_stopline_wait"])
            ext.append(sum(len(q) for q in sim.ext.values()))
        M = np.asarray(Ns, float)
        out[name] = dict(max_X=round(max(max(p["X"].values()) for p in d.plans.values()), 3),
                         n_X_over_1=int(sum(x > 1 for p in d.plans.values() for x in p["X"].values())),
                         mean_N_1800_3600=round(float(M[:, 1800:3600].mean()), 1),
                         mean_N_5400_7200=round(float(M[:, 5400:].mean()), 1),
                         growth_veh_per_h_after_warmup=round(float((M[:, 5400:].mean() - M[:, 1800:3600].mean()) / 1.0), 1),
                         external_queue_at_end=round(float(np.mean(ext)), 1),
                         mean_stopline_wait_s=round(float(np.mean(waits)), 1))
        np.save(RES / f"baseline_N_{name}.npy", M.mean(axis=0))
    json.dump(out, open(RES / "v7_vs_v8_baseline.json", "w"), indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", default="all", nargs="?")
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args()
    RES.mkdir(exist_ok=True)
    ph = a.phase
    if ph in ("T", "all"):
        phase_T(a.procs)
    if ph in ("B", "all"):
        phase_B()
    if ph in ("E", "all"):
        phase_E(a.procs, a.reps)
    if ph in ("V", "all"):
        phase_V(a.procs, a.reps)
    if ph in ("N", "all"):
        phase_N(a.procs, a.reps)
