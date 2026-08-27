"""Thumbnail generation and a dependency-free image writer.

A native build decodes one frame via AVAssetImageGenerator and downsamples on
the GPU; this prototype implementation works directly on decoded numpy frame
buffers so the same call sites work in both worlds.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


class ThumbnailGenerator:
    def __init__(self, size: tuple[int, int] = (160, 90)) -> None:
        self.size = size

    def generate(self, frame: np.ndarray) -> np.ndarray:
        """Nearest-neighbour downsample of an HxWx3 uint8 frame to ``self.size``."""
        target_w, target_h = self.size
        src_h, src_w = frame.shape[:2]
        row_idx = (np.arange(target_h) * src_h / target_h).astype(np.int64)
        col_idx = (np.arange(target_w) * src_w / target_w).astype(np.int64)
        return frame[row_idx][:, col_idx]

    def save_ppm(self, frame: np.ndarray, path: Path) -> Path:
        """Write a P6 PPM file — trivially decodable without an imaging library."""
        h, w = frame.shape[:2]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
            f.write(np.ascontiguousarray(frame[:, :, :3], dtype=np.uint8).tobytes())
        return path

    def contact_sheet(self, frames: list[np.ndarray], columns: int = 4) -> np.ndarray:
        """Tile several thumbnails into one contact-sheet image, filmstrip-style."""
        thumbs = [self.generate(f) for f in frames]
        rows = (len(thumbs) + columns - 1) // columns
        th, tw = self.size[1], self.size[0]
        sheet = np.zeros((rows * th, columns * tw, 3), dtype=np.uint8)
        for i, thumb in enumerate(thumbs):
            r, c = divmod(i, columns)
            sheet[r * th : (r + 1) * th, c * tw : (c + 1) * tw] = thumb[:, :, :3]
        return sheet
