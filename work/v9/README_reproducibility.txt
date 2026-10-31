AmbuGo first draft reproducibility package version 9

This package contains synthetic traffic experiments, their source, generated
inputs, raw outputs, statistical analysis, verification evidence, figures and
paper text. It contains no measured-city calibration dataset. Original supplied
v8 outcomes and the mechanically corrected outcomes are kept in separate folders.

The microscopic main experiment contains 1,728 policy runs. Secondary batches
contain 72 smaller-step runs, 48 progress-guard ablation runs, 72 adaptive-base
runs and 72 noiseless-count runs: 1,992 microscopic evaluation/secondary runs in
all. Development records and both model versions are retained separately. The
corrected mesoscopic evaluation contains 14,400 new policy runs. Those counts
refer to policy runs, not independent ambulances or independent scenario seeds.

1 Extract and verify

Extract the ZIP and open a terminal in the directory containing this README,
MANIFEST.json, outputs/ and work/. Keep this relative layout intact. The
manifest verifier uses only the Python standard library:

    python3 verify_zip.py --directory .

To verify the ZIP before extracting it, run the copy of verify_zip.py against
its archive path. Optional fresh extraction into a new directory is supported:

    python3 verify_zip.py PATH_TO_ZIP --extract NEW_EMPTY_DIRECTORY

Every listed file is checked against its recorded SHA256 and byte count. These
checks detect corruption and accidental changes; they are not a digital
signature establishing authorship. Verify before rerunning analyses that write
new outputs. Execution times, timestamps, font rendering and some platform-level
numerical behavior can differ even when the method is reproduced correctly.

2 Install the local runtime

Python 3.12 and platform-compatible SUMO wheels are recommended. A local virtual
environment keeps the selected Python interpreter separate from other projects:

    python3.12 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install --target work/v9/vendor -r requirements.txt
    export PYTHONPATH="$PWD/work/v9/vendor${PYTHONPATH:+:$PYTHONPATH}"
    export MPLCONFIGDIR="$PWD/work/v9/mpl_cache"

The --target installation is REQUIRED for the frozen traffic source. Its SUMO
and netconvert executable paths are work/v9/vendor/sumo/bin/sumo and netconvert;
installing packages only into the virtual environment's ordinary site-packages
will not populate those paths. PYTHONPATH is needed by some standalone analysis
and inherited mesoscopic scripts that do not insert the target themselves.
Windows users should use their environment's activation and environment-variable
syntax. Successful microscopic execution requires platform-compatible binary
wheels; the package does not contain the author's macOS binaries.

Versions used in this study are pinned in requirements.txt. The archive excludes
vendor/, compiler tools, document-rendering runtimes, font caches and temporary
files. The frozen model hash is recorded in work/v9/sumo_frozen_source.json and
in each experiment protocol. Do not patch that source to relocate the package.

3 Fast checks and analysis regeneration

The following commands use existing raw data rather than rerunning the full
microscopic experiment:

    python work/v9/analysis.py --self-check
    python work/v9/meso_checks.py --out meso_verification_rerun.json
    python work/v9/audit_v8_statistics.py
    python work/v9/analyze_corrected.py
    python work/v9/analyze_sumo.py
    python work/v9/make_base_figures.py

The mesoscopic verification command executes small independent synthetic
verification cases. It is not a calibrated traffic-performance experiment.
Additional included figure/robustness-analysis scripts may regenerate their
respective saved summaries. The principal figure inputs and statistical outputs
are also supplied, so reading the paper does not require traffic reruns.

The source manuscript text is in work/v9/paper_*.txt, with references and figure
captions alongside it. If final manuscript files were supplied during packaging,
they are in manuscript/. Paper authoring scripts are retained as source. Optional DOCX regeneration is:

    python -m pip install --target work/v9/vendor -r requirements-document.txt
    python work/v9/build_paper.py

The manuscript can then be exported to PDF with a Word-compatible processor.
Exact pagination can vary across fonts and document-processing applications.
The provided final PDF is available without installing an authoring environment.

4 Reproduce the original source checks and a stratified subset

    python work/v9/teammate_v8/ambugo_v8/tests/run_tests.py
    python work/v9/v8_regression_checks.py
    python work/v9/reproduce_v8.py

The original test suite reports eight passing checks. The separate adversarial
regression program is EXPECTED to detect the documented original ambulance
storage/capacity exceptions and incomplete wait measurement. Its detections are
not evidence that the corrected variant should preserve those behaviors.
reproduce_v8.py reruns all six policies at all six load levels and both yielding
conditions for seeds 0, 37 and 199: 216 policy runs. It compares the checked
metrics against the supplied original raw rows. This numerical reproduction does
not establish physical validity.

5 Reproduce the mechanically corrected mesoscopic evaluation

    python work/v9/v8_corrected/tests/mechanical_checks.py
    python work/v9/v8_corrected/scripts/run_experiments.py E --reps 200 --procs 4
    python work/v9/analyze_corrected.py

The 18 correction checks address shared source admission, strict storage,
ambulance PCU discharge and conservation under stress. The full evaluation holds
the original tuned parameter choices fixed and produces 14,400 policy runs.
Original and corrected `ambugo` modules have the same Python package name;
run them in separate Python processes as shown, rather than importing both into
one process. The manifest records the correction patch and its source hashes.
The independent 24-check mesoscopic reference has a different verification role
and is not substituted for either of these models' comparative outcomes.

Mesoscopic labels M0, M1, M2, MQ, MC and MR correspond to executable keys P0,
P1, P2, P3, P3C and P4. Microscopic P0-P3 refer to separately defined controllers;
the matching code numbers do not make them identical methods.

6 Reproduce the frozen microscopic evaluation and secondary batches

Use a separate extraction for expensive reruns if you wish to retain the
original archived outputs unchanged. The archived selected_policy.json is the
locked configuration consumed by these commands. Do not retune first.

    python work/v9/run_sumo_batch.py main --workers 4
    python work/v9/run_sumo_batch.py sensitivity --workers 4
    python work/v9/run_sumo_batch.py ablation --workers 4
    python work/v9/run_sumo_robustness.py adaptive_base --workers 4
    python work/v9/run_sumo_robustness.py exact_counts --workers 4
    python work/v9/analyze_sumo.py

All conditions share their designated seed's ordinary scenario and mission
schedule across policy comparisons. Multiple missions within an episode are
clustered; analyses resample seed blocks. The primary physical step is 0.5 s
and the smaller-step sensitivity uses 0.25 s, while control decisions remain on
the integer-second grid. The adaptive baseline selects the largest observed approach vehicle count
(including moving and queued vehicles), rather than downstream max-pressure. The noiseless-count secondary condition
removes count noise and receipt delay and samples every second, while retaining
the specified availability mechanism; it is not full hidden-state information.

Protocols, scalar raw JSON, compressed population traces and individual ordinary
release/insertion/completion event CSVs are retained in each sumo_* evaluation
folder. The event files support the restricted-residence identity and the
individual positive/negative residence decomposition. All unfinished missions
and ordinary trips remain represented. Integration, controller and complete-run
wall times have the scopes documented in the paper; they are machine-specific.

7 Replay both development stages without overwriting frozen evidence

The optional helper creates a new replay project under replays/ and links to
your locally installed runtime. It does not change the frozen evaluation source
or selected configuration in this extraction:

    python work/v9/replay_training.py initial --workers 4
    python work/v9/replay_training.py progress --workers 4

The initial replay uses the archived sumo_study_initial.py version and executes
the first training grid followed by its selector. The progress replay uses the
final model, executes train_progress and applies the progress-stage selector.
Both create their own inputs, outputs, source hash and selected configuration.
Use --output NEW_DIRECTORY to choose a different fresh destination. If runtime
directory links are unavailable, --copy-vendor copies the already installed
runtime into that replay project. Dependency binaries are not copied into the
provided ZIP. Development records and protocols in the archive remain the
historical evidence; rerun timestamps and wall times will differ.

8 Scenario paths and archived evidence

The four required v7 fixture CSVs are staged under
outputs/AmbuGo_v7_Synthetic_Data/: nodes.csv, edges.csv, vehicle_classes.csv and
od_probabilities.csv. They are the original schema consumed by the frozen code;
the v8 exported public CSVs have different columns and cannot replace them.

The active work/v9/scenarios cache is intentionally absent. Cached scenario JSON
contains absolute route-file paths. On extraction, the generator therefore
creates a new local active cache with the same specified random streams. Original
JSON and route XML are preserved separately in work/v9/archived_scenarios/.
Do not copy those JSON files into the active cache unchanged. Generated network
XML and its input geometry XML are in work/v9/sumo_network/.

Raw results preserve recorded trace_file absolute paths as provenance. They are
not needed by the aggregate scalar analyses. PORTABLE_PATH_INDEX.json maps each
recorded path to its actual package-relative trace or archived-route path. Use
that index to open traces from this extraction rather than relying on a former
machine path. The raw hashed evidentiary records have not been silently rewritten.

9 Optional short extraction smoke test

After installing dependencies, the verifier can execute one short microscopic
case using a fresh scenario cache and temporary result folder:

    python verify_zip.py --directory . --smoke

This checks fixture discovery, local binary paths, source insertion, signal
execution and the population/residence identities for a 180 s numerical case.
An ambulance need not finish within such a short horizon. Passing is a software
portability check rather than traffic validation or another effectiveness result.

10 Package rebuild

The authoring build program refuses to package incomplete named simulation
batches, verifies the frozen source hash, includes all main and secondary raw
traces/event files, excludes vendor binaries, writes a manifest and verifies the
resulting ZIP. It must be run only after all study and secondary batches finish:

    python work/v9/build_package.py --simulations-final

Optional --paper PATH arguments can explicitly stage final PDF/DOCX files.
The build produces outputs/AmbuGo_First_Draft_Reproducibility_v9.zip and a small
build summary. No source code or original traffic result is modified by building.
