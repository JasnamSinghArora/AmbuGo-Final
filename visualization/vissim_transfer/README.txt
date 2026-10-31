AMBUGO — PREPARATION FOR A GENUINE PTV VISSIM SIMULATION

STATUS: NOT YET RUN OR VALIDATED IN PTV VISSIM.

The current computer is an Apple Silicon Mac. No Vissim installation or editable
Vissim project was found in the application folders, workspace or Desktop that
were checked. Running the requested simulation requires access to a supported
Windows installation of PTV Vissim with the relevant license and interfaces.
The screenshots in the shared chat are visual references, not editable models.

This folder prepares the existing Mohali scenario for transfer. It does not
contain a completed INPX project, a tested Vissim controller, or Vissim results.
Existing SUMO travel times and queue costs must not be presented as Vissim output.

CONTENTS
- geometry/: OpenDRIVE export, export method, source network and validation evidence.
- scenario/: the frozen desired demand, scenario design, source vehicle types,
  source road metadata and B1000 controller settings used by the existing films.
- scenario/desired_vehicle_schedule.csv: 411 ordinary vehicles and 3 ambulance
  dispatches; these are desired departures, not guaranteed insertion times.
- TRANSFER_STATUS.json: what is ready and what still requires the Vissim runtime.

NATIVE VISSIM WORKFLOW
1. Verify the installed Vissim version, license and COM/API availability.
   The ordinary unlicensed demo disables COM, saving, evaluations and AVI export;
   a demo installation alone is not sufficient for this automation workflow.
2. Import the exported network through File > Import > OpenDRIVE. Select the
   appropriate left-hand-traffic interpretation for the documented export variant.
   Save an actual Vissim INPX project from inside Vissim.
3. Inspect the imported geometry, turn connectors, lane directions, lengths,
   coordinates, hospital approach and PCL Chowk. Import success is not proof of
   topological or behavioral equivalence. Record a source-edge-to-Vissim-link map.
4. Rebuild the seven modeled controllers, signal groups, stop lines, conflicting
   movements, pedestrian clearance, amber and all-red intervals. These source
   timings are assumptions, not measured Mohali signal plans.
5. Configure vehicle classes and demand. Do not copy SUMO's car-following
   parameters into Vissim as though they were equivalent: calibrate the chosen
   Vissim behavior model separately. Preserve desired departures and record any
   insertion delay. Verify every route's connectivity in the imported network.
6. Connect AmbuGo's route/priority planner to live Vissim observations using the
   installed interface documentation. Preserve the burden admission gate,
   receiving-space checks, request leases, route hysteresis and progress guard.
   Route and signal changes must affect the running Vissim simulation. Record
   observations, forecasts, requests, actual phases and vehicle trajectories.
7. Make the signal controller enforce clearance and conflicting-movement
   constraints at every simulation step. An admitted request is not immediate
   green. Do not bypass intergreens to make the video look more responsive.
8. Run a no-priority baseline and AmbuGo using matched network, demand and behavior
   settings. Vissim produces new trajectories and results; it need not reproduce
   the old SUMO times or the original 913/1000 example.
9. Validate vehicle conservation, route continuity, lane use, signal conflicts,
   queue discharge and the distinction between requested and actual departure.
   Compare ambulance travel time, ordinary waiting, spillback and recovery over
   multiple seeds. One illustrative clip is not field-performance validation.
10. Record the native Vissim view at PCL Chowk: one stable, close intersection
    view, detailed lanes, individually visible traffic and a distinct ambulance.
    Use brief labels connected to the relevant queues and the real decision log.
    Export graph data from this new run and synchronize any separate graph film.

SCOPE AND ATTRIBUTION
Road geometry is derived from OpenStreetMap with documented project corrections.
Demand, traffic composition, signal timing and sensor errors are synthetic.
The hospital goal is a modeled road approach, not a surveyed emergency entrance.
© OpenStreetMap contributors; ODbL 1.0:
https://www.openstreetmap.org/copyright
https://opendatacommons.org/licenses/odbl/1-0/
This is not a copy of the unrelated example intersection pictured on PTV's site.

OFFICIAL PTV REFERENCES
OpenDRIVE import and required post-import checks:
https://cgi.ptvgroup.com/vision-help/VISSIM_2026_EN-DE/en-us/Content/5_Netzbearbeiten/Import_openDRIVE-imp.htm
Unlicensed demo limitations:
https://cgi.ptvgroup.com/vision-help/LicenseMgt_ENG/Content/License-mgt/Demo-version-info.htm
Product integration overview:
https://www.ptvgroup.com/en/products/ptv-vissim/faqs

TRANSFER CHECK RESULT
The direction-preserving candidate retains 479 roads and 556 regular lanes. Twelve
invalid boundary predecessor references were repaired against the source network.
Road/lane geometry is unchanged by that repair. Native Vissim import has not been
performed. Export warnings and geometry reconstruction differences still require
inspection in Vissim; see geometry/README.txt.
