"""Exact rectilinear footprint operations on unions of axis-aligned rectangles.

Footprints are composed of non-overlapping rectangular blocks (rectangle,
L-shape, simple composites).  This module computes, without approximation:

* the outline split into *pieces*, each either external or shared with exactly
  one neighbouring block (so shared walls are never counted twice);
* union areas via coordinate compression;
* internal (GIA-style) areas by subtracting wall strips of given thickness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np

from ..core.models import Side

TOL = 1e-6


class GeometryError(ValueError):
    pass


@dataclass(frozen=True)
class Rect:
    rid: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def depth(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.depth

    def side_coord(self, side: Side) -> float:
        return {Side.FRONT: self.y0, Side.REAR: self.y1, Side.LEFT: self.x0, Side.RIGHT: self.x1}[side]

    def side_range(self, side: Side) -> tuple[float, float]:
        if side in (Side.FRONT, Side.REAR):
            return self.x0, self.x1
        return self.y0, self.y1

    def side_length(self, side: Side) -> float:
        a, b = self.side_range(side)
        return b - a


@dataclass(frozen=True)
class Piece:
    """A portion of one block side with uniform exposure."""

    rid: str
    side: Side
    a: float  # start coordinate along the side axis (x for FRONT/REAR, y for LEFT/RIGHT)
    b: float
    coord: float  # fixed coordinate (y for FRONT/REAR, x for LEFT/RIGHT)
    neighbour: Optional[str]

    @property
    def length(self) -> float:
        return self.b - self.a

    @property
    def external(self) -> bool:
        return self.neighbour is None

    def endpoints(self) -> tuple[float, float, float, float]:
        if self.side in (Side.FRONT, Side.REAR):
            return self.a, self.coord, self.b, self.coord
        return self.coord, self.a, self.coord, self.b


_OPPOSITE = {Side.FRONT: Side.REAR, Side.REAR: Side.FRONT, Side.LEFT: Side.RIGHT, Side.RIGHT: Side.LEFT}


def opposite(side: Side) -> Side:
    return _OPPOSITE[side]


def validate_rects(rects: Sequence[Rect]) -> list[str]:
    """Raise on degenerate/overlapping rectangles; return connectivity warnings."""
    ids = [r.rid for r in rects]
    if len(set(ids)) != len(ids):
        raise GeometryError("duplicate block ids")
    for r in rects:
        if r.width <= TOL or r.depth <= TOL:
            raise GeometryError(f"block '{r.rid}' has non-positive width or depth")
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            ox = min(a.x1, b.x1) - max(a.x0, b.x0)
            oy = min(a.y1, b.y1) - max(a.y0, b.y0)
            if ox > TOL and oy > TOL:
                raise GeometryError(
                    f"blocks '{a.rid}' and '{b.rid}' overlap by {ox:.3f} x {oy:.3f} m; "
                    "composite footprints must be made of non-overlapping blocks")
    warnings: list[str] = []
    if len(rects) > 1:
        # connectivity through shared edges
        adj = {r.rid: set() for r in rects}
        for p in side_pieces(rects, _validated=True):
            if p.neighbour:
                adj[p.rid].add(p.neighbour)
        seen = {rects[0].rid}
        stack = [rects[0].rid]
        while stack:
            for n in adj[stack.pop()]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        if len(seen) != len(rects):
            warnings.append("Footprint blocks are not all connected by shared walls; treated as detached volumes.")
    return warnings


def _touching(r: Rect, s: Rect, side: Side) -> bool:
    """True if ``s`` abuts ``r`` along ``side`` of ``r`` with positive overlap."""
    if side == Side.FRONT:
        ok = abs(s.y1 - r.y0) < TOL
        ov = min(r.x1, s.x1) - max(r.x0, s.x0)
    elif side == Side.REAR:
        ok = abs(s.y0 - r.y1) < TOL
        ov = min(r.x1, s.x1) - max(r.x0, s.x0)
    elif side == Side.LEFT:
        ok = abs(s.x1 - r.x0) < TOL
        ov = min(r.y1, s.y1) - max(r.y0, s.y0)
    else:
        ok = abs(s.x0 - r.x1) < TOL
        ov = min(r.y1, s.y1) - max(r.y0, s.y0)
    return ok and ov > TOL


def side_pieces(rects: Sequence[Rect], _validated: bool = False) -> list[Piece]:
    """Split every block side into external / shared pieces."""
    if not _validated:
        validate_rects(rects)
    pieces: list[Piece] = []
    for r in rects:
        for side in (Side.FRONT, Side.RIGHT, Side.REAR, Side.LEFT):
            a0, b0 = r.side_range(side)
            nbrs = [s for s in rects if s.rid != r.rid and _touching(r, s, side)]
            cuts = {a0, b0}
            for s in nbrs:
                sa, sb = s.side_range(opposite(side))
                for c in (sa, sb):
                    if a0 + TOL < c < b0 - TOL:
                        cuts.add(c)
            cs = sorted(cuts)
            for a, b in zip(cs[:-1], cs[1:]):
                if b - a <= TOL:
                    continue
                m = 0.5 * (a + b)
                nb = None
                for s in nbrs:
                    sa, sb = s.side_range(opposite(side))
                    if sa - TOL <= m <= sb + TOL:
                        nb = s.rid
                        break
                pieces.append(Piece(r.rid, side, a, b, r.side_coord(side), nb))
    return pieces


def union_area(rects: Iterable[tuple[float, float, float, float]]) -> float:
    """Exact area of a union of axis-aligned rectangles (x0, y0, x1, y1)."""
    rs = [r for r in rects if r[2] - r[0] > TOL and r[3] - r[1] > TOL]
    if not rs:
        return 0.0
    xs = np.unique(np.array([v for r in rs for v in (r[0], r[2])], dtype=float))
    ys = np.unique(np.array([v for r in rs for v in (r[1], r[3])], dtype=float))
    covered = np.zeros((len(xs) - 1, len(ys) - 1), dtype=bool)
    for x0, y0, x1, y1 in rs:
        i0, i1 = np.searchsorted(xs, x0), np.searchsorted(xs, x1)
        j0, j1 = np.searchsorted(ys, y0), np.searchsorted(ys, y1)
        covered[i0:i1, j0:j1] = True
    dx = np.diff(xs)[:, None]
    dy = np.diff(ys)[None, :]
    return float((covered * dx * dy).sum())


def wall_strip(p: Piece, rect: Rect, thickness: float) -> tuple[float, float, float, float]:
    """Inward strip of ``thickness`` along piece ``p`` inside ``rect``."""
    t = max(0.0, thickness)
    if p.side == Side.FRONT:
        return p.a, rect.y0, p.b, min(rect.y1, rect.y0 + t)
    if p.side == Side.REAR:
        return p.a, max(rect.y0, rect.y1 - t), p.b, rect.y1
    if p.side == Side.LEFT:
        return rect.x0, p.a, min(rect.x1, rect.x0 + t), p.b
    return max(rect.x0, rect.x1 - t), p.a, rect.x1, p.b


def internal_area(rect: Rect, pieces: Sequence[Piece], ext_t: float, shared_t: float) -> float:
    """Area of ``rect`` inside its walls: external pieces lose ``ext_t``, shared pieces lose
    half of ``shared_t`` (the other half belongs to the neighbouring block)."""
    strips = []
    for p in pieces:
        if p.rid != rect.rid:
            continue
        t = ext_t if p.external else 0.5 * shared_t
        strips.append(wall_strip(p, rect, t))
    return max(0.0, rect.area - union_area(strips))


def outline_corners(rect: Rect, pieces: Sequence[Piece]) -> dict[tuple[Side, Side], bool]:
    """For each block corner, whether both adjoining end pieces are external."""
    own = [p for p in pieces if p.rid == rect.rid]

    def end_external(side: Side, at_start: bool) -> bool:
        ps = sorted((p for p in own if p.side == side), key=lambda p: p.a)
        if not ps:
            return False
        return (ps[0] if at_start else ps[-1]).external

    return {
        (Side.FRONT, Side.LEFT): end_external(Side.FRONT, True) and end_external(Side.LEFT, True),
        (Side.FRONT, Side.RIGHT): end_external(Side.FRONT, False) and end_external(Side.RIGHT, True),
        (Side.REAR, Side.LEFT): end_external(Side.REAR, True) and end_external(Side.LEFT, False),
        (Side.REAR, Side.RIGHT): end_external(Side.REAR, False) and end_external(Side.RIGHT, False),
    }


def overhang_regions(rect: Rect, pieces: Sequence[Piece], overhang: dict[Side, float]) -> list[tuple[float, float, float, float]]:
    """Plan rectangles making up a block's roof: the block plus outward strips over
    external pieces and corner squares at fully external corners."""
    regs = [(rect.x0, rect.y0, rect.x1, rect.y1)]
    for p in pieces:
        if p.rid != rect.rid or not p.external:
            continue
        o = overhang.get(p.side, 0.0)
        if o <= TOL:
            continue
        if p.side == Side.FRONT:
            regs.append((p.a, rect.y0 - o, p.b, rect.y0))
        elif p.side == Side.REAR:
            regs.append((p.a, rect.y1, p.b, rect.y1 + o))
        elif p.side == Side.LEFT:
            regs.append((rect.x0 - o, p.a, rect.x0, p.b))
        else:
            regs.append((rect.x1, p.a, rect.x1 + o, p.b))
    for (s1, s2), ext in outline_corners(rect, pieces).items():
        if not ext:
            continue
        oy = overhang.get(s1, 0.0)
        ox = overhang.get(s2, 0.0)
        if ox <= TOL or oy <= TOL:
            continue
        x0, x1 = (rect.x0 - ox, rect.x0) if s2 == Side.LEFT else (rect.x1, rect.x1 + ox)
        y0, y1 = (rect.y0 - oy, rect.y0) if s1 == Side.FRONT else (rect.y1, rect.y1 + oy)
        regs.append((x0, y0, x1, y1))
    return regs


def allocate_plan_areas(regions: dict[str, list[tuple[float, float, float, float]]],
                        footprints: dict[str, tuple[float, float, float, float]],
                        priority: Sequence[str]) -> dict[str, float]:
    """Exactly partition the union of all roof regions between blocks.

    Footprint cells belong to their own block; remaining overhang cells go to the
    first block in ``priority`` whose region covers them (no double counting
    where overhangs meet at re-entrant corners).
    """
    allr = [r for rs in regions.values() for r in rs] + list(footprints.values())
    if not allr:
        return {}
    xs = np.unique(np.array([v for r in allr for v in (r[0], r[2])], dtype=float))
    ys = np.unique(np.array([v for r in allr for v in (r[1], r[3])], dtype=float))
    owner = -np.ones((len(xs) - 1, len(ys) - 1), dtype=int)
    order = list(priority)

    def paint(rect, idx, only_empty=True):
        x0, y0, x1, y1 = rect
        i0, i1 = np.searchsorted(xs, x0), np.searchsorted(xs, x1)
        j0, j1 = np.searchsorted(ys, y0), np.searchsorted(ys, y1)
        sub = owner[i0:i1, j0:j1]
        if only_empty:
            sub[sub < 0] = idx
        else:
            sub[:] = idx

    for bid, fp in footprints.items():
        paint(fp, order.index(bid), only_empty=False)
    for bid in order:
        for r in regions.get(bid, []):
            paint(r, order.index(bid), only_empty=True)
    cell = np.diff(xs)[:, None] * np.diff(ys)[None, :]
    return {bid: float(cell[owner == k].sum()) for k, bid in enumerate(order)}
