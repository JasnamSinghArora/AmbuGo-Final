# AmbuGo v8 — ambulance signal priority in a mixed-traffic synthetic district

v8 turns the v7 *input fixture* into a complete, verified, reproducible research
pipeline: data generator → mesoscopic simulator → priority controllers → verification suite →
pre-registered paired experiment → statistics and figures.

**Everything is synthetic.** No city, field trip or measured intervention is represented.
Results are statements about this model, under declared assumptions (see `REPORT.md` §8).

## Quick start (Python ≥ 3.10, numpy, scipy, pandas, matplotlib)

```bash
python3 tests/run_tests.py                     # 8 verification checks -> results/verification.json
python3 scripts/run_experiments.py T           # tune on TRAINING replications 5000-5039
python3 scripts/run_experiments.py B           # v7 vs v8 baseline at identical demand
python3 scripts/run_experiments.py E --reps 200   # held-out evaluation, 14,400 paired runs (~15 min on 2 cores)
python3 scripts/run_experiments.py V --reps 200   # value of perfect information
python3 scripts/run_experiments.py N --reps 150   # placebo / chaos noise floor
python3 scripts/analyze.py                     # tables, figures, results/summary.json
python3 scripts/generate_fixture.py --x 0.85 --rep 0   # export a public/hidden data fixture
```

## Layout

| Path | Contents |
|---|---|
| `ambugo/rng.py` | SHA-256 namespaced random streams (design, demand, incident, sensor, yield, ambulance) |
| `ambugo/network.py` | network, vehicle classes (PCU), route enumeration |
| `ambugo/design.py` | OD model, logit route sets, demand calibrated to target X, Webster signal plans |
| `ambugo/scenario.py` | one replication: AR(1)-modulated Poisson demand, incident, ambulance mission |
| `ambugo/sim.py` | 1 s spatial-queue simulator with spillback, signals, sensors, yielding |
| `ambugo/policies.py` | base controller with wait guard (P0) and priority policies P1–P4 |
| `ambugo/stats.py` | paired bootstrap, sign-flip test, Holm, Clopper–Pearson, CVaR |
| `tests/run_tests.py` | reproducibility, invariants, Webster validation, fluid-model check, leakage check |
| `scripts/` | experiment pipeline, analysis, fixture export |
| `geometry/` | v7 network geometry (unchanged) |
| `data/fixture_X0.85_rep0/` | example exported fixture (public/ vs hidden/) |
| `results/` | raw run CSVs, tables, figures, summary.json, verification.json |
| `REPORT.md` | full write-up |
