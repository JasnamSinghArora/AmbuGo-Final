"""Plant realisation for one replication (seed): demand, incidents, sensor noise,
ambulance mission.  Every component draws from its own namespaced stream, so the
same replication is reproduced exactly under every policy (common random numbers).
"""
import math
from .network import CLASSES
from .rng import stream

AR_RHO, AR_SIGMA = 0.75, 0.18
BUCKET_S = 60
AMB_ORIGINS = ("BW1", "BW2", "BN1", "BN2", "BS1", "BS2")
HOSPITAL = "BE1"


def _poisson(r, lam):
    if lam < 30:
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= r.random()
            if p <= L:
                return k
            k += 1
    return max(0, int(round(r.gauss(lam, math.sqrt(lam)))))


WARMUP_S = 1800      # MSER-5 truncation point was 1405 s (X=0.8) and 1625 s (X=0.95)


def make_scenario(design, rep, horizon=4200, dispatch_window=(WARMUP_S, WARMUP_S + 300), incident_prob=0.5):
    net, seed = design.net, design.seed
    # ---- demand: stationary AR(1) common shock (fix: v7 started Z0 with variance 0.44)
    rz = stream(seed, "demand", rep, "shock")
    z = rz.gauss(0, 1)
    shocks = []
    for k in range(math.ceil(horizon / BUCKET_S)):
        if k > 0:
            z = AR_RHO * z + math.sqrt(1 - AR_RHO ** 2) * rz.gauss(0, 1)
        shocks.append(z)
    names = list(CLASSES)
    probs = [CLASSES[c]["p"] for c in names]
    vehicles = []
    for o in net.boundaries:
        r = stream(seed, "demand", rep, "origin", o)
        dests = list(design.od[o])
        dprob = [design.od[o][d] for d in dests]
        for k, zk in enumerate(shocks):
            rate = design.origin_rate_vph(o) * math.exp(AR_SIGMA * zk - 0.5 * AR_SIGMA ** 2)
            for _ in range(_poisson(r, rate * BUCKET_S / 3600.0)):
                t = k * BUCKET_S + r.random() * BUCKET_S
                d = r.choices(dests, dprob)[0]
                paths = design.routes[(o, d)]
                route = r.choices([p for p, _ in paths], [w for _, w in paths])[0]
                c = r.choices(names, probs)[0]
                occ = r.choice([1, 1, 1, 2, 3]) if c == "car" else r.randint(8, 35) if c == "bus" else r.choice([1, 1, 2])
                vehicles.append(dict(t=t, o=o, d=d, route=route, cls=c, pcu=CLASSES[c]["pcu"], occ=occ))
    vehicles.sort(key=lambda v: v["t"])
    # ---- ambulance mission (randomised origin and dispatch time)
    ra = stream(seed, "ambulance", rep)
    amb = dict(origin=ra.choice(AMB_ORIGINS), dest=HOSPITAL,
               dispatch=ra.randint(*dispatch_window), insert_pos_m=20.0, pcu=1.5, occ=3)
    # ---- incident: lane blockage on a random two-lane approach near the dispatch time
    ri = stream(seed, "incident", rep)
    incidents = []
    if ri.random() < incident_prob:
        two_lane = [i for i, e in enumerate(net.edges) if e["lanes"] == 2 and not e["is_exit"]]
        e = ri.choice(two_lane)
        start = amb["dispatch"] + ri.randint(-180, 120)
        incidents.append(dict(edge=e, start=start, end=start + ri.randint(240, 480),
                              cap_mult=(1 + ri.uniform(0.45, 0.65)) / 2,   # one of two lanes at 45-65 %
                              speed_mult=ri.uniform(0.75, 0.9)))
    return dict(rep=rep, vehicles=vehicles, shocks=shocks, amb=amb, incidents=incidents, horizon=horizon)
