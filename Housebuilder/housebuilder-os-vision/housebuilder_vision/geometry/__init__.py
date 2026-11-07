"""Exact parametric geometry: rectilinear footprints, walls, roofs, storeys."""
from .footprint import GeometryError, Rect, side_pieces, union_area
from .metrics import BlockParams, OpeningParams, compute_geometry_metrics, compute_metrics, params_from_twin

__all__ = ["GeometryError", "Rect", "side_pieces", "union_area", "BlockParams", "OpeningParams",
           "compute_geometry_metrics", "compute_metrics", "params_from_twin"]
