"""Netlist-derived connectivity between logical groups and SRAM macros.

Input: export/connectivity.json (OpenDB: nets touching >= 2 groups with their
HPWL after placement) and geometry.json (group centroids).  Output: a ranked
list of group pairs with net count, total and mean HPWL, and centroid
distance -- the quantities the locality experiments compare.  These are
placement-based estimates, not routed lengths.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def analyse(conn_path: Path, geo: dict) -> dict:
    d = json.loads(Path(conn_path).read_text())
    groups = geo.get("groups") or {}
    cent = {g: v["centroid_um"] for g, v in groups.items()}
    # SRAM pseudo-groups: centroid of the macros of each kind
    for kind, sel in (("sram_main", lambda n: "u_tile" not in n), ("sram_tspm", lambda n: "u_tile" in n)):
        ms = [m for m in geo.get("macros", []) if sel(m["name"])]
        if ms:
            cent[kind] = [sum((m["bbox"][0] + m["bbox"][2]) / 2 for m in ms) / len(ms),
                          sum((m["bbox"][1] + m["bbox"][3]) / 2 for m in ms) / len(ms)]
    pairs = []
    for p in d.get("pairs", []):
        a, b = p["a"], p["b"]
        dist = None
        if a in cent and b in cent:
            dist = round(abs(cent[a][0] - cent[b][0]) + abs(cent[a][1] - cent[b][1]), 1)
        n = p["nets"]
        hp = float(p["hpwl_um"])
        pairs.append({"a": a, "b": b, "nets": n, "hpwl_um": round(hp, 1), "mean_hpwl_um": round(hp / n, 1) if n else None,
                      "centroid_manhattan_um": dist})
    pairs.sort(key=lambda x: -x["hpwl_um"])
    total = sum(p["hpwl_um"] for p in pairs)
    focus = {}
    for a, b in (("cpu", "sram_main"), ("cpu", "fabric"), ("dma", "fabric"), ("fabric", "sram_main"),
                 ("tile", "sram_tspm"), ("vector", "sram_tspm"), ("tensor", "sram_tspm"), ("fabric", "tile"),
                 ("cpu", "rom"), ("sram_ctrl", "sram_main"), ("vector", "tensor")):
        k = next((p for p in pairs if {p["a"], p["b"]} == {a, b}), None)
        if k:
            focus[f"{a}<->{b}"] = {x: k[x] for x in ("nets", "hpwl_um", "mean_hpwl_um", "centroid_manhattan_um")}
    return {"inter_group_hpwl_um": round(total, 1), "pairs_top": pairs[:25], "focus_pairs": focus,
            "label": "placement-based HPWL of nets crossing logical-group boundaries (not routed length)"}
