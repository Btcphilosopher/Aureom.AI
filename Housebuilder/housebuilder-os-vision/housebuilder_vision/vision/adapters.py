"""Adapter protocols and the adapter registry for image interpretation.

Every piece of machine perception in Housebuilder.OS Vision runs behind an
*adapter*: a small object with ``name``, ``version``, ``capability``,
``is_available()`` and a ``run(...)`` method returning validated model objects
from :mod:`housebuilder_vision.core.models`.  The analysis pipeline never
imports a perception library directly; it asks the :class:`AdapterRegistry`
to run a capability and records an :class:`~housebuilder_vision.core.models.AdapterRun`
for *every* adapter it tried (``ok``, ``unavailable``, ``skipped`` or
``error``, with message and duration), so the provenance of each detection
is auditable.

Boundaries and assumptions
--------------------------
* Adapters interpret *appearance*.  None of them may claim structural system,
  insulation, foundations, concealed services or engineering adequacy.
* Adapter outputs are untrusted: the analysis re-validates them (types,
  image id, coordinate bounds) before use.
* Optional heavy dependencies (``transformers``/``torch``, ``cv2``,
  ``anthropic``) are imported lazily inside ``run``; ``is_available()``
  only checks that the package can be found, so importing this module never
  pulls them in.  Model weights for the Hugging Face adapters are downloaded
  by ``transformers`` on first use (network access required); nothing is
  downloaded unless the adapter is actually run.
* Basis conventions for adapter outputs: curated fixture detections and
  manual annotations are ``OBSERVED`` image evidence; open-vocabulary model
  detections (zero-shot detectors) and monocular depth are ``INFERRED``
  (a model's interpretation that no person has checked); VLM extractions are
  always ``INFERRED``.

Capabilities (``Capability``) and run signatures
------------------------------------------------
=====================  ======================================================
``segmentation``       ``run(asset, rgb, *, seed=0) -> list[DetectedFeature]``
``element_detection``  ``run(asset, rgb, *, seed=0) -> list[DetectedFeature]``
``perspective``        ``run(asset, rgb, *, seed=0) -> PerspectiveEstimate``
``depth``              ``run(asset, rgb, *, seed=0) -> DepthEstimate``
``vlm_extraction``     ``run(asset, rgb, *, seed=0) -> VLMExtraction``
``multiview``          ``run(assets, facades, *, primary_image_id=None,
                       load_rgb=None, seed=0) -> MultiViewResult | None``
=====================  ======================================================

``rgb`` is the EXIF-transposed RGB ``uint8`` array (or ``None`` when pixel
data could not be decoded; pixel-based adapters then raise
:class:`AdapterSkipped`).
"""

from __future__ import annotations

import importlib.util
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Protocol, Sequence, runtime_checkable

import numpy as np

from ..core.models import (
    AdapterRun,
    DepthEstimate,
    DetectedFeature,
    FacadeObservation,
    FeatureType,
    ImageAsset,
    MultiViewResult,
    PerspectiveEstimate,
    VLMExtraction,
)
from ..core.provenance import Basis

#: Bundled detection fixtures (``demo/data/fixtures/<sha256>.json``).
DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "demo" / "data" / "fixtures"


class Capability(str, Enum):
    SEGMENTATION = "segmentation"
    ELEMENT_DETECTION = "element_detection"
    PERSPECTIVE = "perspective"
    DEPTH = "depth"
    MULTIVIEW = "multiview"
    VLM_EXTRACTION = "vlm_extraction"


class AdapterUnavailable(RuntimeError):
    """The adapter cannot run here (missing optional package, key or model)."""


class AdapterSkipped(RuntimeError):
    """The adapter is available but has nothing to contribute for this input
    (e.g. no detection fixture matches the image content)."""


def package_available(*modules: str) -> bool:
    """True when every named top-level module can be imported (no import is done)."""
    for m in modules:
        try:
            if importlib.util.find_spec(m) is None:
                return False
        except (ImportError, ValueError):
            return False
    return True


# =============================================================================
# Protocols
# =============================================================================
@runtime_checkable
class VisionAdapter(Protocol):
    """Common surface of every adapter."""

    name: str
    version: str
    capability: str

    def is_available(self) -> bool: ...


@runtime_checkable
class SegmentationAdapter(VisionAdapter, Protocol):
    """Returns region features (``FINISH_REGION`` / ``FACADE`` / ``ROOF`` polygons)."""

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> list[DetectedFeature]: ...


@runtime_checkable
class ElementDetector(VisionAdapter, Protocol):
    """Returns element features (facades, roofs, openings, lines) in pixel coordinates."""

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> list[DetectedFeature]: ...


@runtime_checkable
class PerspectiveEstimator(VisionAdapter, Protocol):
    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> PerspectiveEstimate: ...


@runtime_checkable
class DepthEstimator(VisionAdapter, Protocol):
    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> DepthEstimate: ...


@runtime_checkable
class VisionLanguageExtractor(VisionAdapter, Protocol):
    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> VLMExtraction: ...


@runtime_checkable
class MultiViewReconstructor(VisionAdapter, Protocol):
    """Links several views of one building.

    ``load_rgb`` lazily returns the pixel array of an asset (reconstructors
    that work on pixels, e.g. SfM, use it; the orthogonal-elevation combiner
    only needs the facade observations).
    """

    def run(self, assets: Sequence[ImageAsset], facades: Sequence[FacadeObservation], *,
            primary_image_id: Optional[str] = None,
            load_rgb: Optional[Callable[[ImageAsset], np.ndarray]] = None,
            seed: int = 0) -> Optional[MultiViewResult]: ...


# =============================================================================
# Registry
# =============================================================================
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")


def safe_message(text: Any, limit: int = 300) -> str:
    """Single-line, length-limited text for logs/AdapterRun messages."""
    s = _CTRL.sub(" ", str(text)).strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _exc_message(exc: BaseException) -> str:
    return safe_message(f"{type(exc).__name__}: {exc}")


@dataclass
class AdapterOutcome:
    adapter: str
    version: str
    capability: str
    value: Any


@dataclass
class RegistryResult:
    """Results of running one capability: successful outputs plus a run record
    for every adapter that was considered."""

    capability: str
    results: list[AdapterOutcome] = field(default_factory=list)
    runs: list[AdapterRun] = field(default_factory=list)

    @property
    def first(self) -> Any:
        return self.results[0].value if self.results else None

    @property
    def ok(self) -> bool:
        return bool(self.results)


class AdapterRegistry:
    """Ordered adapters per capability.

    ``run(capability, ..., mode="first")`` tries adapters in order until one
    returns a result (later ones are recorded as ``skipped``); ``mode="all"``
    runs every adapter.  Exceptions never escape: they become ``error`` runs.
    """

    def __init__(self, adapters: Iterable[Any] = ()) -> None:
        self._by_cap: dict[str, list[Any]] = {}
        for a in adapters:
            self.register(a)

    @staticmethod
    def _cap(capability: Any) -> str:
        return capability.value if isinstance(capability, Enum) else str(capability)

    def register(self, adapter: Any, *, first: bool = False) -> None:
        for attr in ("name", "version", "capability", "is_available", "run"):
            if not hasattr(adapter, attr):
                raise TypeError(f"adapter {adapter!r} lacks '{attr}'")
        cap = self._cap(adapter.capability)
        lst = self._by_cap.setdefault(cap, [])
        if any(a.name == adapter.name for a in lst):
            raise ValueError(f"adapter '{adapter.name}' already registered for '{cap}'")
        if first:
            lst.insert(0, adapter)
        else:
            lst.append(adapter)

    def unregister(self, name: str) -> int:
        n = 0
        for cap, lst in self._by_cap.items():
            keep = [a for a in lst if a.name != name]
            n += len(lst) - len(keep)
            self._by_cap[cap] = keep
        return n

    def adapters(self, capability: Any) -> list[Any]:
        return list(self._by_cap.get(self._cap(capability), []))

    def capabilities(self) -> list[str]:
        return [c for c, lst in self._by_cap.items() if lst]

    def describe(self) -> list[dict[str, Any]]:
        out = []
        for cap, lst in self._by_cap.items():
            for a in lst:
                try:
                    avail = bool(a.is_available())
                except Exception:  # pragma: no cover - defensive
                    avail = False
                out.append({"capability": cap, "name": a.name, "version": a.version, "available": avail})
        return out

    def run(self, capability: Any, *args: Any, mode: str = "first", **kwargs: Any) -> RegistryResult:
        cap = self._cap(capability)
        res = RegistryResult(capability=cap)
        for adapter in self._by_cap.get(cap, []):
            name, version = str(adapter.name), str(adapter.version)
            if mode == "first" and res.results:
                res.runs.append(AdapterRun(adapter=name, version=version, capability=cap, status="skipped",
                                           message=f"not run: '{res.results[0].adapter}' already produced a result"))
                continue
            t0 = time.perf_counter()
            try:
                available = bool(adapter.is_available())
            except Exception as exc:  # pragma: no cover - defensive
                available = False
                msg = _exc_message(exc)
            else:
                msg = "is_available() returned False (optional dependency, credential or data missing)"
            if not available:
                res.runs.append(AdapterRun(adapter=name, version=version, capability=cap, status="unavailable",
                                           message=msg, duration_ms=_ms(t0)))
                continue
            try:
                value = adapter.run(*args, **kwargs)
            except AdapterSkipped as exc:
                res.runs.append(AdapterRun(adapter=name, version=version, capability=cap, status="skipped",
                                           message=safe_message(exc), duration_ms=_ms(t0)))
                continue
            except AdapterUnavailable as exc:
                res.runs.append(AdapterRun(adapter=name, version=version, capability=cap, status="unavailable",
                                           message=safe_message(exc), duration_ms=_ms(t0)))
                continue
            except Exception as exc:  # adapters are untrusted: never let them crash the pipeline
                res.runs.append(AdapterRun(adapter=name, version=version, capability=cap, status="error",
                                           message=_exc_message(exc), duration_ms=_ms(t0)))
                continue
            if value is None or (isinstance(value, list) and not value):
                res.runs.append(AdapterRun(adapter=name, version=version, capability=cap, status="skipped",
                                           message="adapter returned no result", duration_ms=_ms(t0)))
                continue
            res.results.append(AdapterOutcome(adapter=name, version=version, capability=cap, value=value))
            n = len(value) if isinstance(value, list) else 1
            res.runs.append(AdapterRun(adapter=name, version=version, capability=cap, status="ok",
                                       message=f"{n} result(s)", duration_ms=_ms(t0)))
        return res


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 3)


# =============================================================================
# Optional Hugging Face adapters (lazy; unavailable without transformers+torch)
# =============================================================================
_ZERO_SHOT_LABELS: dict[str, FeatureType] = {
    "window": FeatureType.WINDOW,
    "door": FeatureType.DOOR,
    "garage door": FeatureType.GARAGE_DOOR,
    "roof": FeatureType.ROOF,
    "balcony": FeatureType.BALCONY,
}


class HuggingFaceZeroShotDetector:
    """Open-vocabulary element detector (``transformers`` zero-shot-object-detection).

    Default model: OWL-ViT (``google/owlvit-base-patch32``); labels window,
    door, garage door, roof, balcony.  Output boxes are marked
    ``basis=INFERRED`` (an unverified model interpretation), with
    ``method="transformers:zero-shot-object-detection"`` and
    ``method_version=<model id>``.  It does not output facade extents, ground or
    eaves lines, so on its own it supports opening counts and storey rows but
    not facade dimensions; combine with manual facade annotation.
    """

    capability = Capability.ELEMENT_DETECTION.value
    version = "1.0"

    def __init__(self, model_id: str = "google/owlvit-base-patch32", *, labels: Sequence[str] | None = None,
                 threshold: float = 0.15, max_detections: int = 200, device: Optional[str] = None) -> None:
        self.model_id = model_id
        self.name = "hf-zero-shot-detector"
        self.labels = tuple(labels) if labels else tuple(_ZERO_SHOT_LABELS)
        self.threshold = float(threshold)
        self.max_detections = int(max_detections)
        self.device = device
        self._pipe = None

    def is_available(self) -> bool:
        return package_available("transformers", "torch")

    def _pipeline(self):
        if self._pipe is None:
            try:
                from transformers import pipeline  # lazy optional import
            except ImportError as exc:  # pragma: no cover - only without transformers
                raise AdapterUnavailable(f"transformers not installed: {exc}") from exc
            kw = {"model": self.model_id}
            if self.device is not None:
                kw["device"] = self.device
            self._pipe = pipeline("zero-shot-object-detection", **kw)
        return self._pipe

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> list[DetectedFeature]:
        if rgb is None:
            raise AdapterSkipped("no pixel data")
        from PIL import Image

        raw = self._pipeline()(Image.fromarray(np.asarray(rgb, dtype=np.uint8)), candidate_labels=list(self.labels))
        h, w = rgb.shape[:2]
        feats: list[DetectedFeature] = []
        for k, det in enumerate(list(raw)[: self.max_detections]):
            try:
                score = float(det["score"])
                label = str(det["label"]).strip().lower()
                box = det["box"]
                x0, y0 = float(box["xmin"]), float(box["ymin"])
                x1, y1 = float(box["xmax"]), float(box["ymax"])
            except (KeyError, TypeError, ValueError):
                continue
            ft = _ZERO_SHOT_LABELS.get(label)
            if ft is None or not (0.0 <= score <= 1.0) or score < self.threshold:
                continue
            x0, x1 = sorted((min(max(x0, 0.0), w), min(max(x1, 0.0), w)))
            y0, y1 = sorted((min(max(y0, 0.0), h), min(max(y1, 0.0), h)))
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue
            feats.append(DetectedFeature(
                feature_id=f"{asset.image_id}.hfzs{k:03d}", image_id=asset.image_id, feature_type=ft,
                label=label, bbox=(x0, y0, x1, y1), basis=Basis.INFERRED,
                method="transformers:zero-shot-object-detection", method_version=self.model_id,
                confidence=score, pixel_uncertainty=max(4.0, 0.02 * max(x1 - x0, y1 - y0)),
                attributes={"zero_shot_label": label},
                evidence="Open-vocabulary detector output (unverified; basis inferred)."))
        return feats


class TransformersDepthAdapter:
    """Relative monocular depth (``transformers`` depth-estimation pipeline).

    Default model ``depth-anything/Depth-Anything-V2-Small-hf``.  The result
    is a *relative*, model-specific depth range (``basis`` inferred, never
    metric); it is reported for context only and never sets dimensions.
    """

    capability = Capability.DEPTH.value
    version = "1.0"

    def __init__(self, model_id: str = "depth-anything/Depth-Anything-V2-Small-hf", *,
                 device: Optional[str] = None) -> None:
        self.model_id = model_id
        self.name = "hf-depth-estimation"
        self.device = device
        self._pipe = None

    def is_available(self) -> bool:
        return package_available("transformers", "torch")

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> DepthEstimate:
        if rgb is None:
            raise AdapterSkipped("no pixel data")
        if self._pipe is None:
            try:
                from transformers import pipeline  # lazy optional import
            except ImportError as exc:  # pragma: no cover
                raise AdapterUnavailable(f"transformers not installed: {exc}") from exc
            kw = {"model": self.model_id}
            if self.device is not None:
                kw["device"] = self.device
            self._pipe = pipeline("depth-estimation", **kw)
        from PIL import Image

        out = self._pipe(Image.fromarray(np.asarray(rgb, dtype=np.uint8)))
        depth = np.asarray(out["depth"], dtype=np.float64)
        if depth.size == 0 or not np.isfinite(depth).all():
            raise ValueError("depth model returned an empty or non-finite map")
        lo, hi = np.percentile(depth, [5.0, 95.0])
        span = float(depth.max() - depth.min()) or 1.0
        return DepthEstimate(
            method="transformers:depth-estimation", method_version=self.model_id, available=True,
            relative_depth_range=(float((lo - depth.min()) / span), float((hi - depth.min()) / span)),
            notes=["Relative monocular depth (basis inferred); model-specific and not metric. "
                   "Not used to set any dimension."])


# =============================================================================
# Default registry
# =============================================================================
def default_registry(fixture_dir: Optional[Path | str] = None, enable_vlm: bool = False, *,
                     vlm_client: Any = None, enable_optional: bool = True) -> AdapterRegistry:
    """Registry used by :func:`~housebuilder_vision.vision.analysis.analyse_images`.

    Order (first successful adapter wins per capability):

    * element detection: bundled fixtures, then the optional zero-shot detector;
    * segmentation: bundled fixtures;
    * perspective: fixture line segments, optional OpenCV lines, NumPy lines;
    * depth: optional transformers depth;
    * VLM extraction: Claude adapter, only when ``enable_vlm`` (it sends the
      image to an external API, so it is opt-in);
    * multiview: orthogonal-elevation combiner, then the COLMAP SfM interface
      (unavailable by default).
    """
    from .fixture_adapters import FixtureElementDetector, FixturePerspectiveLines, FixtureSegmentation
    from .multiview import ColmapSfMReconstructor, OrthogonalViewCombiner
    from .opencv_adapters import OpenCVLinePerspective
    from .perspective import NumpyLinePerspective

    fd = Path(fixture_dir) if fixture_dir is not None else DEFAULT_FIXTURE_DIR
    reg = AdapterRegistry()
    reg.register(FixtureElementDetector(fd))
    if enable_optional:
        reg.register(HuggingFaceZeroShotDetector())
    reg.register(FixtureSegmentation(fd))
    reg.register(FixturePerspectiveLines(fd))
    if enable_optional:
        reg.register(OpenCVLinePerspective())
    reg.register(NumpyLinePerspective())
    if enable_optional:
        reg.register(TransformersDepthAdapter())
    if enable_vlm:
        from .vlm_adapter import ClaudeVLMExtractor

        reg.register(ClaudeVLMExtractor(client=vlm_client))
    reg.register(OrthogonalViewCombiner())
    reg.register(ColmapSfMReconstructor())
    return reg


__all__ = [
    "DEFAULT_FIXTURE_DIR", "Capability", "AdapterUnavailable", "AdapterSkipped", "package_available",
    "VisionAdapter", "SegmentationAdapter", "ElementDetector", "PerspectiveEstimator", "DepthEstimator",
    "VisionLanguageExtractor", "MultiViewReconstructor", "AdapterOutcome", "RegistryResult",
    "AdapterRegistry", "HuggingFaceZeroShotDetector", "TransformersDepthAdapter", "default_registry",
    "safe_message",
]
