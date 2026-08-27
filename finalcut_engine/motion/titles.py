"""Title generation: positioned, animatable text composited over a background.

Real glyph rasterisation is deliberately behind a small ``GlyphRenderer``
interface rather than a hand-rolled pixel font baked into this module — the
spec's own principle ("don't pretend a pure-Python implementation provides
hardware acceleration it doesn't have") applies just as much to typography:
faking pixel-perfect glyph shapes here would be worse than being explicit
about the gap. :class:`BlockGlyphRenderer` is a correct-by-construction
placeholder (real 7-segment digits, word-shaped blocks for letters) good
enough to test layout, timing, and compositing; a native build swaps in a
Core Text-backed renderer with zero changes to :class:`Title`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Tuple

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.effects.compositing import composite
from finalcut_engine.motion.keyframes import KeyframeTrack

# Standard 7-segment layout: (a, b, c, d, e, f, g) = (top, top-right, bottom-right,
# bottom, bottom-left, top-left, middle).
_SEVEN_SEGMENT = {
    "0": "abcdef",
    "1": "bc",
    "2": "abged",
    "3": "abgcd",
    "4": "fgbc",
    "5": "afgcd",
    "6": "afgecd",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
}


def _draw_segment_digit(cell: np.ndarray, digit: str, colour: np.ndarray) -> None:
    h, w = cell.shape[:2]
    thickness = max(1, h // 8)
    segs = _SEVEN_SEGMENT.get(digit, "")
    mid = h // 2
    if "a" in segs:
        cell[0:thickness, :] = colour
    if "g" in segs:
        cell[mid - thickness // 2 : mid + thickness // 2, :] = colour
    if "d" in segs:
        cell[h - thickness :, :] = colour
    if "f" in segs:
        cell[0:mid, 0:thickness] = colour
    if "b" in segs:
        cell[0:mid, w - thickness :] = colour
    if "e" in segs:
        cell[mid:h, 0:thickness] = colour
    if "c" in segs:
        cell[mid:h, w - thickness :] = colour


class GlyphRenderer(Protocol):
    def render_text(self, text: str, colour: Tuple[float, float, float]) -> np.ndarray:
        """Returns an RGBA float image (H, W, 4) with the rendered text, alpha-premultiplied."""


@dataclass
class BlockGlyphRenderer:
    cell_width: int = 24
    cell_height: int = 36

    def render_text(self, text: str, colour: Tuple[float, float, float] = (1.0, 1.0, 1.0)) -> np.ndarray:
        cw, ch = self.cell_width, self.cell_height
        canvas = np.zeros((ch, max(1, cw * len(text)), 4), dtype=np.float64)
        col = np.array(colour, dtype=np.float64)
        for i, char in enumerate(text):
            cell_rgb = np.zeros((ch, cw, 3), dtype=np.float64)
            cell_alpha = np.zeros((ch, cw), dtype=np.float64)
            if char == " ":
                pass
            elif char.isdigit():
                _draw_segment_digit(cell_rgb, char, col)
                cell_alpha[:] = cell_rgb.sum(axis=-1) > 0
            else:
                # Legible "word-shape" placeholder: a proportionally sized block
                # per glyph, rather than an incorrect hand-drawn letterform.
                pad_x, pad_y = cw // 6, ch // 5
                cell_rgb[pad_y : ch - pad_y, pad_x : cw - pad_x] = col
                cell_alpha[pad_y : ch - pad_y, pad_x : cw - pad_x] = 1.0
            canvas[:, i * cw : (i + 1) * cw, :3] = cell_rgb
            canvas[:, i * cw : (i + 1) * cw, 3] = cell_alpha
        return canvas


@dataclass
class Title:
    text: str
    colour: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    position: Tuple[float, float] = (0.5, 0.85)  # normalised anchor point (lower-third default)
    renderer: GlyphRenderer = field(default_factory=BlockGlyphRenderer)
    opacity_track: KeyframeTrack = field(default_factory=lambda: KeyframeTrack(default=1.0))

    def opacity_at(self, t: Time) -> float:
        return float(self.opacity_track.value_at(t))

    def render_onto(self, background: np.ndarray, t: Time) -> np.ndarray:
        glyphs = self.renderer.render_text(self.text, self.colour)
        gh, gw = glyphs.shape[:2]
        bh, bw = background.shape[:2]

        x0 = int(self.position[0] * bw - gw / 2)
        y0 = int(self.position[1] * bh - gh / 2)

        out = background.astype(np.float64).copy()
        x_start, x_end = max(0, x0), min(bw, x0 + gw)
        y_start, y_end = max(0, y0), min(bh, y0 + gh)
        if x_start >= x_end or y_start >= y_end:
            return out

        gx0, gy0 = x_start - x0, y_start - y0
        region = glyphs[gy0 : gy0 + (y_end - y_start), gx0 : gx0 + (x_end - x_start)]
        alpha = region[..., 3] * self.opacity_at(t)

        out[y_start:y_end, x_start:x_end] = composite(
            out[y_start:y_end, x_start:x_end], region[..., :3], opacity=1.0, mask=alpha
        )
        return out
