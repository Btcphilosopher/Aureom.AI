"""Calibration, geometry hypotheses, the editable parametric twin and its 3D mesh.

Pipeline: ``calibrate_scale`` (pixels -> metres with provenance) ->
``generate_geometry_hypotheses`` (competing hidden-footprint hypotheses) ->
``build_parametric_twin`` (selected hypothesis -> BuildingTwin, hidden facades
rule-filled) -> ``apply_twin_edit`` (validated, logged user edits) ->
``build_mesh`` (trimesh scene for viewing / glTF export).

Only core models and the exact geometry core are used; the vision module's
implementation is not imported here (it only provides ``AnalysisResult`` data).
"""

from .builder import (
    apply_twin_edit,
    build_parametric_twin,
    colour_from_appearance,
    regenerate_hidden_openings,
    twin_hash,
    visual_finishes_from_analysis,
)
from .calibration import calibrate_scale, prior_cue_calibration, resolve_reference, scale_group
from .hypotheses import generate_geometry_hypotheses
from .mesh import build_mesh, piece_outline_polylines, scene_for_gltf, scene_to_plotly_meshes

__all__ = [
    "apply_twin_edit",
    "build_mesh",
    "build_parametric_twin",
    "calibrate_scale",
    "colour_from_appearance",
    "generate_geometry_hypotheses",
    "piece_outline_polylines",
    "prior_cue_calibration",
    "regenerate_hidden_openings",
    "resolve_reference",
    "scale_group",
    "scene_for_gltf",
    "scene_to_plotly_meshes",
    "twin_hash",
    "visual_finishes_from_analysis",
]
