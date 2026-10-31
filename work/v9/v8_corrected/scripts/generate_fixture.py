"""Export an AmbuGo v8 data fixture with a strict public / hidden split.

    python3 scripts/generate_fixture.py --x 0.85 --rep 0 --out data/fixture_X0.85_rep0

public/  depends ONLY on the design stream (geometry, Webster plans, OD model, route
         sets, sensor inventory, mission template).  Verified by tests: identical
         bytes for every replication index.
hidden/  plant truth for one replication: realised releases, latent shock,
         incidents, sensor outages, and the full simulated state at dispatch (a state
         actually reached by warm-up, replacing v7's static packed snapshot).
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ambugo.network import Network, CLASSES, MIN_GREEN, MAX_GREEN     # noqa: E402
from ambugo.design import Design                                     # noqa: E402
from ambugo.scenario import make_scenario, WARMUP_S                  # noqa: E402
from ambugo.sim import Simulator, SENSOR_PERIOD, P_AM, P_MA          # noqa: E402
from ambugo.policies import NoPriority                               # noqa: E402

PROV = "synthetic_design_not_measured"


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [dict(provenance=PROV, **r) for r in rows]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def export(X, rep, out):
    out = Path(out)
    net = Network.from_v7_geometry()
    d = Design(net, target_x=X)
    E = net.edges
    pub, hid = out / "public", out / "hidden"
    counts = {}
    counts["public/nodes.csv"] = write(pub / "nodes.csv", [dict(node_id=k, kind=v["kind"], x_m=v["x"], y_m=v["y"]) for k, v in net.nodes.items()])
    counts["public/edges.csv"] = write(pub / "edges.csv", [dict(edge_id=e["id"], from_node=e["u"], to_node=e["v"], length_m=e["L"], lanes=e["lanes"],
                                                                speed_limit_mps=e["vff"], saturation_flow_pcu_per_s=round(e["s"], 4),
                                                                storage_pcu=e["storage"], design_load_pcu_per_s=round(d.kappa * d.unit_load[i], 5))
                                                           for i, e in enumerate(E)])
    plans = []
    for j, p in d.plans.items():
        plans.append(dict(junction_id=j, cycle_s=p["cycle"], offset_s=p["offset"],
                          stage_kinds="|".join(k for k, _, _ in p["stages"]),
                          stage_arms="|".join(E[a]["id"] if a is not None else "-" for _, a, _ in p["stages"]),
                          stage_durations_s="|".join(str(x) for _, _, x in p["stages"]),
                          webster_Y=round(p["Y"], 4), lost_time_s=p["L"],
                          design_X_max=round(max(p["X"].values()), 4),
                          min_green_s=MIN_GREEN, max_green_s=MAX_GREEN, wait_cap_vehicle_s=180, wait_cap_ped_s=180))
    counts["public/signal_plans.csv"] = write(pub / "signal_plans.csv", plans)
    counts["public/od_probabilities.csv"] = write(pub / "od_probabilities.csv", [dict(origin_id=o, destination_id=dd, probability=round(p, 12))
                                                                                 for o in d.od for dd, p in d.od[o].items()])
    rows = []
    for (o, dd), paths in d.routes.items():
        for k, (path, pr) in enumerate(paths):
            rows.append(dict(origin_id=o, destination_id=dd, route_rank=k, logit_share=round(pr, 6),
                             edge_ids="|".join(E[e]["id"] for e in path)))
    counts["public/route_sets.csv"] = write(pub / "route_sets.csv", rows)
    counts["public/origin_rates.csv"] = write(pub / "origin_rates.csv", [dict(origin_id=o, mean_rate_veh_per_h=round(d.origin_rate_vph(o), 3))
                                                                         for o in net.boundaries])
    counts["public/vehicle_classes.csv"] = write(pub / "vehicle_classes.csv", [dict(class_id=k, probability=v["p"], pcu=v["pcu"], length_m=v["length"],
                                                                                    yield_weight=v["yield_w"]) for k, v in CLASSES.items()])
    counts["public/sensors.csv"] = write(pub / "sensors.csv", [dict(sensor_id="S_" + E[e]["id"], edge_id=E[e]["id"], kind="link_count_camera",
                                                                    period_s=SENSOR_PERIOD, noise="uniform_mixture{-2,-1,0,0,0,1,2}_clipped_at_0",
                                                                    p_available_to_missing=P_AM, p_missing_to_available=P_MA,
                                                                    stationary_missing_fraction=round(P_AM / (P_AM + P_MA), 4),
                                                                    stopline_presence_detector=True)
                                                               for e in range(len(E)) if not E[e]["is_exit"]])
    counts["public/mission_template.csv"] = write(pub / "mission_template.csv", [dict(destination="BE1", origins="BW1|BW2|BN1|BN2|BS1|BS2",
                                                                                      dispatch_window_s=f"{WARMUP_S}-{WARMUP_S + 300}",
                                                                                      speed_privilege=False, red_bypass=False)])
    # ---------------- hidden plant truth
    sc = make_scenario(d, rep)
    counts["hidden/desired_departures.csv"] = write(hid / "desired_departures.csv", [
        dict(vehicle_id=f"D{i:05d}", desired_departure_s=round(v["t"], 3), origin_id=v["o"], destination_id=v["d"], class_id=v["cls"],
             route_edge_ids="|".join(E[e]["id"] for e in v["route"]), occupancy_persons=v["occ"]) for i, v in enumerate(sc["vehicles"])])
    counts["hidden/latent_shock.csv"] = write(hid / "latent_shock.csv", [dict(bucket_start_s=60 * k, z=round(z, 8)) for k, z in enumerate(sc["shocks"])])
    counts["hidden/ambulance_mission.csv"] = write(hid / "ambulance_mission.csv", [dict(**sc["amb"])])
    inc = [dict(edge_id=E[i["edge"]]["id"], start_s=i["start"], end_s=i["end"], capacity_multiplier=round(i["cap_mult"], 4),
                speed_multiplier=round(i["speed_mult"], 4)) for i in sc["incidents"]] or [dict(edge_id="", start_s="", end_s="", capacity_multiplier="", speed_multiplier="")]
    counts["hidden/incidents.csv"] = write(hid / "incidents.csv", inc)
    state = []

    class Snap(NoPriority):
        def on_tick(self, sim, t):
            if t == sc["amb"]["dispatch"]:
                for e, q in enumerate(sim.dq):
                    for k, v in enumerate(q):
                        if v == sim.amb:
                            continue
                        state.append(dict(t_s=t, edge_id=E[e]["id"], fifo_index=k, vehicle_id=f"D{v:05d}",
                                          stopline_ready_s=round(sim.ready[v], 3), queued=sim.ready[v] <= t))
                for o, q in sim.ext.items():
                    for k, v in enumerate(q):
                        state.append(dict(t_s=t, edge_id=f"EXTERNAL_{o}", fifo_index=k, vehicle_id=f"D{v:05d}",
                                          stopline_ready_s="", queued=True))
    sim = Simulator(d, sc, Snap())
    sim.run()
    if sim.outage:
        counts["hidden/sensor_outage.csv"] = write(hid / "sensor_outage.csv", [dict(sensor_ids="|".join("S_" + E[e]["id"] for e in sorted(sim.outage[0])),
                                                                                   start_s=sim.outage[1], end_s=sim.outage[2])])
    counts["hidden/state_at_dispatch.csv"] = write(hid / "state_at_dispatch.csv", state)
    files = sorted(p for p in out.rglob("*.csv"))
    manifest = dict(provenance=PROV, design_seed=d.seed, target_X=X, realised_X_max=round(d.max_x(d.plans), 4), kappa=round(d.kappa, 6),
                    replication=rep, warmup_s=WARMUP_S,
                    files=[dict(file=str(p.relative_to(out)), sha256=hashlib.sha256(p.read_bytes()).hexdigest(), rows=counts.get(str(p.relative_to(out))))
                           for p in files],
                    information_boundary="controller may read public/ and live sensor feeds only; hidden/ is plant/evaluator truth")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=float, default=0.85)
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    m = export(a.x, a.rep, a.out or ROOT / "data" / f"fixture_X{a.x}_rep{a.rep}")
    print(json.dumps({k: v for k, v in m.items() if k != "files"}, indent=2))
