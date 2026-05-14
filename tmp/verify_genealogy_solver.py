"""Verify the genealogy_solver.json against expected outputs for the
12 test APNs in the plan. Mirrors the JS BFS so any discrepancy reveals
either a data issue or a port bug to investigate."""
import json
import re
import sys
from pathlib import Path
from collections import deque

ROOT = Path(r"C:/Users/mbindl/Documents/GitHub/Reporting")
DATA = ROOT / "html" / "genealogy_solver" / "data" / "genealogy_solver.json"

with DATA.open(encoding="utf-8") as f:
    payload = json.load(f)

edges = payload["edges"]
apns  = payload["apns"]

STD_APN_RE = re.compile(r"^(\d{3})-(\d{3})-(\d{2,3})$")

def canonical_apn(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = STD_APN_RE.match(s)
    if not m:
        return s
    return f"{m.group(1)}-{m.group(2)}-{m.group(3).zfill(3)}"


def walk(seed, apply_filter=True):
    seed = canonical_apn(seed)
    if not seed or seed not in apns:
        return {"found": False, "seed": seed, "members": 0, "up": 0, "dn": 0}

    members = {seed: ("self", 0)}
    edge_idxs = set()

    def bfs(direction, role):
        visited = {seed}
        queue = deque([(seed, 0)])
        while queue:
            apn, hop = queue.popleft()
            node = apns.get(apn, {})
            ei_list = node.get("pi" if direction == "in" else "po", [])
            for ei in ei_list:
                e = edges[ei]
                if apply_filter and not e["ab"]:
                    continue
                neighbor = e["o"] if direction == "in" else e["n"]
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                edge_idxs.add(ei)
                if neighbor not in members:
                    members[neighbor] = (role, hop + 1)
                queue.append((neighbor, hop + 1))

    bfs("in",  "ancestor")
    bfs("out", "descendant")

    up = max((h for (r, h) in members.values() if r == "ancestor"),   default=0)
    dn = max((h for (r, h) in members.values() if r == "descendant"), default=0)
    return {"found": True, "seed": seed, "members": len(members), "up": up, "dn": dn,
            "n_ancestors": sum(1 for r, _ in members.values() if r == "ancestor"),
            "n_descendants": sum(1 for r, _ in members.values() if r == "descendant"),
            "edge_count": len(edge_idxs)}


def fmt(r):
    if not r["found"]:
        return f"seed={r['seed']} NOT FOUND"
    return (f"seed={r['seed']} | size={r['members']:>4} | "
            f"{r['n_ancestors']:>3}↑ / {r['n_descendants']:>3}↓ | "
            f"max {r['up']}↑ / {r['dn']}↓ | edges traversed={r['edge_count']}")


cases = [
    ("1. No-event APN",            "048-041-03",       True),
    ("2. Simple multi-hop rename", "132-231-10",       True),
    ("3. Split parent",            "132-232-10",       True),
    ("4. Leaf at end of chain",    "132-630-01",       True),
    ("5. Hub APN (filter ON)",     "029-630-029",      True),
    ("5b. Hub APN (filter OFF)",   "029-630-029",      False),
    ("6. Huge fan-out",            "032-301-011",      True),
    ("7. EL Dorado pad rename",    "091-152-10",       True),
    ("8a. is_primary toggle ON",   "124-071-42",       True),
    ("8b. is_primary toggle OFF",  "124-071-42",       False),
    ("9a. LTINFO no-year ON",      "132-231-09",       True),
    ("9b. LTINFO no-year OFF",     "132-231-09",       False),
    ("10. Douglas long-form",      "1318-22-310-001",  True),
    ("11. Pre-2018 EL pad input",  "015-331-04",       True),
    ("12. Invalid input",          "not-an-apn",       True),
]

print("=" * 100)
print(f"{'CASE':<32}  FILTER  RESULT")
print("=" * 100)
for label, apn, apply_filter in cases:
    r = walk(apn, apply_filter)
    f = "ON " if apply_filter else "OFF"
    print(f"{label:<32}  {f}     {fmt(r)}")
