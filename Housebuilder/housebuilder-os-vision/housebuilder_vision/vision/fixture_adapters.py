"""Fixture-backed adapters: bundled detections for known images.

A *detection fixture* is a JSON file recording what a detector (or a person
doing manual annotation) emitted for one specific image.  Fixtures make the
bundled demonstration deterministic and testable without model weights, and
they document the exact evidence a detector would have to produce.

Matching is by **content**: ``<fixture_dir>/<sha256 of the image bytes>.json``.
A fixture is only used when its ``image_sha256`` and pixel dimensions match the
ingested asset, so a different image that merely has the same filename never
receives fixture detections (detections are never fabricated).  A caller may
explicitly bind an asset to a fixture by ``fixture_key`` (``bindings`` maps
``image_id`` or ``sha256`` to a key) — for example after a lossless re-encode —
in which case the dimensions must still match and every feature records the
binding in its ``evidence``.

Fixture files are untrusted input: size-limited (5 MB), parsed with the strict
Pydantic schema :class:`DetectionFixture` (unknown keys rejected, finite
coordinates inside the image, bounded list lengths and attribute sizes), and
only ``observed`` / ``inferred`` bases are accepted (a fixture cannot claim
user confirmation).

Adapters produce results only when a fixture exists; otherwise they raise
:class:`~.adapters.AdapterSkipped` (recorded as status ``skipped``).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal, Optional, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ..core.models import DetectedFeature, FeatureType, ImageAsset, PerspectiveEstimate
from ..core.provenance import Basis
from .adapters import AdapterSkipped, Capability
from .perspective import estimate_vanishing_points, focal_length_px_from_exif, rng_for

FIXTURE_SCHEMA_VERSION = "1.0"
MAX_FIXTURE_BYTES = 5 * 1024 * 1024
#: Fixture feature types returned by the segmentation adapter (others go to the detector).
SEGMENTATION_TYPES = {FeatureType.FINISH_REGION}

AttrValue = Union[StrictBool, StrictInt, StrictFloat, StrictStr, None]
Pt = tuple[float, float]
Box = tuple[float, float, float, float]


class FixtureError(ValueError):
    """A fixture exists but is invalid or does not match the image."""


class FixtureDetector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9_.:\- ]{1,80}$")
    version: str = Field(pattern=r"^[A-Za-z0-9_.:\-]{1,20}$")


def _finite(*vals: float) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals)


def _check_attrs(attrs: dict) -> None:
    if len(attrs) > 32:
        raise ValueError("at most 32 attributes per item")
    for k, v in attrs.items():
        if not (1 <= len(k) <= 64):
            raise ValueError("attribute keys must be 1-64 characters")
        if isinstance(v, str) and len(v) > 200:
            raise ValueError(f"attribute '{k}' is longer than 200 characters")
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(f"attribute '{k}' is not finite")


class FixtureFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str = Field(pattern=r"^[A-Za-z0-9_.\-]{1,48}$")
    feature_type: FeatureType
    label: str = Field(default="", max_length=120)
    bbox: Optional[Box] = None
    polygon: Optional[list[Pt]] = Field(default=None, min_length=3, max_length=256)
    line: Optional[Box] = None
    confidence: float = Field(ge=0.0, le=1.0)
    pixel_uncertainty: float = Field(default=2.0, ge=0.0, le=100.0)
    #: Only OBSERVED or INFERRED (a fixture cannot claim user confirmation or assumption).
    basis: Basis = Basis.OBSERVED
    #: Overrides the fixture-level detector name (e.g. "manual-annotation-fixture").
    method: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.:\- ]{1,80}$")
    attributes: dict[str, AttrValue] = Field(default_factory=dict)
    evidence: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _check(self) -> "FixtureFeature":
        if self.basis not in (Basis.OBSERVED, Basis.INFERRED):
            raise ValueError(f"feature {self.feature_id}: fixture basis must be 'observed' or 'inferred'")
        if self.bbox is None and self.polygon is None and self.line is None:
            raise ValueError(f"feature {self.feature_id} has no geometry")
        if self.bbox is not None:
            if not _finite(*self.bbox) or self.bbox[2] < self.bbox[0] or self.bbox[3] < self.bbox[1]:
                raise ValueError(f"feature {self.feature_id}: bbox must be finite (x0, y0, x1, y1) with x1>=x0, y1>=y0")
        if self.line is not None and not _finite(*self.line):
            raise ValueError(f"feature {self.feature_id}: line is not finite")
        if self.polygon is not None and not all(_finite(*p) for p in self.polygon):
            raise ValueError(f"feature {self.feature_id}: polygon is not finite")
        _check_attrs(self.attributes)
        return self

    def points(self) -> list[Pt]:
        pts: list[Pt] = []
        if self.bbox:
            pts += [(self.bbox[0], self.bbox[1]), (self.bbox[2], self.bbox[3])]
        if self.line:
            pts += [(self.line[0], self.line[1]), (self.line[2], self.line[3])]
        if self.polygon:
            pts += list(self.polygon)
        return pts


class DetectionFixture(BaseModel):
    """Strict schema of ``fixtures/<sha256>.json``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = FIXTURE_SCHEMA_VERSION
    fixture_key: str = Field(pattern=r"^[A-Za-z0-9_.\-]{1,80}$")
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width_px: int = Field(gt=0, le=30000)
    height_px: int = Field(gt=0, le=30000)
    detector: FixtureDetector
    description: str = Field(default="", max_length=2000)
    #: Image-level annotations, e.g. {"image_kind_hint": "ai_generated_concept"}.
    image_attributes: dict[str, AttrValue] = Field(default_factory=dict)
    features: list[FixtureFeature] = Field(default_factory=list, max_length=2000)
    perspective_lines: list[Box] = Field(default_factory=list, max_length=5000)
    notes: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _check(self) -> "DetectionFixture":
        _check_attrs(self.image_attributes)
        ids = [f.feature_id for f in self.features]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate feature_id in fixture")
        mx, my = 0.02 * self.width_px + 5.0, 0.02 * self.height_px + 5.0
        pts = [p for f in self.features for p in f.points()]
        for ln in self.perspective_lines:
            if not _finite(*ln):
                raise ValueError("perspective line is not finite")
            pts += [(ln[0], ln[1]), (ln[2], ln[3])]
        for x, y in pts:
            if not (-mx <= x <= self.width_px + mx and -my <= y <= self.height_px + my):
                raise ValueError(f"coordinate ({x:.1f}, {y:.1f}) lies outside the {self.width_px}x{self.height_px} image")
        if any(len(n) > 500 for n in self.notes):
            raise ValueError("fixture notes are limited to 500 characters each")
        return self


# =============================================================================
# Loading
# =============================================================================
class FixtureStore:
    """Loads and caches fixtures from a directory (content-addressed)."""

    def __init__(self, fixture_dir: Path | str, *, bindings: Optional[dict[str, str]] = None) -> None:
        self.fixture_dir = Path(fixture_dir)
        self.bindings = dict(bindings or {})
        self._cache: dict[tuple, DetectionFixture] = {}

    def _read(self, path: Path) -> DetectionFixture:
        st = path.stat()
        if st.st_size > MAX_FIXTURE_BYTES:
            raise FixtureError(f"fixture {path.name} exceeds {MAX_FIXTURE_BYTES // (1024 * 1024)} MB")
        key = (str(path), st.st_mtime_ns, st.st_size)
        if key not in self._cache:
            try:
                self._cache[key] = DetectionFixture.model_validate_json(path.read_bytes())
            except ValueError as exc:
                raise FixtureError(f"fixture {path.name} failed validation: {exc}") from exc
        return self._cache[key]

    def by_key(self, fixture_key: str) -> Optional[DetectionFixture]:
        if not self.fixture_dir.is_dir():
            return None
        for p in sorted(self.fixture_dir.glob("*.json")):
            try:
                fx = self._read(p)
            except FixtureError:
                continue
            if fx.fixture_key == fixture_key:
                return fx
        return None

    def load(self, asset: ImageAsset) -> tuple[Optional[DetectionFixture], str]:
        """Return (fixture or None, how it matched: "sha256" / "binding:<key>" / "")."""
        path = self.fixture_dir / f"{asset.sha256}.json"
        if path.is_file():
            fx = self._read(path)
            if fx.image_sha256 != asset.sha256:
                raise FixtureError(f"fixture {path.name} declares a different image_sha256")
            self._check_dims(fx, asset)
            return fx, "sha256"
        key = self.bindings.get(asset.image_id) or self.bindings.get(asset.sha256)
        if key:
            fx = self.by_key(key)
            if fx is None:
                raise FixtureError(f"no fixture with fixture_key '{key}'")
            self._check_dims(fx, asset)
            return fx, f"binding:{key}"
        return None, ""

    @staticmethod
    def _check_dims(fx: DetectionFixture, asset: ImageAsset) -> None:
        if (fx.width_px, fx.height_px) != (asset.width_px, asset.height_px):
            raise FixtureError(f"fixture is for a {fx.width_px}x{fx.height_px} image but the asset is "
                               f"{asset.width_px}x{asset.height_px}")


def fixture_features(fx: DetectionFixture, asset: ImageAsset, *, match: str = "sha256",
                     include: Optional[set[FeatureType]] = None, exclude: Optional[set[FeatureType]] = None,
                     with_image_metadata: bool = False) -> list[DetectedFeature]:
    """Convert fixture records into :class:`DetectedFeature` objects for ``asset``."""
    out: list[DetectedFeature] = []
    bound = match.startswith("binding:")
    for ff in fx.features:
        if include is not None and ff.feature_type not in include:
            continue
        if exclude is not None and ff.feature_type in exclude:
            continue
        evidence = ff.evidence or f"Detection fixture '{fx.fixture_key}'."
        if bound:
            evidence += f" (Fixture explicitly bound by key '{fx.fixture_key}'; image content hash differs.)"
        out.append(DetectedFeature(
            feature_id=f"{asset.image_id}.{ff.feature_id}", image_id=asset.image_id,
            feature_type=ff.feature_type, label=ff.label, bbox=ff.bbox,
            polygon=list(ff.polygon) if ff.polygon else None, line=ff.line, basis=ff.basis,
            method=ff.method or fx.detector.name, method_version=fx.detector.version,
            confidence=ff.confidence, pixel_uncertainty=ff.pixel_uncertainty,
            attributes=dict(ff.attributes), evidence=evidence))
    if with_image_metadata and fx.image_attributes:
        out.append(DetectedFeature(
            feature_id=f"{asset.image_id}.image_meta", image_id=asset.image_id, feature_type=FeatureType.OTHER,
            label="image-metadata", bbox=(0.0, 0.0, float(asset.width_px), float(asset.height_px)),
            basis=Basis.INFERRED, method=fx.detector.name, method_version=fx.detector.version,
            attributes=dict(fx.image_attributes),
            evidence=f"Image-level annotation from fixture '{fx.fixture_key}'."))
    return out


# =============================================================================
# Adapters
# =============================================================================
class _FixtureAdapterBase:
    version = "1.0"

    def __init__(self, fixture_dir: Path | str, *, bindings: Optional[dict[str, str]] = None,
                 store: Optional[FixtureStore] = None) -> None:
        self.store = store or FixtureStore(fixture_dir, bindings=bindings)

    def is_available(self) -> bool:
        return self.store.fixture_dir.is_dir()

    def _fixture(self, asset: ImageAsset) -> tuple[DetectionFixture, str]:
        fx, match = self.store.load(asset)
        if fx is None:
            raise AdapterSkipped(f"no detection fixture for image content sha256 {asset.sha256[:12]}...")
        return fx, match


class FixtureElementDetector(_FixtureAdapterBase):
    """Element detections (everything except finish regions) from a matching fixture."""

    name = "fixture-element-detector"
    capability = Capability.ELEMENT_DETECTION.value

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray] = None, *, seed: int = 0) -> list[DetectedFeature]:
        fx, match = self._fixture(asset)
        feats = fixture_features(fx, asset, match=match, exclude=SEGMENTATION_TYPES, with_image_metadata=True)
        if not feats:
            raise AdapterSkipped("fixture contains no element detections")
        return feats


class FixtureSegmentation(_FixtureAdapterBase):
    """Finish / material-appearance regions from a matching fixture."""

    name = "fixture-segmentation"
    capability = Capability.SEGMENTATION.value

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray] = None, *, seed: int = 0) -> list[DetectedFeature]:
        fx, match = self._fixture(asset)
        feats = fixture_features(fx, asset, match=match, include=SEGMENTATION_TYPES)
        if not feats:
            raise AdapterSkipped("fixture contains no segmentation regions")
        return feats


class FixturePerspectiveLines(_FixtureAdapterBase):
    """Vanishing points from the fixture's line segments (``perspective_lines`` + ``line_segment`` features)."""

    name = "fixture-perspective-lines"
    capability = Capability.PERSPECTIVE.value

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray] = None, *, seed: int = 0) -> PerspectiveEstimate:
        fx, _ = self._fixture(asset)
        lines = [tuple(ln) for ln in fx.perspective_lines]
        lines += [tuple(f.line) for f in fx.features if f.feature_type == FeatureType.LINE_SEGMENT and f.line]
        if len(lines) < 6:
            raise AdapterSkipped("fixture has too few line segments for perspective estimation")
        est = estimate_vanishing_points(np.array(lines, dtype=np.float64), (asset.width_px, asset.height_px),
                                        rng=rng_for(asset, seed), focal_length_px=focal_length_px_from_exif(asset),
                                        method="fixture-lines+numpy-ransac-vp")
        est.notes.append(f"Line segments from fixture '{fx.fixture_key}' ({fx.detector.name} {fx.detector.version}).")
        return est


__all__ = ["FIXTURE_SCHEMA_VERSION", "FixtureError", "FixtureDetector", "FixtureFeature", "DetectionFixture",
           "FixtureStore", "fixture_features", "FixtureElementDetector", "FixtureSegmentation",
           "FixturePerspectiveLines"]
