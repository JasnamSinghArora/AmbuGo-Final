"""Namespaced, order-independent random streams.

v7 drew every random quantity from ONE stream, so changing any upstream design
choice silently re-drew all downstream realizations (no common random numbers).
Here every (seed, namespace, *keys) tuple gets its own independent stream derived
with SHA-256, so e.g. the demand realization of replication 17 is identical
across all policies and is unaffected by how many incident draws were made.
"""
import hashlib
import random

NAMESPACES = ("design", "demand", "incident", "sensor", "yield", "ambulance")


def stream(seed, namespace, *keys):
    if namespace not in NAMESPACES:
        raise ValueError(f"unknown RNG namespace {namespace!r}")
    tag = "|".join([str(seed), namespace, *map(str, keys)]).encode()
    return random.Random(int.from_bytes(hashlib.sha256(tag).digest()[:8], "big"))
