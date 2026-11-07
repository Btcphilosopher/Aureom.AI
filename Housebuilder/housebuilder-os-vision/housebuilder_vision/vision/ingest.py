"""Validated, content-addressed image ingest.

Uploaded files are untrusted.  :func:`ingest_image` therefore:

1. rejects payloads over ``MAX_BYTES`` (25 MB) before touching them;
2. detects the format from the *content* with Pillow, restricted to
   PNG / JPEG / WebP / TIFF / BMP (the filename extension is ignored);
3. checks width x height against ``MAX_PIXELS`` (50 MP) and ``MAX_SIDE``
   from the header *before* any pixel data is decoded (decompression-bomb
   guard; Pillow's own bomb warnings are escalated to errors);
4. runs ``Image.verify()`` and then re-opens and fully decodes the image, so
   truncated or corrupt files are rejected;
5. computes the SHA-256 of the original bytes (``image_id = "img_" + sha[:16]``)
   and, when ``store_dir`` is given, preserves the *original bytes unchanged*
   at ``store_dir/<sha256>.<ext>`` (atomic write; content addressing makes
   re-ingest idempotent);
6. keeps only a safe subset of EXIF (Make, Model, FocalLength,
   FocalLengthIn35mmFilm, DateTimeOriginal) as sanitised strings — GPS,
   maker notes, thumbnails and free-text fields are dropped.

``width_px``/``height_px`` are the dimensions *as displayed* (after the EXIF
orientation is applied), matching :func:`load_image_array`, which returns an
EXIF-transposed RGB ``uint8`` array; all pixel coordinates in detections refer
to that array.

The module never executes or interprets image content (text in images is not
read), and never writes outside ``store_dir``.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
import unicodedata
import warnings
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageOps

from ..core.models import ImageAsset, ImageKind, ViewDirection

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 50_000_000
#: Longest permitted side (guards against degenerate 1 x 50M images).
MAX_SIDE = 30_000

#: Pillow format name -> (media type, stored extension)
ALLOWED_FORMATS: dict[str, tuple[str, str]] = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
    "TIFF": ("image/tiff", "tif"),
    "BMP": ("image/bmp", "bmp"),
}
MEDIA_TYPE_EXTENSIONS: dict[str, str] = {mt: ext for mt, ext in ALLOWED_FORMATS.values()}

#: name -> (tag id, IFD) of the EXIF fields we keep.
SAFE_EXIF_TAGS: dict[str, tuple[int, str]] = {
    "Make": (0x010F, "ifd0"),
    "Model": (0x0110, "ifd0"),
    "FocalLength": (0x920A, "exif"),
    "FocalLengthIn35mmFilm": (0xA405, "exif"),
    "DateTimeOriginal": (0x9003, "exif"),
}
_EXIF_IFD = 0x8769
_ORIENTATION = 0x0112

_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


class ImageRejected(ValueError):
    """The upload is not an acceptable image (format, size, integrity)."""


# ----------------------------------------------------------------- filenames
def sanitize_filename(name: Any, default: str = "upload") -> str:
    """Return a safe display filename: basename only, printable ASCII subset,
    no leading dots, at most 120 characters.  Never used as a storage path."""
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = s.replace("\\", "/").split("/")[-1]
    s = "".join(ch for ch in s if ch.isprintable())
    s = re.sub(r"[^A-Za-z0-9._ ()\-]+", "_", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip(" ._")
    if not s:
        s = default
    stem = s.split(".")[0]
    if stem.upper() in _WINDOWS_RESERVED:
        s = "_" + s
    if len(s) > 120:
        stem, dot, ext = s.rpartition(".")
        if dot and 0 < len(ext) <= 10:
            s = stem[: 119 - len(ext)] + "." + ext
        else:
            s = s[:120]
    return s


# ---------------------------------------------------------------- decoding
def _open_restricted(data: bytes) -> Image.Image:
    """Open lazily (header only) with the allowed decoders only."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            return Image.open(io.BytesIO(data), formats=list(ALLOWED_FORMATS))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageRejected(f"image dimensions exceed the decompression-bomb limit ({exc})") from exc
    except Exception as exc:  # UnidentifiedImageError, OSError, SyntaxError, ...
        raise ImageRejected("not a recognised PNG/JPEG/WebP/TIFF/BMP image") from exc


def _check_dimensions(im: Image.Image, max_pixels: int) -> tuple[int, int]:
    w, h = (int(v) for v in im.size)
    if w <= 0 or h <= 0:
        raise ImageRejected("image has zero width or height")
    if w > MAX_SIDE or h > MAX_SIDE:
        raise ImageRejected(f"image side {max(w, h)} px exceeds the {MAX_SIDE} px limit")
    if w * h > max_pixels:
        raise ImageRejected(f"image has {w * h / 1e6:.1f} MP; the limit is {max_pixels / 1e6:.0f} MP")
    return w, h


def _full_decode(data: bytes, max_pixels: int) -> Image.Image:
    im = _open_restricted(data)
    if im.format not in ALLOWED_FORMATS:
        raise ImageRejected(f"format {im.format!r} is not allowed")
    _check_dimensions(im, max_pixels)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im.load()
    except ImageRejected:
        raise
    except Exception as exc:
        raise ImageRejected(f"image data could not be decoded ({type(exc).__name__})") from exc
    return im


def _exif_text(value: Any) -> str:
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    if isinstance(value, tuple) and value:
        value = value[0]
    try:
        if not isinstance(value, str):
            f = float(value)
            value = f"{f:g}" if np.isfinite(f) else ""
    except (TypeError, ValueError, ZeroDivisionError):
        value = str(value)
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()
    return s[:64]


def _safe_exif(im: Image.Image) -> tuple[dict[str, str], Optional[int]]:
    try:
        exif = im.getexif()
    except Exception:
        return {}, None
    try:
        sub = exif.get_ifd(_EXIF_IFD)
    except Exception:
        sub = {}
    out: dict[str, str] = {}
    for name, (tag, where) in SAFE_EXIF_TAGS.items():
        val = exif.get(tag) if where == "ifd0" else sub.get(tag, exif.get(tag))
        if val is None:
            continue
        s = _exif_text(val)
        if s:
            out[name] = s
    orient = exif.get(_ORIENTATION)
    try:
        orient = int(orient) if orient is not None else None
    except (TypeError, ValueError):
        orient = None
    return out, orient


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ ingest
def ingest_image(data: bytes, filename: str, *, kind: ImageKind = ImageKind.UNKNOWN,
                 view: ViewDirection = ViewDirection.UNKNOWN, store_dir: Path | str | None = None,
                 notes: str = "", max_bytes: int = MAX_BYTES, max_pixels: int = MAX_PIXELS) -> ImageAsset:
    """Validate an uploaded image and return its content-addressed :class:`ImageAsset`.

    Raises :class:`ImageRejected` for anything that is not an acceptable image.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ImageRejected("image data must be bytes")
    data = bytes(data)
    if not data:
        raise ImageRejected("empty upload")
    if len(data) > max_bytes:
        raise ImageRejected(f"file is {len(data) / 2**20:.1f} MiB; the limit is {max_bytes / 2**20:.0f} MiB")

    im = _open_restricted(data)
    fmt = im.format
    if fmt not in ALLOWED_FORMATS:
        raise ImageRejected(f"format {fmt!r} is not allowed")
    _check_dimensions(im, max_pixels)  # header only: no pixel data decoded yet
    try:
        im.verify()  # must directly follow open()
    except Exception as exc:
        raise ImageRejected(f"image failed integrity verification ({type(exc).__name__})") from exc
    full = _full_decode(data, max_pixels)  # verify() invalidates the object: reopen and decode
    n_frames = int(getattr(full, "n_frames", 1) or 1)
    exif, orientation = _safe_exif(full)
    w, h = full.size
    if orientation in (5, 6, 7, 8):
        w, h = h, w

    sha = hashlib.sha256(data).hexdigest()
    media_type, ext = ALLOWED_FORMATS[fmt]
    stored_path: Optional[str] = None
    if store_dir is not None:
        target = Path(store_dir) / f"{sha}.{ext}"
        if not (target.is_file() and target.stat().st_size == len(data)
                and hashlib.sha256(target.read_bytes()).hexdigest() == sha):
            _atomic_write(target, data)
        stored_path = str(target)

    note_parts = [notes.strip()] if notes and notes.strip() else []
    if orientation and orientation != 1:
        note_parts.append(f"EXIF orientation {orientation} applied; dimensions are as displayed.")
    if n_frames > 1:
        note_parts.append(f"Multi-frame image ({n_frames} frames): only the first frame is analysed.")
    return ImageAsset(
        image_id="img_" + sha[:16], sha256=sha, original_filename=sanitize_filename(filename),
        media_type=media_type, width_px=int(w), height_px=int(h), size_bytes=len(data), kind=kind,
        view=view, stored_path=stored_path, exif=exif, notes=" ".join(note_parts),
    )


def ingest_path(path: Path | str, *, kind: ImageKind = ImageKind.UNKNOWN,
                view: ViewDirection = ViewDirection.UNKNOWN, store_dir: Path | str | None = None,
                filename: Optional[str] = None, notes: str = "", max_bytes: int = MAX_BYTES) -> ImageAsset:
    """Ingest a file from disk (size checked before reading)."""
    p = Path(path)
    if not p.is_file():
        raise ImageRejected(f"not a file: {sanitize_filename(p.name)}")
    if p.stat().st_size > max_bytes:
        raise ImageRejected(f"file is {p.stat().st_size / 2**20:.1f} MiB; the limit is {max_bytes / 2**20:.0f} MiB")
    return ingest_image(p.read_bytes(), filename or p.name, kind=kind, view=view, store_dir=store_dir,
                        notes=notes, max_bytes=max_bytes)


# --------------------------------------------------------------- loading
def decode_rgb(data: bytes, *, max_pixels: int = MAX_PIXELS) -> np.ndarray:
    """Decode validated image bytes to an EXIF-transposed RGB ``uint8`` array."""
    im = _full_decode(data, max_pixels)
    im = ImageOps.exif_transpose(im) or im
    if im.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        arr = np.asarray(im, dtype=np.float64)
        top = float(arr.max()) if arr.size else 1.0
        arr = np.clip(arr / (top if top > 0 else 1.0) * 255.0, 0, 255).astype(np.uint8)
        return np.repeat(arr[..., None], 3, axis=2)
    if im.mode == "P" or im.mode == "LA" or (im.mode == "L" and "transparency" in im.info):
        im = im.convert("RGBA")
    if im.mode != "RGB":
        im = im.convert("RGB")
    return np.ascontiguousarray(np.asarray(im, dtype=np.uint8))


def stored_image_path(asset: ImageAsset, store_dir: Path | str | None = None) -> Path:
    """Locate the preserved original for ``asset`` (``store_dir`` first, then ``stored_path``)."""
    cands: list[Path] = []
    if store_dir is not None:
        ext = MEDIA_TYPE_EXTENSIONS.get(asset.media_type)
        if ext:
            cands.append(Path(store_dir) / f"{asset.sha256}.{ext}")
        cands.extend(sorted(Path(store_dir).glob(f"{asset.sha256}.*")))
    if asset.stored_path:
        cands.append(Path(asset.stored_path))
    for c in cands:
        if c.is_file():
            return c
    raise FileNotFoundError(f"stored original for {asset.image_id} not found")


def load_image_array(asset: ImageAsset, store_dir: Path | str | None = None) -> np.ndarray:
    """Load the preserved original as an EXIF-transposed RGB ``uint8`` array.

    The stored bytes are re-hashed and must match ``asset.sha256``.
    """
    path = stored_image_path(asset, store_dir)
    if path.stat().st_size > MAX_BYTES:
        raise ImageRejected("stored file exceeds the size limit")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != asset.sha256:
        raise ImageRejected(f"stored file for {asset.image_id} does not match its sha256")
    return decode_rgb(data)


__all__ = [
    "MAX_BYTES", "MAX_PIXELS", "MAX_SIDE", "ALLOWED_FORMATS", "SAFE_EXIF_TAGS", "ImageRejected",
    "sanitize_filename", "ingest_image", "ingest_path", "decode_rgb", "stored_image_path", "load_image_array",
]
