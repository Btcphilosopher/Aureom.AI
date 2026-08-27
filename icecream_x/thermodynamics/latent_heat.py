"""Latent heat of fusion of water/ice.

A single constant is used (no strong temperature dependence is modelled --
the latent heat of fusion of water varies only a few percent over the
ice-cream-relevant temperature range and this is a second-order effect
next to the freezing-point-depression physics). Replace
``LATENT_HEAT_FUSION_WATER_J_KG`` with a temperature-dependent
correlation if higher fidelity is required.
"""

from __future__ import annotations

LATENT_HEAT_FUSION_WATER_J_KG = 334_000.0
