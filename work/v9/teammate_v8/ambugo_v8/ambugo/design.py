"""Design layer: OD model, route sets, demand calibration to a target degree of
saturation, and Webster-optimised fixed-time baseline signal plans.

Fixes relative to v7
* v7 drew greens from {20,24,28} s independent of demand, leaving 8/51 approaches
  oversaturated (X up to 1.66) at MEAN demand.  Here demand is scaled so that the
  critical junction reaches a declared target X, and every junction gets a
  Webster cycle with demand-proportional splits, so the do-nothing baseline is a
  defensible engineering counterfactual rather than a strawman.
* v7 used all-or-nothing static shortest paths (12/51 approaches carried zero
  demand).  Here each OD pair has up to 4 near-shortest routes with a logit split.
"""
import math
from .network import (MEAN_PCU, AMBER_S, ALLRED_S, PED_STAGES, PED_TIME, MIN_GREEN, MAX_GREEN,
                      STARTUP_LOST_S, simple_paths)
from .rng import stream

LOGIT_THETA = 0.05          # 1/s ; a 20 s slower route gets e^-1 of the share
ROUTE_SLACK = 1.25
DEST_ATTRACTION = {"BE1": 1.6, "BE2": 1.2, "BS1": 1.2}
DIST_SCALE_M = 2200.0
CYCLE_MIN, CYCLE_MAX = 60, 150
LOST_PER_PHASE = AMBER_S + ALLRED_S + STARTUP_LOST_S - AMBER_S  # = all-red + start-up = 4 s
EFFECTIVE_GREEN_BONUS = AMBER_S - STARTUP_LOST_S                # g_eff = g + 1


class Design:
    def __init__(self, net, seed=20261024, target_x=0.85):
        self.net, self.seed, self.target_x = net, seed, target_x
        r = stream(seed, "design", "bases")
        self.base_vph = {b: r.uniform(230, 390) for b in net.boundaries}   # relative origin weights
        self.od = self._od()
        self.routes = self._routes()
        self.unit_load = self._unit_load()          # PCU/s on each edge per 1x base demand
        self.kappa, self.plans = self._calibrate()

    # ---------------- OD & routes
    def _od(self):
        n, od = self.net.nodes, {}
        for o in self.net.boundaries:
            w = {}
            for d in self.net.boundaries:
                if d == o:
                    continue
                dist = math.hypot(n[o]["x"] - n[d]["x"], n[o]["y"] - n[d]["y"])
                w[d] = DEST_ATTRACTION.get(d, 1.0) * math.exp(-dist / DIST_SCALE_M)
            tot = sum(w.values())
            od[o] = {d: v / tot for d, v in w.items()}
        return od

    def _routes(self):
        out = {}
        for o in self.net.boundaries:
            for d in self.net.boundaries:
                if o == d:
                    continue
                paths = simple_paths(self.net, o, d, slack=ROUTE_SLACK)
                t0 = paths[0][0]
                w = [math.exp(-LOGIT_THETA * (t - t0)) for t, _ in paths]
                s = sum(w)
                out[(o, d)] = [(p, wi / s) for (t, p), wi in zip(paths, w)]
        return out

    def _unit_load(self):
        load = [0.0] * len(self.net.edges)
        for o in self.net.boundaries:
            lam = self.base_vph[o] / 3600.0 * MEAN_PCU
            for d, pd in self.od[o].items():
                for path, pr in self.routes[(o, d)]:
                    for e in path:
                        load[e] += lam * pd * pr
        return load

    # ---------------- Webster
    def webster(self, kappa):
        plans = {}
        for j in self.net.junctions:
            arms = self.net.arms[j]
            n = len(arms)
            L = n * LOST_PER_PHASE + PED_TIME
            y = {a: kappa * self.unit_load[a] / self.net.edges[a]["s"] for a in arms}
            Y = sum(y.values())
            C = CYCLE_MAX if Y >= 0.95 * (1 - L / CYCLE_MAX) else (1.5 * L + 5) / (1 - Y)
            C = min(max(C, CYCLE_MIN), CYCLE_MAX)
            G = C - L                                   # total effective green
            # proportional split with min/max greens (iterative water-filling)
            geff = {}
            free = set(arms)
            Gleft = G
            while True:
                Yf = sum(y[a] for a in free) or 1e-9
                changed = False
                for a in list(free):
                    g = Gleft * (y[a] / Yf) if Yf > 1e-8 else Gleft / len(free)
                    if g < MIN_GREEN + EFFECTIVE_GREEN_BONUS:
                        geff[a] = MIN_GREEN + EFFECTIVE_GREEN_BONUS; free.discard(a); changed = True
                    elif g > MAX_GREEN + EFFECTIVE_GREEN_BONUS:
                        geff[a] = MAX_GREEN + EFFECTIVE_GREEN_BONUS; free.discard(a); changed = True
                if not changed:
                    for a in free:
                        geff[a] = Gleft * (y[a] / Yf) if Yf > 1e-8 else Gleft / len(free)
                    break
                Gleft = G - sum(geff.values())
                if not free:
                    break
            greens = {a: max(MIN_GREEN, min(MAX_GREEN, int(round(geff[a] - EFFECTIVE_GREEN_BONUS)))) for a in arms}
            stages = []
            for a in arms:
                stages += [("G", a, greens[a]), ("Y", a, AMBER_S), ("R", a, ALLRED_S)]
            stages += [(k, None, d) for k, d in PED_STAGES]
            cycle = sum(d for _, _, d in stages)
            offset = stream(self.seed, "design", "offset", j).randrange(cycle)
            X = {a: (kappa * self.unit_load[a]) * cycle / (self.net.edges[a]["s"] * (greens[a] + EFFECTIVE_GREEN_BONUS))
                 for a in arms}
            plans[j] = dict(stages=stages, cycle=cycle, offset=offset, greens=greens, X=X, Y=Y, L=L)
        return plans

    def max_x(self, plans):
        return max(max(p["X"].values()) for p in plans.values())

    def _calibrate(self):
        lo, hi = 0.05, 5.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self.max_x(self.webster(mid)) < self.target_x:
                lo = mid
            else:
                hi = mid
        # integer rounding of greens makes X a step function of kappa; take the largest
        # kappa whose realised (rounded) max X does not exceed the target.
        return lo, self.webster(lo)

    def origin_rate_vph(self, o):
        return self.kappa * self.base_vph[o]
