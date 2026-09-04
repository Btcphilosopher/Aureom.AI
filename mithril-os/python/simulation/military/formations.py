"""
Formation modifiers.

Spec ref: 16 (unit formations).
"""

from __future__ import annotations

from typing import Dict

# Multiplicative modifiers applied to an army's effective attack/defence
# depending on its chosen formation. Kept small and legible rather than a
# full spatial rank simulation (that lives in the future high-fidelity
# battle renderer, section 46 LEVEL 4/5).
FORMATION_MODIFIERS: Dict[str, Dict[str, float]] = {
    "LINE":           {"attack": 1.0,  "defence": 1.0,  "speed": 1.0},
    "COLUMN":         {"attack": 0.85, "defence": 0.85, "speed": 1.25},
    "WEDGE":          {"attack": 1.3,  "defence": 0.8,  "speed": 1.1},
    "SQUARE":         {"attack": 0.8,  "defence": 1.35, "speed": 0.7},
    "SHIELD_WALL":    {"attack": 0.9,  "defence": 1.5,  "speed": 0.6},
    "CAVALRY_WEDGE":  {"attack": 1.5,  "defence": 0.7,  "speed": 1.2},
    "SCATTERED":      {"attack": 0.7,  "defence": 0.6,  "speed": 1.3},
    "RANK":           {"attack": 1.1,  "defence": 1.05, "speed": 0.95},
}


def modifier(formation: str, stat: str) -> float:
    return FORMATION_MODIFIERS.get(formation, FORMATION_MODIFIERS["LINE"]).get(stat, 1.0)
