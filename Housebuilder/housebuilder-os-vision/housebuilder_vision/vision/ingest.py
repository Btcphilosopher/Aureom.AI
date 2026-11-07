"""Validated, content-addressed image ingest.

Uploaded files are untrusted.  :func:`ingest_image` therefore:

1. rejects payloads over ``MAX_BYTES`` (25 MB) before touching them;
2. detects the format from the *content* with Pillow, restricted to
   PNG / JPEG / WebP / TIFF / BMP (the filename extension is ignored; a
   multi-picture JPEG - Pillow format ``MPO``, written by many phones and
   cameras - is a JPEG: ``image/jpeg``, first frame analysed, original bytes
   kept);
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

Loading (:func:`load_image_array`) reads a preserved original only from a
content-addressed file ``<sha256>.<ext>`` (``ImageAsset.stored_path`` from a
loaded project is untrusted: any other name, or a path outside ``store_dir``
when one is given, is ignored), with a size cap, and re-checks the sha256.
16-bit / 32-bit images are scaled to 8 bits in row chunks (integer / float32
arithmetic) so the 50 MP limit also bounds decode memory.

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
    # Multi-picture JPEG (an MPF index: stereo / preview / depth frames written by many phones and cameras).
    # The file *is* a JPEG whose first frame is the photo; only that frame is analysed.
    "MPO": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
    "TIFF": ("image/tiff", "tif"),
    "BMP": ("image/bmp", "bmp"),
}
MEDIA_TYPE_EXTENSIONS: dict[str, str] = {mt: ext for mt, ext in ALLOWED_FORMATS.values()}
#: Pillow decoders tried when opening (MPO files are opened by the JPEG decoder, which reports ``MPO``).
OPEN_FORMATS: tuple[str, ...] = ("PNG", "JPEG", "WEBP", "TIFF", "BMP")
#: Extensions a preserved original may have (content-addressed ``<sha256>.<ext>``).
STORED_EXTENSIONS = frozenset(MEDIA_TYPE_EXTENSIONS.values())
#: Rows decoded per chunk when scaling >8-bit images to 8 bits (bounds the temporaries).
_DECODE_CHUNK_ROWS = 512

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
            return Image.open(io.BytesIO(data), formats=list(OPEN_FORMATS))
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
def _to_uint8(arr: np.ndarray) -> np.ndarray:
    """Scale a >8-bit single-channel array to ``uint8`` (0 .. max -> 0 .. 255), chunk by chunk.

    Integer images are scaled with integer arithmetic and float images in ``float32``, a block of
    rows at a time, so the temporaries stay a few MB whatever the image size (a full-resolution
    ``float64`` copy of a 49 MP 16-bit image would need ~1.2 GB).
    """
    out = np.empty(arr.shape, dtype=np.uint8)
    if arr.size == 0:
        return out
    is_int = np.issubdtype(arr.dtype, np.integer)
    top_f = 0.0
    for r0 in range(0, arr.shape[0], _DECODE_CHUNK_ROWS):  # largest finite value, chunk by chunk
        blk = arr[r0:r0 + _DECODE_CHUNK_ROWS]
        m = blk.max() if is_int else np.max(blk, where=np.isfinite(blk), initial=0.0)
        top_f = max(top_f, float(m))
    for r0 in range(0, arr.shape[0], _DECODE_CHUNK_ROWS):
        blk = arr[r0:r0 + _DECODE_CHUNK_ROWS]
        if is_int and top_f > 0:
            b = np.clip(blk.astype(np.int64), 0, None)
            out[r0:r0 + _DECODE_CHUNK_ROWS] = (b * 255 // int(top_f)).astype(np.uint8)
        else:
            b = np.nan_to_num(blk.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
            if top_f > 0:
                b *= np.float32(255.0 / top_f)
            np.clip(b, 0, 255, out=b)
            out[r0:r0 + _DECODE_CHUNK_ROWS] = b.astype(np.uint8)
    return out


def decode_rgb(data: bytes, *, max_pixels: int = MAX_PIXELS) -> np.ndarray:
    """Decode validated image bytes to an EXIF-transposed RGB ``uint8`` array.

    16-bit / 32-bit single-channel images are scaled to 8 bits without a full-resolution
    floating-point copy (see :func:`_to_uint8`).
    """
    im = _full_decode(data, max_pixels)
    im = ImageOps.exif_transpose(im) or im
    if im.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        arr = _to_uint8(np.asarray(im))
        return np.repeat(arr[..., None], 3, axis=2)
    if im.mode == "P" or im.mode == "LA" or (im.mode == "L" and "transparency" in im.info):
        im = im.convert("RGBA")
    if im.mode != "RGB":
        im = im.convert("RGB")
    return np.ascontiguousarray(np.asarray(im, dtype=np.uint8))


def _content_addressed(path: Path, asset: ImageAsset) -> bool:
    """``path`` (after resolving links) is a regular file named ``<sha256>.<allowed ext>`` of this asset."""
    try:
        real = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    stem, dot, ext = real.name.rpartition(".")
    return bool(dot) and stem == asset.sha256 and ext in STORED_EXTENSIONS and real.is_file()


def stored_image_path(asset: ImageAsset, store_dir: Path | str | None = None) -> Path:
    """Locate the preserved original for ``asset`` (``store_dir`` first, then ``stored_path``).

    ``ImageAsset.stored_path`` comes from project state (untrusted when a project is loaded): it is
    used only when it names a content-addressed file ``<sha256>.<ext>`` of this asset - and, when
    ``store_dir`` is given, one inside ``store_dir`` - so a crafted path (``/proc/self/environ``, a
    file elsewhere on the server) is never opened.
    """
    cands: list[Path] = []
    root: Optional[Path] = None
    if store_dir is not None:
        root = Path(store_dir)
        ext = MEDIA_TYPE_EXTENSIONS.get(asset.media_type)
        if ext:
            cands.append(root / f"{asset.sha256}.{ext}")
        cands.extend(sorted(root.glob(f"{asset.sha256}.*")))
    if asset.stored_path:
        sp = Path(asset.stored_path)
        inside = True
        if root is not None:
            try:
                sp.resolve().relative_to(root.resolve())
            except (ValueError, OSError, RuntimeError):
                inside = False
        if inside:
            cands.append(sp)
    for c in cands:
        if _content_addressed(c, asset):
            return c
    raise FileNotFoundError(f"stored original for {asset.image_id} not found")


def load_image_array(asset: ImageAsset, store_dir: Path | str | None = None) -> np.ndarray:
    """Load the preserved original as an EXIF-transposed RGB ``uint8`` array.

    The stored bytes are read with a size cap (``MAX_BYTES``; ``st_size`` is not trusted) and
    re-hashed: they must match ``asset.sha256``.
    """
    path = stored_image_path(asset, store_dir)
    with open(path, "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ImageRejected("stored file exceeds the size limit")
    if hashlib.sha256(data).hexdigest() != asset.sha256:
        raise ImageRejected(f"stored file for {asset.image_id} does not match its sha256")
    return decode_rgb(data)


__all__ = [
    "MAX_BYTES", "MAX_PIXELS", "MAX_SIDE", "ALLOWED_FORMATS", "STORED_EXTENSIONS", "SAFE_EXIF_TAGS",
    "ImageRejected",
    "sanitize_filename", "ingest_image", "ingest_path", "decode_rgb", "stored_image_path", "load_image_array",
]
