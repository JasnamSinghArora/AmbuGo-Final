"""Turn experiment outputs into tables (results/tables/*.csv, results/summary.json) and figures."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ambugo.stats import paired_ci, sign_flip_p, holm, clopper_pearson, cvar   # noqa: E402

RES = ROOT / "results"
FIG = RES / "figures"
TAB = RES / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)

# reference categorical palette, fixed order (validated light-mode slots)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
POL = ["P0", "P1", "P2", "P3", "P3C", "P4"]
POL_LABEL = {"P0": "P0 no priority", "P1": "P1 classic EVP (v7)", "P2": "P2 preempt + skip",
             "P3": "P3 queue-aware", "P3C": "P3C + compensation", "P4": "P4 + re-routing"}
COLOR = dict(zip(POL, SERIES))

plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF,
                     "axes.facecolor": SURF, "savefig.facecolor": SURF, "legend.frameon": False,
                     "lines.linewidth": 2, "font.family": "DejaVu Sans"})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=160)
    plt.close(fig)


def main():
    df = pd.read_csv(RES / "eval_runs.csv")
    summary = {}
    # ------------------------------------------------------------- core table
    rows = []
    pv = {}
    for (X, rho), g in df.groupby(["X", "rho"]):
        base = g[g.policy == "P0"].set_index("rep")
        for p in POL:
            s = g[g.policy == p].set_index("rep").loc[base.index]
            tt = s.amb_tt.values
            r = dict(X=X, rho=rho, policy=p, n=len(s), amb_mean=tt.mean(), amb_p50=np.median(tt),
                     amb_p90=np.quantile(tt, 0.9), amb_cvar90=cvar(tt, 0.9),
                     max_wait_p95=np.quantile(s.max_wait, 0.95), n_wait_over_mean=s.n_wait_over.mean(),
                     ped_wait_max=s.max_ped_wait.max(), gridlock_runs=int(s.gridlock.sum()))
            if p != "P0":
                dtt = tt - base.amb_tt.values
                r["d_amb_mean"], r["d_amb_lo"], r["d_amb_hi"] = paired_ci(dtt)
                for col, key in (("d_delay_vh", "d_delay"), ("d_delay_ph", "d_pdelay")):
                    m, lo, hi = paired_ci(s[col].values)
                    r[key + "_mean"], r[key + "_lo"], r[key + "_hi"] = m, lo, hi
                pv[(X, rho, p)] = sign_flip_p(s.d_delay_vh.values)
                r["recovery_med_s"] = float(np.median(s.recovery_s))
                r["recovery_censored_frac"] = float(s.recovery_censored.mean())
                k = int((s.n_wait_over.values > base.n_wait_over.values).sum())
                r["frac_runs_more_overcap_waits"] = k / len(s)
                r["d_wait_over_mean"] = float((s.n_wait_over.values - base.n_wait_over.values).mean())
            rows.append(r)
    T = pd.DataFrame(rows)
    adj = holm({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in pv.items()})
    T["p_delay_holm"] = [adj.get(f"{r.X}|{r.rho}|{r.policy}", np.nan) for r in T.itertuples()]
    T.round(4).to_csv(TAB / "main_results.csv", index=False)

    # ------------------------------------------------------------- headline numbers
    def get(X, rho, p, c):
        return float(T[(T.X == X) & (T.rho == rho) & (T.policy == p)][c].iloc[0])
    summary["n_runs"] = int(len(df))
    summary["reps_per_cell"] = int(df.groupby(["X", "rho", "policy"]).size().min())
    summary["headline"] = {}
    for X in sorted(df.X.unique()):
        for rho in sorted(df.rho.unique()):
            summary["headline"][f"X={X},rho={rho}"] = {
                p: dict(amb_mean=round(get(X, rho, p, "amb_mean"), 1), amb_p90=round(get(X, rho, p, "amb_p90"), 1),
                        **({} if p == "P0" else dict(
                            d_amb=[round(get(X, rho, p, c), 1) for c in ("d_amb_mean", "d_amb_lo", "d_amb_hi")],
                            d_delay_vh=[round(get(X, rho, p, c), 2) for c in ("d_delay_mean", "d_delay_lo", "d_delay_hi")],
                            p_holm=round(get(X, rho, p, "p_delay_holm"), 4))))
                for p in POL}

    # ------------------------------------------------------------- placebo noise floor
    if (RES / "placebo_runs.csv").exists():
        pl = pd.read_csv(RES / "placebo_runs.csv")
        summary["placebo"] = {str(X): dict(sd_d_delay_vh=round(g.d_delay_vh.std(), 3),
                                          mean_abs_d_delay_vh=round(g.d_delay_vh.abs().mean(), 3),
                                          p95_abs=round(g.d_delay_vh.abs().quantile(0.95), 3),
                                          median_max_abs_dN=float(g.max_abs_dN.median()))
                              for X, g in pl.groupby("X")}
    # ------------------------------------------------------------- tail risk (ambulance late) with exact CIs
    tail = []
    for (X, rho, p), g in df.groupby(["X", "rho", "policy"]):
        thr = 300.0
        k = int((g.amb_tt > thr).sum())
        lo, hi = clopper_pearson(k, len(g))
        tail.append(dict(X=X, rho=rho, policy=p, threshold_s=thr, late=k, n=len(g), p_hat=k / len(g), cp_lo=lo, cp_hi=hi))
    pd.DataFrame(tail).round(4).to_csv(TAB / "tail_risk.csv", index=False)
    # ------------------------------------------------------------- VOI
    if (RES / "voi_runs.csv").exists():
        v = pd.read_csv(RES / "voi_runs.csv")
        v = v[v.policy == "P3"]
        voi = {}
        for X, g in v.groupby("X"):
            a = g[~g.perfect].set_index("rep").amb_tt
            b = g[g.perfect].set_index("rep").amb_tt.loc[a.index]
            m, lo, hi = paired_ci((a - b).values)
            voi[str(X)] = dict(noisy_mean=round(a.mean(), 1), perfect_mean=round(b.mean(), 1),
                               value_of_perfect_info_s=[round(m, 2), round(lo, 2), round(hi, 2)])
        summary["value_of_information"] = voi
    # ------------------------------------------------------------- explanatory regression of the delay cost
    sub = df[(df.policy == "P3") & (df.rho == 0.0)]
    summary["d_delay_by_incident"] = {str(k): round(g.d_delay_vh.mean(), 3) for k, g in sub.groupby("incident")}
    summary["d_amb_by_origin_P3_X0.9"] = {o: round(g.amb_tt.mean(), 1) for o, g in df[(df.policy == "P3") & (df.X == 0.9) & (df.rho == 0)].groupby("origin")}
    # ------------------------------------------------------------- pairwise policy contrasts (same replications)
    contrasts = []
    for (X, rho), g in df.groupby(["X", "rho"]):
        piv_t = g.pivot(index="rep", columns="policy", values="amb_tt")
        piv_d = g.pivot(index="rep", columns="policy", values="delay_vh")
        for a, b in (("P2", "P1"), ("P3", "P2"), ("P3C", "P3"), ("P4", "P3C")):
            mt, lt, ht = paired_ci((piv_t[a] - piv_t[b]).values)
            md, ld, hd = paired_ci((piv_d[a] - piv_d[b]).values)
            contrasts.append(dict(X=X, rho=rho, contrast=f"{a}-{b}", d_amb=mt, d_amb_lo=lt, d_amb_hi=ht,
                                  d_delay_vh=md, d_delay_lo=ld, d_delay_hi=hd))
    C = pd.DataFrame(contrasts).round(3)
    C.to_csv(TAB / "policy_contrasts.csv", index=False)
    summary["contrasts"] = C.to_dict(orient="records")
    # ------------------------------------------------------------- ensemble recovery (the per-run version is ill-posed: chaos)
    z = np.load(RES / "eval_dN_curves.npz")
    rec = {}
    for key in z.files:
        y = pd.Series(z[key]).rolling(60, center=True, min_periods=1).mean().values
        peak = np.nanmax(y)
        if peak <= 0.5:
            continue
        ipk = int(np.nanargmax(y))
        above = np.nonzero(y[ipk:] > 0.1 * peak)[0]
        rec[key] = dict(peak_extra_veh=round(float(peak), 2), t_peak_after_dispatch_s=ipk - 60,
                        t_recover_to_10pct_s=int(ipk + above[-1] - 60) if len(above) else None,
                        censored=bool(len(above) and ipk + above[-1] >= len(y) - 31))
    summary["ensemble_recovery"] = rec
    summary["per_run_recovery_censored_frac"] = float(df[df.policy != "P0"].recovery_censored.mean())
    # ------------------------------------------------------------- exchange rate and 1/(1-X) scaling of the cost
    ex = {}
    for (X, rho), g in T[T.policy == "P2"].groupby(["X", "rho"]):
        r = g.iloc[0]
        ex[f"X={X},rho={rho}"] = round(3600 * r.d_delay_mean / -r.d_amb_mean, 1)
    summary["vehicle_seconds_per_ambulance_second_P2"] = ex
    sub = T[(T.policy == "P2") & (T.rho == 0.0)]
    xx, yy = 1 / (1 - sub.X.values), sub.d_delay_mean.values
    slope = float((xx * yy).sum() / (xx * xx).sum())
    resid = yy - slope * xx
    summary["cost_scaling_fit_P2"] = dict(model="d_delay_vh = k/(1-X)", k=round(slope, 4),
                                          r2=round(1 - (resid ** 2).sum() / ((yy - yy.mean()) ** 2).sum(), 3),
                                          points=[dict(X=float(a), obs=round(float(b), 3), fit=round(float(slope / (1 - a)), 3)) for a, b in zip(sub.X, yy)])
    base = df[df.policy == "P0"]
    summary["baseline_delay_vh_in_window"] = {str(X): round(g.delay_vh.mean(), 1) for X, g in base.groupby("X")}
    for f in ("tuned_parameters.json", "v7_vs_v8_baseline.json", "verification.json"):
        if (RES / f).exists():
            summary[f.replace(".json", "")] = json.load(open(RES / f))
    json.dump(summary, open(RES / "summary.json", "w"), indent=2, default=float)
    figures(df, T, summary)
    print(json.dumps(summary["headline"], indent=1)[:3000])


def figures(df, T, summary):
    Xs = sorted(T.X.unique())
    # F1 ambulance travel time vs X
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, rho in zip(axes, (0.0, 0.5)):
        for p in POL:
            s = T[(T.rho == rho) & (T.policy == p)].sort_values("X")
            ax.plot(s.X, s.amb_mean, color=COLOR[p], marker="o", ms=5, label=POL_LABEL[p])
        ax.set_title(f"{'no yielding' if rho == 0 else 'partial yielding (rho = 0.5)'}", color=INK, fontsize=10, loc="left")
        ax.set_xlabel("design degree of saturation X (critical junction)")
    axes[0].set_ylabel("mean ambulance travel time (s)")
    axes[1].legend(fontsize=8, loc="upper left")
    fig.suptitle("Ambulance travel time by policy and network load (200 held-out replications per point)", x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, "F1_ambulance_time_vs_X.png")

    # F2 ordinary delay change with CI and placebo band
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    pl = summary.get("placebo", {})
    for ax, rho in zip(axes, (0.0, 0.5)):
        if pl:
            px = sorted(float(k) for k in pl)
            band = [1.96 * pl[str(x)]["sd_d_delay_vh"] / np.sqrt(summary["reps_per_cell"]) for x in px]
            ax.fill_between(px, [-b for b in band], band, color=GRID, alpha=0.9, lw=0, label="placebo: 1 s signal nudge (95% band of a 200-rep mean)")
        for i, p in enumerate(POL[1:]):
            s = T[(T.rho == rho) & (T.policy == p)].sort_values("X")
            off = (i - 2) * 0.004
            ax.errorbar(s.X + off, s.d_delay_mean, yerr=[s.d_delay_mean - s.d_delay_lo, s.d_delay_hi - s.d_delay_mean],
                        color=COLOR[p], marker="o", ms=5, capsize=3, lw=1.6, label=POL_LABEL[p])
        ax.axhline(0, color=INK2, lw=1)
        ax.set_title(f"{'no yielding' if rho == 0 else 'partial yielding (rho = 0.5)'}", color=INK, fontsize=10, loc="left")
        ax.set_xlabel("design degree of saturation X")
    axes[0].set_ylabel("change in ordinary vehicle-hours vs P0\n(paired mean, 95% bootstrap CI)")
    axes[1].legend(fontsize=8, loc="upper left")
    fig.suptitle("Network cost of one prioritised mission", x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, "F2_network_delay_cost_vs_X.png")

    # F3 cumulative extra vehicle-hours since dispatch (plateau = recovered)
    z = np.load(RES / "eval_dN_curves.npz")
    t = np.arange(-60, 2000)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), sharey=True)
    for p in POL[1:]:
        key = f"0.9|0.0|{p}"
        y = np.nancumsum(np.where(t >= 0, z[key], 0)) / 3600
        axes[0].plot(t, y, color=COLOR[p], lw=1.8, label=POL_LABEL[p])
    axes[0].set_title("all policies, X = 0.9", loc="left", fontsize=10, color=INK)
    for i, X in enumerate((0.7, 0.8, 0.85, 0.9, 0.95)):
        key = f"{X}|0.0|P2"
        y = np.nancumsum(np.where(t >= 0, z[key], 0)) / 3600
        axes[1].plot(t, y, color=SERIES[i], lw=1.8, label=f"X = {X}")
    axes[1].set_title("P2 preempt + skip, by load", loc="left", fontsize=10, color=INK)
    for ax in axes:
        ax.axhline(0, color=INK2, lw=1)
        ax.set_xlabel("seconds since ambulance dispatch")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("cumulative extra ordinary\nvehicle-hours vs P0 (mean)")
    fig.suptitle("Where the network cost accrues: a plateau means the disturbance has been absorbed (no yielding, 200 reps)",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    save(fig, "F3_cumulative_cost_after_dispatch.png")

    # F4 trade-off: seconds saved vs vehicle-hours
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for p in POL[1:]:
        s = T[(T.rho == 0.0) & (T.policy == p)].sort_values("X")
        ax.plot(-s.d_amb_mean, s.d_delay_mean, color=COLOR[p], marker="o", ms=5, label=POL_LABEL[p])
        last = s.iloc[-1]
        ax.annotate(f"X={last.X}", (-last.d_amb_mean, last.d_delay_mean), fontsize=7, color=INK2,
                    xytext=(4, 4), textcoords="offset points")
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xlabel("ambulance seconds saved vs P0 (mean)")
    ax.set_ylabel("extra ordinary vehicle-hours (mean)")
    ax.legend(fontsize=8)
    ax.set_title("Benefit-cost frontier across load levels (no yielding)", loc="left", fontsize=11, color=INK)
    save(fig, "F4_tradeoff_frontier.png")

    # F5 baseline v7 vs v8
    if (RES / "baseline_N_v7_random_plan_pure_fixed_time.npy").exists():
        fig, ax = plt.subplots(figsize=(8, 3.6))
        for name, c, lab in (("v7_random_plan_pure_fixed_time", SERIES[1], "v7 signal plan, fixed-time (as specified)"),
                             ("v8_webster_plan_pure_fixed_time", SERIES[0], "v8 Webster plan, fixed-time"),
                             ("v7_random_plan", SERIES[2], "v7 plan + v8 wait guard")):
            y = np.load(RES / f"baseline_N_{name}.npy")
            ax.plot(np.arange(len(y)) / 60, y, color=c, label=lab, lw=1.8)
        ax.set_xlabel("time (min)")
        ax.set_ylabel("vehicles in system\n(mean of 20 replications)")
        ax.set_title("Identical demand, different baseline control (no ambulance)", loc="left", fontsize=11, color=INK)
        ax.legend(fontsize=8)
        save(fig, "F5_v7_vs_v8_baseline.png")

    # F6 verification
    ver = summary.get("verification", {})
    if "T3_webster_validation" in ver:
        fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
        w = ver["T3_webster_validation"]["rows"]
        axes[0].plot([r["X"] for r in w], [r["webster_s"] for r in w], color=SERIES[1], marker="s", label="Webster (1958) formula")
        axes[0].plot([r["X"] for r in w], [r["sim_delay_s"] for r in w], color=SERIES[0], marker="o", label="simulator")
        axes[0].set_xlabel("degree of saturation X"); axes[0].set_ylabel("mean delay per vehicle (s)")
        axes[0].set_title("Isolated junction delay", loc="left", fontsize=10, color=INK); axes[0].legend(fontsize=8)
        c = ver["T4_priority_cost_vs_fluid_model"]["rows"]
        axes[1].plot([r["X"] for r in c], [r["fluid_extra_veh_s"] for r in c], color=SERIES[1], marker="s", label="independent fluid model")
        axes[1].plot([r["X"] for r in c], [r["sim_extra_veh_s"] for r in c], color=SERIES[0], marker="o", label="simulator")
        axes[1].plot([r["X"] for r in c], [r["closed_form_veh_s"] for r in c], color=SERIES[2], marker="^", ls="--", label="closed form (upper approx.)")
        axes[1].set_xlabel("degree of saturation X"); axes[1].set_ylabel("extra delay from 10 s lost green (veh·s)")
        axes[1].set_title("Cost of lost green", loc="left", fontsize=10, color=INK); axes[1].legend(fontsize=8)
        save(fig, "F6_verification.png")

    # F7 protections
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9))
    s0 = T[(T.rho == 0.0) & (T.policy == "P0")].sort_values("X")
    axes[0].plot(s0.X, s0.n_wait_over_mean, color=COLOR["P0"], marker="o", ms=5)
    axes[0].set_yscale("log")
    axes[0].set_title("baseline P0: vehicles waiting > 180 s per run", loc="left", fontsize=10, color=INK)
    axes[0].set_xlabel("design degree of saturation X")
    for p in POL[1:]:
        s1 = T[(T.rho == 0.0) & (T.policy == p)].sort_values("X")
        axes[1].plot(s1.X, s1.d_wait_over_mean, color=COLOR[p], marker="o", ms=5, label=POL_LABEL[p])
    axes[1].axhline(0, color=INK2, lw=1)
    axes[1].set_title("extra over-cap waits caused by priority (paired mean)", loc="left", fontsize=10, color=INK)
    axes[1].set_xlabel("design degree of saturation X")
    axes[1].legend(fontsize=8)
    fig.suptitle("The 180 s wait cap is infeasible for the baseline itself above X ~ 0.8 (no yielding)",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    save(fig, "F7_wait_cap_breaches.png")

if __name__ == "__main__":
    main()
