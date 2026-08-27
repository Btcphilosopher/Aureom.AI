"""3D LUT loading (.cube format) and trilinear application."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class LUT3D:
    """A cubic 3D lookup table: ``table`` has shape (size, size, size, 3)."""

    size: int
    table: np.ndarray
    title: str = "Untitled LUT"

    @classmethod
    def identity(cls, size: int = 17) -> "LUT3D":
        axis = np.linspace(0.0, 1.0, size)
        r, g, b = np.meshgrid(axis, axis, axis, indexing="ij")
        table = np.stack([r, g, b], axis=-1)
        return cls(size=size, table=table, title="Identity")

    @classmethod
    def from_cube_file(cls, path: Path) -> "LUT3D":
        size = None
        title = path.stem
        values: list[list[float]] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.upper().startswith("TITLE"):
                title = line.split(None, 1)[1].strip().strip('"')
            elif line.upper().startswith("LUT_3D_SIZE"):
                size = int(line.split()[1])
            elif line.upper().startswith(("DOMAIN_MIN", "DOMAIN_MAX")):
                continue
            else:
                values.append([float(v) for v in line.split()])
        if size is None:
            raise ValueError(f"{path}: missing LUT_3D_SIZE")
        arr = np.array(values, dtype=np.float64)
        if len(arr) != size**3:
            raise ValueError(f"{path}: expected {size**3} rows, got {len(arr)}")
        # .cube files are ordered with the red index fastest-varying.
        table = arr.reshape(size, size, size, 3, order="F")
        return cls(size=size, table=table, title=title)

    def to_cube_text(self) -> str:
        lines = [f'TITLE "{self.title}"', f"LUT_3D_SIZE {self.size}"]
        flat = self.table.reshape(-1, 3, order="F")
        lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in flat]
        return "\n".join(lines) + "\n"

    def apply(self, image: np.ndarray) -> np.ndarray:
        """Trilinear interpolation. ``image``: float array in [0, 1], shape (..., 3)."""
        scaled = np.clip(image.astype(np.float64), 0.0, 1.0) * (self.size - 1)
        i0 = np.floor(scaled).astype(np.int64)
        i1 = np.clip(i0 + 1, 0, self.size - 1)
        frac = scaled - i0

        r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
        r1, g1, b1 = i1[..., 0], i1[..., 1], i1[..., 2]
        fr, fg, fb = frac[..., 0:1], frac[..., 1:2], frac[..., 2:3]

        def sample(ri, gi, bi):
            return self.table[ri, gi, bi]

        c000, c001 = sample(r0, g0, b0), sample(r0, g0, b1)
        c010, c011 = sample(r0, g1, b0), sample(r0, g1, b1)
        c100, c101 = sample(r1, g0, b0), sample(r1, g0, b1)
        c110, c111 = sample(r1, g1, b0), sample(r1, g1, b1)

        c00 = c000 * (1 - fb) + c001 * fb
        c01 = c010 * (1 - fb) + c011 * fb
        c10 = c100 * (1 - fb) + c101 * fb
        c11 = c110 * (1 - fb) + c111 * fb

        c0 = c00 * (1 - fg) + c01 * fg
        c1 = c10 * (1 - fg) + c11 * fg

        return np.clip(c0 * (1 - fr) + c1 * fr, 0.0, 1.0)
