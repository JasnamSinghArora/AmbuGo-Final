"""Statistics used in the analysis (all paired over replications, which share
common random numbers across policies)."""
import math
import numpy as np


def paired_ci(diff, n_boot=10000, alpha=0.05, seed=0):
    """Mean of paired differences with a percentile bootstrap CI (resampling replications)."""
    d = np.asarray(diff, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    means = d[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(d.mean()), float(lo), float(hi)


def sign_flip_p(diff, n_perm=20000, seed=0):
    """Two-sided paired randomisation (sign-flip) test of mean difference = 0."""
    d = np.asarray(diff, float)
    rng = np.random.default_rng(seed)
    obs = abs(d.mean())
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(d)))
    null = np.abs((signs * d).mean(axis=1))
    return float((1 + (null >= obs - 1e-12).sum()) / (n_perm + 1))


def holm(pvals):
    """Holm step-down adjusted p-values (dict name -> p)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def clopper_pearson(k, n, alpha=0.05):
    from scipy.stats import beta
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return float(lo), float(hi)


def cvar(x, q=0.9):
    """Mean of the worst (1-q) fraction (upper tail)."""
    x = np.sort(np.asarray(x, float))
    k = int(math.floor(q * len(x)))
    return float(x[k:].mean())
