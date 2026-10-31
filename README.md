# AmbuGo

Joint ambulance routing and selective traffic signal priority, evaluated in a synthetic traffic network.

The controller scores route–priority combinations, keeps candidates within a predicted travel-time allowance, and selects the one with the lowest estimated traffic burden. Signal changes respect minimum greens and clearance intervals. An ambulance that falls behind its free-flow progress switches to aggressive priority.

[Read the paper](paper/AmbuGo_Audited_Research_Paper.pdf) · [Reproduce the study](docs/reproduction.md) · [Animation source](visualization/README.md) · [Data and video downloads](https://github.com/JasnamSinghArora/AmbuGo-Final/releases/tag/v1.0.0)

## Results

The primary SUMO experiment contains 1,728 policy runs across 48 scenario seeds, three demand levels and three mission frequencies. The corrected mesoscopic experiment contains another 14,400 policy runs. Development and sensitivity runs are recorded separately.

| Policy | Balanced mean ambulance duration |
| --- | ---: |
| Routing alone (S0) | 401.57 s |
| Sequential routing and priority (SEQ) | 214.68 s |
| Aggressive joint control (JFAST) | 211.19 s |
| Selective joint control (JSEL) | 222.29 s |

Relative to JFAST, JSEL added 11.10 s of mean duration while reducing positive spatial occupancy exposure by 3.84 vehicle-hours. The respective 95% seed-block bootstrap intervals are 9.47–12.94 s and −4.73 to −2.95 vehicle-hours.

These are synthetic results. JSEL escalated to aggressive control in 51.6% of missions, and two journeys exceeded 30 minutes. The study does not establish global optimality, field performance or deployment readiness. The paper reports the difficult cases alongside the averages.

## Repository layout

| Directory | Contents |
| --- | --- |
| `work/v9/` | Frozen SUMO controller, experiment runners, analysis and retained results |
| `work/v9/teammate_v8/ambugo_v8/` | Original mesoscopic implementation and results |
| `work/v9/v8_corrected/` | Mechanical corrections, tests and corrected results |
| `outputs/AmbuGo_v7_Synthetic_Data/` | Network, vehicle-class and OD fixtures |
| `paper/` | Final PDF, editable manuscript, equations, bibliography and figure builder |
| `visualization/` | Map replay, evolving graphs, video composition and Vissim transfer files |
| `scripts/` | Repository checks |

The study's original relative paths are retained because the frozen implementation resolves its fixtures and SUMO binaries through them. Source files that produced the reported experiments are unchanged. Their hashes are checked before analysis.

Raw scalar records and mesoscopic CSVs are in Git. The full population traces, vehicle event files, scenario archive and video assets are attached to the [release](https://github.com/JasnamSinghArora/AmbuGo-Final/releases/tag/v1.0.0), keeping the checkout smaller. The research archive includes the earlier draft; `paper/` contains the final audited manuscript.

## Quick checks

Use Python 3.12. From the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-checks.txt
python scripts/check.py
```

These checks exercise the accounting identities, mechanical corrections, statistical utilities and retained experiment structure. They do not rerun the full traffic study.

## Run the study

The frozen source expects its SUMO installation in `work/v9/vendor/`:

```sh
python -m pip install --target work/v9/vendor -r requirements.txt
export PYTHONPATH="$PWD/work/v9/vendor${PYTHONPATH:+:$PYTHONPATH}"
export MPLCONFIGDIR="$PWD/work/v9/mpl_cache"

# Recompute summaries from the records included in this checkout.
python work/v9/analyze_corrected.py
python work/v9/analyze_sumo.py

# Rerun the primary microscopic experiment.
python work/v9/run_sumo_batch.py main --workers 4
```

Reruns write generated results. Use a separate checkout if you want to preserve the supplied outputs. See [the reproduction guide](docs/reproduction.md) for the complete experiment sequence, archive verification and platform notes.

## Paper and visualizations

The final paper is supplied as PDF and DOCX. To rebuild its editable document:

```sh
python -m pip install -r requirements-document.txt
python paper/build.py
```

To regenerate its results figure after installing the study dependencies:

```sh
python paper/plot_results.py
```

Export the DOCX to PDF with Word or LibreOffice. Pagination depends on installed fonts and the document processor.

The [visualization guide](visualization/README.md) covers the map replay and simultaneous graph animations. The Mohali demonstration is a separate synthetic example, not the paper's evaluation network. The Vissim folder contains transfer geometry and preparation notes; no Vissim experiment was run.

## Third-party material

SUMO and the Python dependencies are installed separately. Map-related files retain their Google Maps and OpenStreetMap attribution notices. Those notices do not grant a project-wide license for third-party imagery; see the `THIRD_PARTY_NOTICES.txt` files beside each visualization.
