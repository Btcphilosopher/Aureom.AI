"""
Spatial Anchor Engine: lets virtual content stay attached to real-world
locations, objects, rooms, or geographic coordinates, independent of the
current tracking session.

    REAL TABLE -> SPATIAL ANCHOR -> VIRTUAL SCREEN
"""

from xr_os.anchors.anchor_engine import Anchor, AnchorStore, AnchorType, SpatialAnchorEngine

__all__ = ["Anchor", "AnchorType", "AnchorStore", "SpatialAnchorEngine"]
