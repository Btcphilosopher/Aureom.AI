"""Image ingest and interpretation (vision).

Pipeline: :func:`ingest_image` (validated, content-addressed upload) ->
:func:`analyse_images` (adapters -> evidence -> pixel-space facade
observations, unknowns and warnings) -> calibration / hypotheses (``twin``).

Everything here works on appearance.  Nothing in this package identifies
structure, insulation, foundations or services, and every output carries a
provenance basis.  Optional dependencies (OpenCV, transformers, anthropic) are
imported lazily inside their adapters.
"""

from .adapters import (
    AdapterRegistry,
    AdapterSkipped,
    AdapterUnavailable,
    Capability,
    DepthEstimator,
    ElementDetector,
    MultiViewReconstructor,
    PerspectiveEstimator,
    SegmentationAdapter,
    VisionLanguageExtractor,
    default_registry,
)
from .analysis import analyse_images
from .fixture_adapters import DetectionFixture, FixtureElementDetector, FixturePerspectiveLines, FixtureSegmentation
from .ingest import ImageRejected, ingest_image, ingest_path, load_image_array, sanitize_filename
from .multiview import combine_orthogonal_views
from .perspective import detect_line_segments_numpy, estimate_vanishing_points

__all__ = [
    "AdapterRegistry", "AdapterSkipped", "AdapterUnavailable", "Capability", "DepthEstimator", "ElementDetector",
    "MultiViewReconstructor", "PerspectiveEstimator", "SegmentationAdapter", "VisionLanguageExtractor",
    "default_registry", "analyse_images", "DetectionFixture", "FixtureElementDetector", "FixturePerspectiveLines",
    "FixtureSegmentation", "ImageRejected", "ingest_image", "ingest_path", "load_image_array", "sanitize_filename",
    "combine_orthogonal_views", "detect_line_segments_numpy", "estimate_vanishing_points",
]
