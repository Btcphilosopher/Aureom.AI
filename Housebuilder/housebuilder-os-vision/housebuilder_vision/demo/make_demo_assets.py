"""Generate the bundled demonstration images and detection fixtures (deterministic).

"Aureom Demo House, Plot 7" is **fictional**.  This script draws two synthetic
elevations with Pillow and NumPy (randomness only from seeded
``numpy.random.Generator`` objects, so re-running produces byte-identical PNGs
with the same Pillow/zlib build) and writes detection fixtures
``data/fixtures/<sha256 of the image bytes>.json`` in the form a detector would
emit them, validated by :class:`~housebuilder_vision.vision.fixture_adapters.DetectionFixture`.

Hidden truth (used ONLY to draw the images and to compute fixture pixel
coordinates; the engine must recover it from evidence plus labelled inputs):

* front elevation 1600 x 1000 px, near fronto-parallel, 92 px/m at the facade
  plane, ground line at y = 900;
* main block 9.60 m wide, 8.40 m deep, 2 storeys, FFL 0.15 m, floor-to-floor
  2.70 m (wall plate 5.55 m), gable roof with ridge parallel to the frontage,
  pitch 35 deg (rise 2.94 m), verge overhang 0.20 m; red-brown brick-like walls,
  dark grey tile-like roof, subtle first-floor band;
* garage 3.20 m wide on the right, abutting the main block, 1 storey, same FFL,
  front-facing gable, pitch 30 deg (rise 0.924 m); white panel-like garage door;
* front openings per ``docs/ARCHITECTURE.md`` section 4;
* left elevation 1400 x 900 px at 78 px/m (ground at y = 800): gable end of the
  main block (depth 8.40 m, pitch 35 deg), one window per storey (GF 0.90 x 1.20
  at 5.70 m from the rear corner, sill 0.90; FF 0.60 x 0.90 at 3.90 m, sill
  1.10); the garage is not visible.

Fixture coordinates are computed from the same parameters with seeded
uniform noise of +/-1.5 px and confidences in [0.80, 0.97].

The concept-reference example ``concept_render_example.jpg`` is a downscale
(1200 px wide, JPEG quality 85, no metadata) of an AI-generated house render
supplied with the project; its fixture holds approximate *manual annotations*
(``method="manual-annotation-fixture"``, confidence 0.6) and marks the image as
an AI concept.  If the source render is not available the existing JPEG and
fixture are kept.

Usage::

    python -m housebuilder_vision.demo.make_demo_assets [--out DIR] [--concept-source PATH] [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
from PIL import Image, ImageDraw

from ..vision.fixture_adapters import DetectionFixture

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE_DIR = DATA_DIR / "fixtures"
FRONT_NAME = "demo_front_elevation.png"
LEFT_NAME = "demo_left_elevation.png"
CONCEPT_NAME = "concept_render_example.jpg"
DEFAULT_CONCEPT_SOURCE = Path(__file__).resolve().parents[3] / "6b54f15e-b79c-4c67-aa8c-3db8fc4ed053.png"

FRONT_KEY = "aureom-demo-front-elevation-v1"
LEFT_KEY = "aureom-demo-left-elevation-v1"
CONCEPT_KEY = "aureom-concept-render-example-v1"
DETECTOR = {"name": "fixture:aureom-demo-detector", "version": "1.0"}
MANUAL = {"name": "manual-annotation-fixture", "version": "1.0"}
NOISE_PX = 1.5
EVIDENCE = ("Synthetic demo detection (fixture): computed from the drawing parameters with seeded "
            "+/-1.5 px noise. Fictional data.")

# ----------------------------------------------------------------- hidden truth (metres)
MAIN_W, MAIN_D = 9.60, 8.40
FFL, FTF = 0.15, 2.70
MAIN_STOREYS = 2
PLATE = FFL + MAIN_STOREYS * FTF  # 5.55
MAIN_PITCH = 35.0
MAIN_RISE = 0.5 * MAIN_D * math.tan(math.radians(MAIN_PITCH))  # 2.9409
RIDGE_Z = PLATE + MAIN_RISE
VERGE = 0.20
GAR_W, GAR_PITCH = 3.20, 30.0
GAR_PLATE = FFL + FTF  # 2.85
GAR_RISE = 0.5 * GAR_W * math.tan(math.radians(GAR_PITCH))  # 0.9238
GAR_APEX_Z = GAR_PLATE + GAR_RISE
GAR_X0 = MAIN_W  # garage starts at the main block's right wall
SIDE_EAVES_OVERHANG = 0.25

#: (id, block, kind, storey, offset from the block's left wall end, width, height, sill above storey floor)
FRONT_OPENINGS: list[tuple[str, str, str, int, float, float, float, float]] = [
    ("o01", "main", "window", 0, 1.00, 1.80, 1.20, 0.90),
    ("o02", "main", "door", 0, 4.30, 1.00, 2.10, 0.00),
    ("o03", "main", "window", 0, 6.80, 1.80, 1.20, 0.90),
    ("o04", "main", "window", 1, 1.30, 1.20, 1.20, 0.90),
    ("o05", "main", "window", 1, 4.20, 1.20, 1.20, 0.90),
    ("o06", "main", "window", 1, 7.10, 1.20, 1.20, 0.90),
    ("o07", "garage", "garage_door", 0, 0.40, 2.40, 2.13, 0.00),
]
#: Left elevation (gable end of main); offset from the image-left end (= rear corner).
LEFT_OPENINGS: list[tuple[str, str, str, int, float, float, float, float]] = [
    ("o01", "main", "window", 0, 5.70, 0.90, 1.20, 0.90),
    ("o02", "main", "window", 1, 3.90, 0.60, 0.90, 1.10),
]
_FT = {"window": "window", "door": "door", "garage_door": "garage_door"}

# ----------------------------------------------------------------- colours
SKY_TOP, SKY_HORIZON = (112, 160, 212), (206, 224, 240)
GRASS = (84, 130, 60)
BRICK, MORTAR = (150, 72, 52), (196, 186, 170)
PLINTH = (96, 54, 48)
BAND = (182, 122, 90)
TILE = (74, 76, 82)
WHITE = (238, 238, 232)
GLASS, GLASS_HI = (96, 126, 150), (150, 178, 198)
SILL = (206, 201, 190)
LINTEL = (128, 62, 46)
DOOR_LEAF = (34, 72, 80)
CONCRETE, PAVING = (172, 170, 162), (188, 178, 160)


@dataclass(frozen=True)
class Elevation:
    """Metric -> pixel mapping of one fronto-parallel elevation."""

    width_px: int
    height_px: int
    ppm: float
    ground_y: float
    origin_x: float

    def X(self, m: float) -> float:
        return self.origin_x + m * self.ppm

    def Y(self, z: float) -> float:
        return self.ground_y - z * self.ppm

    def pt(self, m: float, z: float) -> tuple[float, float]:
        return self.X(m), self.Y(z)

    def rect(self, x0: float, z0: float, x1: float, z1: float) -> list[tuple[float, float]]:
        return [self.pt(x0, z0), self.pt(x0, z1), self.pt(x1, z1), self.pt(x1, z0)]


FRONT = Elevation(1600, 1000, 92.0, 900.0, 210.0)
LEFT = Elevation(1400, 900, 78.0, 800.0, 372.0)


# =============================================================================
# Textures (vectorised, seeded)
# =============================================================================
def _grid(el: Elevation) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:el.height_px, 0:el.width_px].astype(np.float64)
    z = (el.ground_y - (yy + 0.5)) / el.ppm
    xm = ((xx + 0.5) - el.origin_x) / el.ppm
    return xm, z


def _clip(a: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(a), 0, 255).astype(np.uint8)


def sky_and_ground(el: Elevation, rng: np.random.Generator) -> np.ndarray:
    H, W = el.height_px, el.width_px
    img = np.zeros((H, W, 3))
    t = np.clip(np.arange(H) / max(1.0, el.ground_y), 0.0, 1.0)[:, None]
    for c in range(3):
        img[:, :, c] = SKY_TOP[c] + (SKY_HORIZON[c] - SKY_TOP[c]) * t
    g0 = int(math.ceil(el.ground_y))
    n = H - g0
    if n > 0:
        shade = np.linspace(1.0, 0.85, n)[:, None, None]
        noise = rng.normal(0.0, 9.0, size=(n, W, 1))
        img[g0:] = np.array(GRASS)[None, None, :] * shade + noise
    return _clip(img)


def brick_texture(el: Elevation, rng: np.random.Generator, *, base: Sequence[int] = BRICK,
                  x_offset_m: float = 0.0, variation: float = 0.07) -> np.ndarray:
    """Stretcher bond: 65 mm bricks + 10 mm joints (75 mm courses), 225 mm brick + joint."""
    xm, z = _grid(el)
    xm = xm - x_offset_m
    course, length, joint = 0.075, 0.225, 0.010
    c = np.floor(z / course).astype(np.int64)
    zin = z - c * course
    xb = xm + (c % 2) * (length / 2.0)
    b = np.floor(xb / length).astype(np.int64)
    xin = xb - b * length
    c0, b0 = int(c.min()), int(b.min())
    shape = (int(c.max()) - c0 + 1, int(b.max()) - b0 + 1)
    fac = rng.normal(1.0, variation, size=shape)[c - c0, b - b0]
    red = rng.normal(0.0, 6.0, size=shape)[c - c0, b - b0]
    tex = np.empty(z.shape + (3,))
    tex[..., 0] = base[0] * fac + red
    tex[..., 1] = base[1] * fac
    tex[..., 2] = base[2] * fac
    mortar = (zin < joint) | (xin < joint)
    tex[mortar] = MORTAR
    tex += rng.normal(0.0, 4.0, size=z.shape + (1,))
    return _clip(tex)


def tile_texture(el: Elevation, rng: np.random.Generator, *, z_top: float, row_h: float, tile_w: float = 0.30) -> np.ndarray:
    """Tile courses seen in elevation: staggered tiles, shadowed butt edges."""
    xm, z = _grid(el)
    d = z_top - z
    r = np.floor(d / row_h).astype(np.int64)
    rin = d - r * row_h
    xb = xm + (r % 2) * (tile_w / 2.0)
    t = np.floor(xb / tile_w).astype(np.int64)
    xin = xb - t * tile_w
    r0, t0 = int(r.min()), int(t.min())
    shape = (int(r.max()) - r0 + 1, int(t.max()) - t0 + 1)
    fac = rng.normal(1.0, 0.06, size=shape)[r - r0, t - t0]
    tex = np.array(TILE, dtype=np.float64)[None, None, :] * fac[..., None]
    tex[rin > 0.80 * row_h] *= 0.55
    tex[xin < 0.012] *= 0.65
    tex += rng.normal(0.0, 3.0, size=z.shape + (1,))
    return _clip(tex)


def _paste(img: Image.Image, tex: np.ndarray, polygon: Sequence[tuple[float, float]]) -> None:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon([(float(x), float(y)) for x, y in polygon], fill=255)
    img.paste(Image.fromarray(tex, "RGB"), (0, 0), mask)


def _r(draw: ImageDraw.ImageDraw, el: Elevation, x0: float, z0: float, x1: float, z1: float, fill) -> None:
    draw.rectangle([el.X(x0), el.Y(z1), el.X(x1) - 1, el.Y(z0) - 1], fill=fill)


# =============================================================================
# Openings
# =============================================================================
def draw_window(draw: ImageDraw.ImageDraw, el: Elevation, x0: float, z0: float, w: float, h: float) -> None:
    fw = 0.06
    _r(draw, el, x0 - 0.10, z0 + h, x0 + w + 0.10, z0 + h + 0.075, LINTEL)  # soldier-course lintel
    _r(draw, el, x0, z0, x0 + w, z0 + h, WHITE)  # frame
    _r(draw, el, x0 + fw, z0 + fw, x0 + w - fw, z0 + h - fw, GLASS)
    # reflection
    gx0, gx1, gz0, gz1 = x0 + fw, x0 + w - fw, z0 + fw, z0 + h - fw
    k = 0.35 * (gz1 - gz0)
    draw.polygon([el.pt(gx0, gz1 - k), el.pt(gx0 + k, gz1), el.pt(gx0 + 2 * k, gz1), el.pt(gx0, gz1 - 2 * k)],
                 fill=GLASS_HI)
    # transom and mullions
    _r(draw, el, x0, z0 + h - 0.32, x0 + w, z0 + h - 0.27, WHITE)
    if w >= 1.0:
        n = 3 if w > 1.5 else 2
        for i in range(1, n):
            xm = x0 + i * w / n
            _r(draw, el, xm - 0.025, z0, xm + 0.025, z0 + h, WHITE)
    _r(draw, el, x0 - 0.05, z0 - 0.06, x0 + w + 0.05, z0, SILL)  # sill


def draw_door(draw: ImageDraw.ImageDraw, el: Elevation, x0: float, z0: float, w: float, h: float) -> None:
    fw = 0.06
    _r(draw, el, x0 - 0.10, z0 + h, x0 + w + 0.10, z0 + h + 0.075, LINTEL)
    _r(draw, el, x0, z0, x0 + w, z0 + h, WHITE)
    _r(draw, el, x0 + fw, z0, x0 + w - fw, z0 + h - fw, DOOR_LEAF)
    _r(draw, el, x0 + 0.30, z0 + 1.45, x0 + w - 0.30, z0 + h - 0.25, GLASS)  # vision panel
    _r(draw, el, x0 + 0.35, z0 + 0.95, x0 + w - 0.35, z0 + 1.00, (180, 160, 90))  # letter plate
    cx, cz = el.pt(x0 + w - 0.16, z0 + 1.05)
    draw.ellipse([cx - 4, cz - 4, cx + 4, cz + 4], fill=(196, 164, 84))
    _r(draw, el, x0 - 0.10, z0 - FFL, x0 + w + 0.10, z0, SILL)  # step up to FFL


def draw_garage_door(draw: ImageDraw.ImageDraw, el: Elevation, x0: float, z0: float, w: float, h: float) -> None:
    _r(draw, el, x0 - 0.10, z0 + h, x0 + w + 0.10, z0 + h + 0.075, LINTEL)
    _r(draw, el, x0, z0, x0 + w, z0 + h, (214, 214, 208))
    _r(draw, el, x0 + 0.05, z0, x0 + w - 0.05, z0 + h - 0.05, (242, 242, 236))
    for i in range(1, 4):  # sectional panel joints
        zz = z0 + i * (h - 0.05) / 4.0
        _r(draw, el, x0 + 0.05, zz - 0.012, x0 + w - 0.05, zz + 0.012, (192, 192, 186))
    for i in range(4):  # embossed panels
        zb = z0 + i * (h - 0.05) / 4.0
        for j in range(4):
            xa = x0 + 0.15 + j * (w - 0.30) / 4.0
            _r(draw, el, xa + 0.04, zb + 0.10, xa + (w - 0.30) / 4.0 - 0.04, zb + (h - 0.05) / 4.0 - 0.10,
               (232, 232, 226))
    _r(draw, el, x0 + w / 2 - 0.08, z0 + 0.20, x0 + w / 2 + 0.08, z0 + 0.25, (90, 90, 90))
    _r(draw, el, x0 - 0.05, z0 - FFL, x0 + w + 0.05, z0, CONCRETE)  # threshold/apron edge


def _opening_box(el: Elevation, block_x0: float, storey: int, off: float, w: float, h: float, sill: float):
    z0 = FFL + storey * FTF + sill
    return block_x0 + off, z0, w, h


# =============================================================================
# Rendering
# =============================================================================
def render_front_elevation(seed: int = 20261107) -> Image.Image:
    el = FRONT
    rng = np.random.default_rng(seed)
    img = Image.fromarray(sky_and_ground(el, rng), "RGB")
    brick_main = brick_texture(el, rng)
    brick_gar = brick_texture(el, rng, x_offset_m=0.11)
    plinth = brick_texture(el, rng, base=PLINTH, variation=0.05)
    tiles = tile_texture(el, rng, z_top=RIDGE_Z, row_h=MAIN_RISE / 20.0)
    # driveway and path (below ground line)
    d = ImageDraw.Draw(img)
    d.polygon([(el.X(GAR_X0 + 0.15), el.ground_y), (el.X(GAR_X0 + GAR_W - 0.15), el.ground_y),
               (el.X(GAR_X0 + GAR_W + 0.9), el.height_px), (el.X(GAR_X0 - 0.9), el.height_px)], fill=CONCRETE)
    d.polygon([(el.X(4.15), el.ground_y), (el.X(5.45), el.ground_y), (el.X(5.75), el.height_px),
               (el.X(3.85), el.height_px)], fill=PAVING)
    # walls
    _paste(img, brick_main, el.rect(0.0, 0.0, MAIN_W, PLATE))
    _paste(img, brick_gar, [el.pt(GAR_X0, 0.0), el.pt(GAR_X0, GAR_PLATE), el.pt(GAR_X0 + GAR_W / 2, GAR_APEX_Z),
                            el.pt(GAR_X0 + GAR_W, GAR_PLATE), el.pt(GAR_X0 + GAR_W, 0.0)])
    _paste(img, plinth, el.rect(0.0, 0.0, GAR_X0 + GAR_W, FFL))
    d = ImageDraw.Draw(img)
    # first-floor band (main block only) and movement joint at the garage abutment
    _r(d, el, 0.0, GAR_PLATE, MAIN_W, GAR_PLATE + 0.09, BAND)
    for i in range(int(MAIN_W / 0.075)):
        x = i * 0.075
        d.line([el.pt(x, GAR_PLATE), el.pt(x, GAR_PLATE + 0.09)], fill=MORTAR, width=1)
    d.line([el.pt(GAR_X0, 0.0), el.pt(GAR_X0, GAR_PLATE)], fill=(70, 44, 38), width=2)
    # main roof band: eaves (plate) to ridge, extended by the verge overhang at both gable ends
    _paste(img, tiles, el.rect(-VERGE, PLATE, MAIN_W + VERGE, RIDGE_Z))
    d = ImageDraw.Draw(img)
    _r(d, el, -VERGE, RIDGE_Z - 0.12, MAIN_W + VERGE, RIDGE_Z, (52, 54, 58))  # ridge tiles
    _r(d, el, -VERGE, PLATE, MAIN_W + VERGE, PLATE + 0.12, WHITE)  # fascia
    _r(d, el, -VERGE, PLATE, -VERGE + 0.04, RIDGE_Z, (225, 225, 220))  # bargeboard ends
    _r(d, el, MAIN_W + VERGE - 0.04, PLATE, MAIN_W + VERGE, RIDGE_Z, (225, 225, 220))
    # garage verge (rake) band: outline through the wall corners at plate level, overhang beyond walls
    t = math.tan(math.radians(GAR_PITCH))
    zl = GAR_PLATE - VERGE * t
    outer = [el.pt(GAR_X0 - VERGE, zl), el.pt(GAR_X0 + GAR_W / 2, GAR_APEX_Z), el.pt(GAR_X0 + GAR_W + VERGE, zl)]
    th = 0.16
    inner = [el.pt(GAR_X0 + GAR_W + VERGE, zl - th), el.pt(GAR_X0 + GAR_W / 2, GAR_APEX_Z - th),
             el.pt(GAR_X0 - VERGE, zl - th)]
    rake_tiles = tile_texture(el, rng, z_top=GAR_APEX_Z, row_h=0.05)
    _paste(img, rake_tiles, outer + inner)
    d = ImageDraw.Draw(img)
    d.line([inner[2], inner[1], inner[0]], fill=WHITE, width=4)
    # openings
    for oid, block, kind, storey, off, w, h, sill in FRONT_OPENINGS:
        bx0 = 0.0 if block == "main" else GAR_X0
        x0, z0, w, h = _opening_box(el, bx0, storey, off, w, h, sill)
        if kind == "window":
            draw_window(d, el, x0, z0, w, h)
        elif kind == "door":
            draw_door(d, el, x0, z0, w, h)
        else:
            draw_garage_door(d, el, x0, z0, w, h)
    return img


def render_left_elevation(seed: int = 20261108) -> Image.Image:
    el = LEFT
    rng = np.random.default_rng(seed)
    img = Image.fromarray(sky_and_ground(el, rng), "RGB")
    brick = brick_texture(el, rng)
    plinth = brick_texture(el, rng, base=PLINTH, variation=0.05)
    tiles = tile_texture(el, rng, z_top=RIDGE_Z, row_h=0.05)
    _paste(img, brick, [el.pt(0.0, 0.0), el.pt(0.0, PLATE), el.pt(MAIN_D / 2, RIDGE_Z), el.pt(MAIN_D, PLATE),
                        el.pt(MAIN_D, 0.0)])
    _paste(img, plinth, el.rect(0.0, 0.0, MAIN_D, FFL))
    d = ImageDraw.Draw(img)
    _r(d, el, 0.0, GAR_PLATE, MAIN_D, GAR_PLATE + 0.09, BAND)
    for i in range(int(MAIN_D / 0.075)):
        x = i * 0.075
        d.line([el.pt(x, GAR_PLATE), el.pt(x, GAR_PLATE + 0.09)], fill=MORTAR, width=1)
    t = math.tan(math.radians(MAIN_PITCH))
    zl = PLATE - SIDE_EAVES_OVERHANG * t
    outer = [el.pt(-SIDE_EAVES_OVERHANG, zl), el.pt(MAIN_D / 2, RIDGE_Z), el.pt(MAIN_D + SIDE_EAVES_OVERHANG, zl)]
    th = 0.20
    inner = [el.pt(MAIN_D + SIDE_EAVES_OVERHANG, zl - th), el.pt(MAIN_D / 2, RIDGE_Z - th),
             el.pt(-SIDE_EAVES_OVERHANG, zl - th)]
    _paste(img, tiles, outer + inner)
    d = ImageDraw.Draw(img)
    d.line([inner[2], inner[1], inner[0]], fill=WHITE, width=4)
    for xg in (-SIDE_EAVES_OVERHANG, MAIN_D + SIDE_EAVES_OVERHANG - 0.12):  # gutter ends
        _r(d, el, xg, zl - th - 0.10, xg + 0.12, zl - th, (60, 60, 62))
    for oid, block, kind, storey, off, w, h, sill in LEFT_OPENINGS:
        x0, z0, w, h = _opening_box(el, 0.0, storey, off, w, h, sill)
        draw_window(d, el, x0, z0, w, h)
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


# =============================================================================
# Fixtures
# =============================================================================
class _Noisy:
    def __init__(self, el: Elevation, rng: np.random.Generator) -> None:
        self.el, self.rng = el, rng

    def n(self) -> float:
        return float(self.rng.uniform(-NOISE_PX, NOISE_PX))

    def conf(self) -> float:
        return round(float(self.rng.uniform(0.80, 0.97)), 3)

    def p(self, m: float, z: float) -> list[float]:
        return [round(self.el.X(m) + self.n(), 2), round(self.el.Y(z) + self.n(), 2)]

    def bbox(self, x0: float, z0: float, x1: float, z1: float) -> list[float]:
        return [round(self.el.X(x0) + self.n(), 2), round(self.el.Y(z1) + self.n(), 2),
                round(self.el.X(x1) + self.n(), 2), round(self.el.Y(z0) + self.n(), 2)]

    def line(self, x0: float, z0: float, x1: float, z1: float) -> list[float]:
        return [*self.p(x0, z0), *self.p(x1, z1)]


def _feat(fid: str, ftype: str, nz: _Noisy, *, label: str = "", attrs: Optional[dict] = None,
          **geom: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"feature_id": fid, "feature_type": ftype, "label": label}
    d.update(geom)
    d.update({"confidence": nz.conf(), "pixel_uncertainty": NOISE_PX, "attributes": attrs or {},
              "evidence": EVIDENCE})
    return d


def _opening_features(nz: _Noisy, openings, block_x0: dict[str, float]) -> list[dict[str, Any]]:
    out = []
    for oid, block, kind, storey, off, w, h, sill in openings:
        x0, z0, w, h = _opening_box(nz.el, block_x0[block], storey, off, w, h, sill)
        lbl = {"window": "window", "door": "front door", "garage_door": "garage door"}[kind]
        out.append(_feat(oid, _FT[kind], nz, label=lbl, attrs={"block": block, "storey": storey},
                         bbox=nz.bbox(x0, z0, x0 + w, z0 + h)))
    return out


def front_fixture(image_sha256: str, seed: int = 7) -> DetectionFixture:
    el = FRONT
    nz = _Noisy(el, np.random.default_rng(seed))
    gx1 = GAR_X0 + GAR_W
    t = math.tan(math.radians(GAR_PITCH))
    zl = GAR_PLATE - VERGE * t
    feats = [
        _feat("f01_facade_main", "facade", nz, label="main block facade (walls, ground to wall plate)",
              attrs={"block": "main"}, bbox=nz.bbox(0.0, 0.0, MAIN_W, PLATE)),
        _feat("f02_facade_garage", "facade", nz, label="garage facade (walls, ground to wall plate)",
              attrs={"block": "garage"}, bbox=nz.bbox(GAR_X0, 0.0, gx1, GAR_PLATE)),
        _feat("f03_roof_main", "roof", nz, label="main roof band (eaves to ridge, verges at both ends)",
              attrs={"block": "main", "roof_form": "gable", "ridge_orientation": "parallel_to_view",
                     "gable_visible": False, "verge_overhang_visible": True},
              polygon=[nz.p(-VERGE, PLATE), nz.p(-VERGE, RIDGE_Z), nz.p(MAIN_W + VERGE, RIDGE_Z),
                       nz.p(MAIN_W + VERGE, PLATE)]),
        _feat("f04_roof_garage", "roof", nz, label="garage front gable (roof outline through wall corners)",
              attrs={"block": "garage", "roof_form": "gable", "ridge_orientation": "perpendicular_to_view",
                     "gable_visible": True},
              polygon=[nz.p(GAR_X0, GAR_PLATE), nz.p(GAR_X0 + GAR_W / 2, GAR_APEX_Z), nz.p(gx1, GAR_PLATE)]),
        _feat("f05_eaves_main", "eaves_line", nz, label="main eaves (wall plate)", attrs={"block": "main"},
              line=nz.line(-VERGE, PLATE, MAIN_W + VERGE, PLATE)),
        _feat("f06_eaves_garage", "eaves_line", nz, label="garage wall plate at gable base",
              attrs={"block": "garage"}, line=nz.line(GAR_X0, GAR_PLATE, gx1, GAR_PLATE)),
        _feat("f07_ridge_main", "ridge_line", nz, label="main ridge", attrs={"block": "main"},
              line=nz.line(-VERGE, RIDGE_Z, MAIN_W + VERGE, RIDGE_Z)),
        _feat("f08_ground", "ground_line", nz, label="ground line", line=nz.line(-1.0, 0.0, gx1 + 1.0, 0.0)),
        _feat("f09_storey_main", "storey_line", nz, label="first-floor band", attrs={"block": "main"},
              line=nz.line(0.0, GAR_PLATE, MAIN_W, GAR_PLATE)),
    ]
    feats += _opening_features(nz, FRONT_OPENINGS, {"main": 0.0, "garage": GAR_X0})
    gd = next(o for o in FRONT_OPENINGS if o[0] == "o07")
    gx0, gz0, gw, gh = _opening_box(el, GAR_X0, gd[3], gd[4], gd[5], gd[6], gd[7])
    feats += [
        _feat("r01_walls_main", "finish_region", nz, label="main walls",
              attrs={"block": "main", "element": "walls", "appearance": "red-brown brick-like"},
              bbox=nz.bbox(0.0, 0.0, MAIN_W, PLATE)),
        _feat("r02_walls_garage", "finish_region", nz, label="garage walls",
              attrs={"block": "garage", "element": "walls", "appearance": "red-brown brick-like"},
              bbox=nz.bbox(GAR_X0, 0.0, gx1, GAR_APEX_Z)),
        _feat("r03_roof_main", "finish_region", nz, label="main roof covering",
              attrs={"block": "main", "element": "roof", "appearance": "dark grey tile-like"},
              bbox=nz.bbox(-VERGE, PLATE, MAIN_W + VERGE, RIDGE_Z)),
        _feat("r04_roof_garage", "finish_region", nz, label="garage verge tiles",
              attrs={"block": "garage", "element": "roof", "appearance": "dark grey tile-like"},
              polygon=[nz.p(GAR_X0 - VERGE, zl), nz.p(GAR_X0 + GAR_W / 2, GAR_APEX_Z),
                       nz.p(gx1 + VERGE, zl), nz.p(gx1 + VERGE, zl - 0.16),
                       nz.p(GAR_X0 + GAR_W / 2, GAR_APEX_Z - 0.16), nz.p(GAR_X0 - VERGE, zl - 0.16)]),
        _feat("r05_garage_door", "finish_region", nz, label="garage door",
              attrs={"block": "garage", "element": "garage_door", "appearance": "white panel-like"},
              bbox=nz.bbox(gx0, gz0, gx0 + gw, gz0 + gh)),
    ]
    segs = [(0.0, 0.2, 0.0, 5.4), (MAIN_W, 3.0, MAIN_W, 5.4), (gx1, 0.2, gx1, 2.7), (4.3, 0.2, 4.3, 2.2),
            (5.3, 0.2, 5.3, 2.2), (0.0, 0.0, gx1, 0.0), (-VERGE, PLATE, MAIN_W + VERGE, PLATE),
            (-VERGE, RIDGE_Z, MAIN_W + VERGE, RIDGE_Z), (0.0, GAR_PLATE, MAIN_W, GAR_PLATE)]
    for k, s in enumerate(segs, start=1):
        feats.append(_feat(f"l{k:02d}", "line_segment", nz, label="straight edge", line=nz.line(*s)))
    plines = []
    for oid, block, kind, storey, off, w, h, sill in FRONT_OPENINGS:
        x0, z0, w, h = _opening_box(el, 0.0 if block == "main" else GAR_X0, storey, off, w, h, sill)
        plines += [nz.line(x0, z0, x0, z0 + h), nz.line(x0 + w, z0, x0 + w, z0 + h),
                   nz.line(x0, z0 + h, x0 + w, z0 + h)]
        if kind == "window":
            plines.append(nz.line(x0, z0, x0 + w, z0))
    return DetectionFixture.model_validate({
        "schema_version": "1.0", "fixture_key": FRONT_KEY, "image_sha256": image_sha256,
        "width_px": el.width_px, "height_px": el.height_px, "detector": DETECTOR,
        "description": ("Synthetic detections for the Aureom Demo House (fictional) front elevation, as an element "
                        "detector would emit them."),
        "image_attributes": {"image_kind_hint": "synthetic_elevation_drawing", "fictional": True},
        "features": feats, "perspective_lines": plines,
        "notes": ["Fictional demonstration data.",
                  "Facade boxes cover the wall zone from ground to wall plate; roof outlines are separate features."],
    })


def left_fixture(image_sha256: str, seed: int = 8) -> DetectionFixture:
    el = LEFT
    nz = _Noisy(el, np.random.default_rng(seed))
    t = math.tan(math.radians(MAIN_PITCH))
    zl = PLATE - SIDE_EAVES_OVERHANG * t
    feats = [
        _feat("f01_facade_main", "facade", nz, label="main block gable-end wall (ground to wall plate)",
              attrs={"block": "main"}, bbox=nz.bbox(0.0, 0.0, MAIN_D, PLATE)),
        _feat("f02_roof_main", "roof", nz, label="main gable (roof outline through wall corners)",
              attrs={"block": "main", "roof_form": "gable", "ridge_orientation": "perpendicular_to_view",
                     "gable_visible": True},
              polygon=[nz.p(0.0, PLATE), nz.p(MAIN_D / 2, RIDGE_Z), nz.p(MAIN_D, PLATE)]),
        _feat("f03_eaves_main", "eaves_line", nz, label="wall plate at gable base", attrs={"block": "main"},
              line=nz.line(0.0, PLATE, MAIN_D, PLATE)),
        _feat("f04_ridge_main", "ridge_line", nz, label="ridge end at gable apex", attrs={"block": "main"},
              line=nz.line(MAIN_D / 2 - 0.15, RIDGE_Z, MAIN_D / 2 + 0.15, RIDGE_Z)),
        _feat("f05_ground", "ground_line", nz, label="ground line", line=nz.line(-1.0, 0.0, MAIN_D + 1.0, 0.0)),
        _feat("f06_storey_main", "storey_line", nz, label="first-floor band", attrs={"block": "main"},
              line=nz.line(0.0, GAR_PLATE, MAIN_D, GAR_PLATE)),
    ]
    feats += _opening_features(nz, LEFT_OPENINGS, {"main": 0.0})
    feats += [
        _feat("r01_walls_main", "finish_region", nz, label="gable wall",
              attrs={"block": "main", "element": "walls", "appearance": "red-brown brick-like"},
              bbox=nz.bbox(0.0, 0.0, MAIN_D, RIDGE_Z)),
        _feat("r02_roof_main", "finish_region", nz, label="verge tiles",
              attrs={"block": "main", "element": "roof", "appearance": "dark grey tile-like"},
              polygon=[nz.p(-SIDE_EAVES_OVERHANG, zl), nz.p(MAIN_D / 2, RIDGE_Z),
                       nz.p(MAIN_D + SIDE_EAVES_OVERHANG, zl), nz.p(MAIN_D + SIDE_EAVES_OVERHANG, zl - 0.2),
                       nz.p(MAIN_D / 2, RIDGE_Z - 0.2), nz.p(-SIDE_EAVES_OVERHANG, zl - 0.2)]),
    ]
    segs = [(0.0, 0.2, 0.0, 5.4), (MAIN_D, 0.2, MAIN_D, 5.4), (0.0, 0.0, MAIN_D, 0.0), (0.0, PLATE, MAIN_D, PLATE),
            (0.0, GAR_PLATE, MAIN_D, GAR_PLATE)]
    for k, s in enumerate(segs, start=1):
        feats.append(_feat(f"l{k:02d}", "line_segment", nz, label="straight edge", line=nz.line(*s)))
    plines = []
    for oid, block, kind, storey, off, w, h, sill in LEFT_OPENINGS:
        x0, z0, w, h = _opening_box(el, 0.0, storey, off, w, h, sill)
        plines += [nz.line(x0, z0, x0, z0 + h), nz.line(x0 + w, z0, x0 + w, z0 + h),
                   nz.line(x0, z0 + h, x0 + w, z0 + h), nz.line(x0, z0, x0 + w, z0)]
    return DetectionFixture.model_validate({
        "schema_version": "1.0", "fixture_key": LEFT_KEY, "image_sha256": image_sha256,
        "width_px": el.width_px, "height_px": el.height_px, "detector": DETECTOR,
        "description": "Synthetic detections for the Aureom Demo House (fictional) left (gable-end) elevation.",
        "image_attributes": {"image_kind_hint": "synthetic_elevation_drawing", "fictional": True},
        "features": feats, "perspective_lines": plines,
        "notes": ["Fictional demonstration data.", "The garage (right of the main block) is not visible in this view."],
    })


#: Approximate manual annotations of the 1200 px concept JPEG (x0, y0, x1, y1 / polygons in px).
_CONCEPT_FEATURES: list[dict[str, Any]] = [
    {"feature_id": "c01_facade_main", "feature_type": "facade",
     "label": "two-storey main mass: left wing, glazed centre, right wing", "bbox": [190, 168, 1118, 450],
     "attributes": {"block": "main"}},
    {"feature_id": "c02_facade_garage", "feature_type": "facade", "label": "single-storey garage wing",
     "bbox": [77, 320, 372, 456], "attributes": {"block": "garage"}},
    {"feature_id": "c03_roof_left", "feature_type": "roof", "label": "left wing low-pitch hipped roof",
     "polygon": [[135, 205], [168, 172], [455, 170], [505, 218]],
     "attributes": {"block": "main", "roof_form": "hip", "pitch_hint": "low", "gable_visible": False}},
    {"feature_id": "c04_roof_centre", "feature_type": "roof", "label": "glazed centre low-pitch hipped roof",
     "polygon": [[452, 197], [540, 140], [845, 145], [907, 187]],
     "attributes": {"block": "main", "roof_form": "hip", "pitch_hint": "low", "gable_visible": False}},
    {"feature_id": "c05_roof_right", "feature_type": "roof", "label": "right wing low-pitch hipped roof",
     "polygon": [[852, 246], [860, 215], [1060, 232], [1140, 266]],
     "attributes": {"block": "main", "roof_form": "hip", "pitch_hint": "low", "gable_visible": False}},
    {"feature_id": "c06_roof_garage", "feature_type": "roof", "label": "garage low-pitch hipped roof",
     "polygon": [[42, 322], [75, 281], [358, 279], [392, 322]],
     "attributes": {"block": "garage", "roof_form": "hip", "pitch_hint": "low", "gable_visible": False}},
    {"feature_id": "c07_ground", "feature_type": "ground_line", "label": "ground / terrace line",
     "line": [60, 457, 1190, 446]},
    {"feature_id": "w01", "feature_type": "window", "bbox": [235, 209, 345, 285], "attributes": {"block": "main", "storey": 1}},
    {"feature_id": "w02", "feature_type": "window", "bbox": [381, 219, 454, 292], "attributes": {"block": "main", "storey": 1}},
    {"feature_id": "w03", "feature_type": "window", "label": "curtain-wall glazing (upper part)",
     "bbox": [548, 172, 842, 292], "attributes": {"block": "main", "storey": 1}},
    {"feature_id": "w04", "feature_type": "window", "bbox": [857, 251, 924, 311], "attributes": {"block": "main", "storey": 1}},
    {"feature_id": "w05", "feature_type": "window", "bbox": [958, 259, 1018, 316], "attributes": {"block": "main", "storey": 1}},
    {"feature_id": "w06", "feature_type": "window", "bbox": [1048, 266, 1108, 321], "attributes": {"block": "main", "storey": 1}},
    {"feature_id": "w07", "feature_type": "window", "bbox": [380, 343, 454, 421], "attributes": {"block": "main", "storey": 0}},
    {"feature_id": "w08", "feature_type": "window", "label": "curtain-wall glazing (lower part)",
     "bbox": [655, 320, 845, 445], "attributes": {"block": "main", "storey": 0}},
    {"feature_id": "d01", "feature_type": "door", "label": "glazed entrance door", "bbox": [575, 350, 618, 447],
     "attributes": {"block": "main", "storey": 0}},
    {"feature_id": "d02", "feature_type": "door", "label": "sliding glazed doors to terrace",
     "bbox": [857, 345, 1110, 445], "attributes": {"block": "main", "storey": 0, "kind": "patio_door"}},
    {"feature_id": "g01", "feature_type": "garage_door", "label": "garage door", "bbox": [118, 351, 336, 456],
     "attributes": {"block": "garage", "storey": 0}},
    {"feature_id": "r01_walls_left", "feature_type": "finish_region", "bbox": [190, 200, 500, 450],
     "attributes": {"block": "main", "element": "walls", "appearance": "light horizontal board cladding-like"}},
    {"feature_id": "r02_walls_right", "feature_type": "finish_region", "bbox": [854, 245, 1117, 345],
     "attributes": {"block": "main", "element": "walls", "appearance": "light horizontal board cladding-like"}},
    {"feature_id": "r03_roof_main", "feature_type": "finish_region", "bbox": [452, 140, 907, 197],
     "attributes": {"block": "main", "element": "roof", "appearance": "dark grey standing-seam metal-like"}},
    {"feature_id": "r04_roof_garage", "feature_type": "finish_region", "bbox": [42, 279, 392, 322],
     "attributes": {"block": "garage", "element": "roof", "appearance": "dark grey standing-seam metal-like"}},
    {"feature_id": "r05_garage_door", "feature_type": "finish_region", "bbox": [118, 351, 336, 456],
     "attributes": {"block": "garage", "element": "garage_door", "appearance": "dark grey flush panel-like"}},
    {"feature_id": "r06_glazing", "feature_type": "finish_region", "bbox": [548, 172, 842, 445],
     "attributes": {"block": "main", "element": "windows", "appearance": "black-framed glazing-like"}},
]


def concept_fixture(image_sha256: str, width_px: int, height_px: int) -> DetectionFixture:
    feats = []
    for f in _CONCEPT_FEATURES:
        d = dict(f)
        d.setdefault("label", f["feature_type"].replace("_", " "))
        d["confidence"] = 0.6
        d["pixel_uncertainty"] = 6.0
        d["method"] = MANUAL["name"]
        attrs = dict(d.get("attributes", {}))
        attrs["source_image"] = "ai_generated_concept"
        d["attributes"] = attrs
        d["evidence"] = ("Approximate manual annotation of an AI-generated concept render (low confidence); "
                         "describes the concept image, not a real building.")
        feats.append(d)
    return DetectionFixture.model_validate({
        "schema_version": "1.0", "fixture_key": CONCEPT_KEY, "image_sha256": image_sha256,
        "width_px": width_px, "height_px": height_px, "detector": MANUAL,
        "description": "Approximate manual annotations of an AI-generated house render used as a concept reference.",
        "image_attributes": {"image_kind_hint": "ai_generated_concept",
                             "source_note": "AI-generated house render supplied as a design concept; not a "
                                            "photograph or a measured drawing of a real building.",
                             "annotation_quality": "approximate manual annotation, low confidence"},
        "features": feats,
        "notes": ["Concept reference: geometry may be internally inconsistent; dimensions indicative only."],
    })


# =============================================================================
# Writing
# =============================================================================
def _write_if_changed(path: Path, data: bytes) -> bool:
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _write_fixture(fixture_dir: Path, fx: DetectionFixture) -> Path:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    target = fixture_dir / f"{fx.image_sha256}.json"
    for old in sorted(fixture_dir.glob("*.json")):  # remove stale fixtures for the same key only
        if old == target:
            continue
        try:
            if json.loads(old.read_text(encoding="utf-8")).get("fixture_key") == fx.fixture_key:
                old.unlink()
        except (OSError, ValueError):
            continue
    text = json.dumps(fx.model_dump(mode="json", exclude_none=True), indent=1, ensure_ascii=True) + "\n"
    _write_if_changed(target, text.encode("utf-8"))
    return target


def _concept_jpeg(source: Path) -> bytes:
    with Image.open(source) as src:
        im = src.convert("RGB")
    w, h = im.size
    nw = 1200
    nh = int(round(h * nw / w))
    im = im.resize((nw, nh), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def build_assets(out_dir: Path | str = DATA_DIR, *, concept_source: Optional[Path | str] = DEFAULT_CONCEPT_SOURCE,
                 verbose: bool = False) -> dict[str, Path]:
    """Render images and write fixtures into ``out_dir`` (``out_dir/fixtures``)."""
    out = Path(out_dir)
    fdir = out / "fixtures"
    paths: dict[str, Path] = {}
    for name, render, fixture in ((FRONT_NAME, render_front_elevation, front_fixture),
                                  (LEFT_NAME, render_left_elevation, left_fixture)):
        data = png_bytes(render())
        p = out / name
        changed = _write_if_changed(p, data)
        sha = hashlib.sha256(data).hexdigest()
        paths[name] = p
        paths[name + ".fixture"] = _write_fixture(fdir, fixture(sha))
        if verbose:
            print(f"{name}: sha256 {sha} ({'written' if changed else 'unchanged'})")
    cpath = out / CONCEPT_NAME
    src = Path(concept_source) if concept_source else None
    if src is not None and src.is_file():
        _write_if_changed(cpath, _concept_jpeg(src))
    elif verbose:
        print(f"concept source not found ({src}); keeping existing {CONCEPT_NAME} if present")
    if cpath.is_file():
        data = cpath.read_bytes()
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
        paths[CONCEPT_NAME] = cpath
        paths[CONCEPT_NAME + ".fixture"] = _write_fixture(fdir, concept_fixture(hashlib.sha256(data).hexdigest(), w, h))
        if verbose:
            print(f"{CONCEPT_NAME}: sha256 {hashlib.sha256(data).hexdigest()} ({w}x{h})")
    return paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DATA_DIR), help="output data directory")
    ap.add_argument("--concept-source", default=str(DEFAULT_CONCEPT_SOURCE), help="AI concept render (PNG/JPEG)")
    ap.add_argument("--check", action="store_true",
                    help="regenerate into a temporary directory and compare with --out (exit 1 on difference)")
    args = ap.parse_args(argv)
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_assets(tmp, concept_source=args.concept_source)
            bad = []
            for key, p in paths.items():
                ref = Path(args.out) / Path(p).relative_to(tmp)
                if not ref.is_file() or ref.read_bytes() != Path(p).read_bytes():
                    bad.append(str(ref))
            if bad:
                print("differs: " + ", ".join(bad))
                return 1
            print("demo assets are up to date")
            return 0
    build_assets(args.out, concept_source=args.concept_source, verbose=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
