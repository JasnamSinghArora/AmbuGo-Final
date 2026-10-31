AMBUGO — OPTIONAL FULL SIMULATION REPRODUCTION

This folder reproduces the two numerical episodes used by the 20-second videos.
The main package can rerender the stored replays without running SUMO. This
folder instead reruns the traffic simulation, route planning and signal control.

EXACT EPISODES

* B1000: the recorded P3 controller with a 1,000 vehicle-second admission budget,
  epsilon zero, actions (0,0) and (30,60), and the 20-second progress guard.
  The focused ambulance is a002, the third mission. Its travel time is 323.5 s.
* P0: matched traffic-aware routing without signal priority. The same ambulance
  takes 516.5 s in this episode. All three missions and ordinary demand are shared.

The package data/replays/P3.npz is the B1000 sensitivity episode, not the default
10,000-budget episode. These are illustrative synthetic traffic conditions on
real mapped roads. They do not establish field effectiveness or global optimality.

QUICK START

From the package root, using CPython 3.12 in a fresh virtual environment:

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -r simulation/requirements.txt
    python simulation/run.py --smoke
    python simulation/run.py --case all

On Windows, activate with .venv\Scripts\activate instead of the source command.
The scripts use pathlib and no workspace-specific runtime paths.

Always use run.py for these episodes. Calling run_punjab.py directly uses the
adapter's default 10,000 budget and does not reproduce the video's B1000 case.

The smoke test advances the exact input network and traffic for 10 simulation
seconds using the actual controller interface. It does not test an ambulance
mission. The full command runs both 1,800-second episodes and verifies every
stored numerical array against data/replays. On the original machine each full
episode took about 2.5 seconds, excluding environment installation.

Outputs go into simulation/reruns/P0 and simulation/reruns/B1000. Shipped replays
are not overwritten. Use --output PATH to choose another destination, or --case
P0 / --case B1000 to run one episode. --reference-dir can point to another folder
containing the expected P0.npz and P3.npz files.

INTERNAL CONNECTOR GEOMETRY

    python simulation/build_connectors.py

This regenerates simulation/reruns/connectors.json and compares it with the
shipped data/connectors.json. It reads the exact network's XML connections and
via-lane shapes, retaining XML order and duplicate options. libsumo converts
each lane coordinate to longitude/latitude. No simulation step is advanced.
The verified result has 878 from-edge|to-edge keys and 955 connector options.

DEPENDENCIES AND DETERMINISM

The recorded and verified environment used:

    Python 3.12.14; macOS 26.5.2; Apple Silicon
    SUMO / libsumo / sumolib / traci / sumo-data / eclipse-sumo 1.28.0
    NumPy 2.5.4; NetworkX 3.7

requirements.txt pins these simulation packages. The libsumo backend is required;
it runs SUMO in-process and uses the supplied network directly. No network fetch,
Google Maps access, geocoding request or OSM download occurs during simulation.

The random seed is 19. The same frozen demand file contains 411 ordinary vehicles
and three ambulance dispatches at simulation times 600, 660 and 760. Route-pool
selection, traffic types, observation noise and dropout use the original seeded
logic. Generated demand must match the shipped SHA-256 before simulation starts.

Different simulator, NumPy, NetworkX, Python or projection-library builds can
change tie breaking, floating-point behavior, vehicle motion or geometry. The
runner reports versions, compares all arrays exactly (NaNs treated equally),
and fails verification when differences appear. Do not assume a different
environment is identical because arrival times alone look similar. The shipped
replays remain the authoritative data for faithfully rerendering the videos.

JSON and NPZ file bytes need not match: output paths, runtime durations, JSON
ordering and archive metadata can change. Verification compares numerical arrays,
mission outcomes, plans, guard events, ordinary-vehicle events and decision logs.
Instrumentation event order is normalized by time and ambulance for comparison.

WHAT IS INCLUDED

run.py                     Portable launcher and numerical verification.
run_punjab.py              Actual real-road adapter, with portable path discovery.
instrumentation.py        Original read-only ExplainedController class body.
upstream/sumo_study.py     Byte-identical frozen v9 controller module.
inputs/mohali_urban.net.xml Exact corrected, capped network used for both episodes.
inputs/demand.rou.xml      Exact frozen desired vehicle arrivals and initial routes.
inputs/config.json         Same numerical scenario settings with portable metadata.
inputs/scenario.json       Frozen route pool, missions and modeled signal design.
reference/                Captured outcomes, ordinary events and B1000 decisions.
provenance/               Original sources, source hashes and geometry correction.
checks/                   Verified smoke, full-reproduction and connector reports.

The upstream module is retained intact so its original hash and methods can be
checked. This adapter uses DEFAULTS, stable_rng, green_split, Signal and Controller.
Its unrelated synthetic-district fixture utilities are not called. No v7 fixture
dataset, study outputs, package vendor tree or external repository is required.

PORTABILITY EDITS

Only module/output path discovery and the libsumo command-line executable token
changed in run_punjab.py. The original file is included in provenance. The entire
ExplainedController class body is copied from the instrumentation source; run.py
replaces its workspace-specific entry point. Numerical traffic and control logic
are preserved. Adapter-file hashes therefore differ from the historical file,
while the frozen controller, network and demand hashes remain exact.

The package test reproduced both full episodes with every stored numerical array
equal, plus identical mission/route/control/ordinary-event outcomes. B1000's
candidate decisions and request explanations also matched. See checks/ for the
machine-readable verification evidence and recorded environment.

GEOMETRY, DATA ASSUMPTIONS AND ATTRIBUTION

Road data are derived from © OpenStreetMap contributors, available under the
Open Database License. Attribution and license information:
https://www.openstreetmap.org/copyright
https://opendatacommons.org/licenses/odbl/1-0/

This is a 479-directed-link major-road subset with seven modeled controllers.
Most lane counts and speeds are modeled defaults, with a 50 km/h upper cap;
traffic counts, demand, sensor errors and signal plans are synthetic assumptions.
The hospital goal is a mapped road approach, not a surveyed emergency entrance.

The Fortis-area junction was physically corrected because the source OSM geometry
cut across a traffic island visible in Esri imagery. Six clockwise circulating
arcs were inserted in the network before every policy was simulated. The assumed
centerline radius is 17.5 m; lane width 3.2 m; circulation speed 20 km/h; estimated
digitization uncertainty is ±2 m. Imagery acquisition date is unknown. This is
not a survey. See provenance/roundabout_patch.json and alignment_audit.json.

Correction reference imagery attribution: Esri, Vantor, Earthstar Geographics,
and the GIS User Community. The imagery itself is not needed or included here.
The final video basemap is a separate Google Maps capture handled by the main
rendering package; it does not influence these simulated positions or decisions.

LIMITS OF THE EXAMPLE

The admission burden is an unvalidated forecast proxy. The focused ambulance's
request is refused at 785–791, admitted at 792, and its approach first appears
green at 796.5. Its guard escalates at 851. Genuine route changes affect the
hospital approach. The final observed ordinary traffic service does not prove
that all aftereffects disappear or that the selected policy minimizes measured
network harm. All network comparisons include the other two ambulance missions.
