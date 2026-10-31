"""Network representation shared by the generator, simulator and policies."""
import csv
import math
from collections import defaultdict
from pathlib import Path

GEOM = Path(__file__).resolve().parent.parent / "geometry"

# Vehicle classes. PCU values are declared design assumptions of the same order
# as Indian guideline values; they must be calibrated before any field claim.
CLASSES = {
    "car":          dict(p=0.53, pcu=1.0, length=4.5, yield_w=0.6),
    "motorcycle":   dict(p=0.30, pcu=0.5, length=2.1, yield_w=1.0),
    "autorickshaw": dict(p=0.10, pcu=1.0, length=2.8, yield_w=0.8),
    "bus":          dict(p=0.04, pcu=3.0, length=11.5, yield_w=0.2),
    "goods":        dict(p=0.03, pcu=2.5, length=7.0, yield_w=0.2),
}
MEAN_PCU = sum(c["p"] * c["pcu"] for c in CLASSES.values())
JAM_DENSITY_PCU_PER_M = 0.16
STOPLINE_BUFFER_M = 5.0
STARTUP_LOST_S = 2.0
AMBER_S, ALLRED_S = 3, 2
PED_STAGES = (("W", 7), ("PC", 16), ("PR", 2))
PED_TIME = sum(d for _, d in PED_STAGES)
MIN_GREEN, MAX_GREEN = 8, 60


class Network:
    def __init__(self, nodes, edges):
        self.nodes = nodes                      # id -> dict(x, y, kind)
        self.edges = edges                      # list of dict, index = edge idx
        self.eid = {e["id"]: i for i, e in enumerate(edges)}
        self.out = defaultdict(list)
        self.inc = defaultdict(list)
        for i, e in enumerate(edges):
            self.out[e["u"]].append(i)
            self.inc[e["v"]].append(i)
        self.junctions = sorted(n for n, d in nodes.items() if d["kind"] == "J")
        self.boundaries = sorted(n for n, d in nodes.items() if d["kind"] == "B")
        # arms ordered by edge id (same convention as v7)
        self.arms = {j: sorted(self.inc[j], key=lambda i: edges[i]["id"]) for j in self.junctions}
        for i, e in enumerate(edges):
            e["tt"] = e["L"] / e["vff"]
            e["storage"] = math.floor((e["L"] - STOPLINE_BUFFER_M) * e["lanes"] * JAM_DENSITY_PCU_PER_M)
            e["is_exit"] = nodes[e["v"]]["kind"] == "B"
            e["is_entry"] = nodes[e["u"]]["kind"] == "B"

    def allowed(self, a, b):
        ea, eb = self.edges[a], self.edges[b]
        return ea["v"] == eb["u"] and eb["v"] != ea["u"]

    def first_edge(self, origin):
        (e,) = self.out[origin]
        return e

    @classmethod
    def from_v7_geometry(cls, path=GEOM):
        nodes = {}
        for r in csv.DictReader(open(Path(path) / "nodes.csv")):
            nodes[r["node_id"]] = dict(x=float(r["x_m"]), y=float(r["y_m"]),
                                       kind="J" if r["kind"] == "signalized_junction" else "B",
                                       land_use=r["land_use"])
        edges = []
        for r in csv.DictReader(open(Path(path) / "edges.csv")):
            edges.append(dict(id=r["edge_id"], u=r["from_node"], v=r["to_node"], L=float(r["length_m"]),
                              lanes=int(r["lanes"]), vff=float(r["speed_limit_mps"]),
                              s=float(r["capacity_veh_per_s_per_lane"]) * int(r["lanes"])))  # PCU/s, whole approach
        return cls(nodes, edges)


def simple_paths(net, origin, dest, slack=1.25, kmax=4):
    """All loop-free paths origin->dest (no U-turns, no passing other boundaries)
    with free-flow time <= slack * fastest, best kmax returned sorted by time."""
    found = []

    def dfs(node, seen, path, t, bound):
        if t > bound:
            return
        if node == dest:
            found.append((t, tuple(path)))
            return
        for e in net.out[node]:
            v = net.edges[e]["v"]
            if v in seen or (net.nodes[v]["kind"] == "B" and v != dest):
                continue
            path.append(e); seen.add(v)
            dfs(v, seen, path, t + net.edges[e]["tt"], bound)
            path.pop(); seen.discard(v)

    dfs(origin, {origin}, [], 0.0, 1e9 if slack is None else 1e9)
    found.sort()
    best = found[0][0]
    keep = [p for p in found if p[0] <= slack * best + 1e-9][:kmax]
    return keep
