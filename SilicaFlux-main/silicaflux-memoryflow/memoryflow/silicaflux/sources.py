"""Locate and extract the SilicaFlux HDL sources that live in this repository.

The SilicaFlux tree keeps most of its RTL inside archives (``silicaflux.zip``,
``memory_cache_repo.zip``, ``soc_integration.tar.gz`` ...) and the 2.x
generation as loose ``.sf`` files (SystemVerilog with a custom extension).
:func:`materialise` copies every HDL member of a :class:`SourceSet` into
``build/sf_src/<key>/`` and records, for each file, where it came from
(``archive::member`` or the loose path) and its sha256, so every piece of
evidence in the inventory can be traced back to a byte-exact repository file.

The repository files themselves are never modified.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import tarfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

MF_ROOT = Path(__file__).resolve().parents[2]
HDL_EXT = (".sv", ".svh", ".v", ".vh", ".sf")


def silicaflux_root() -> Path | None:
    """The SilicaFlux-main directory that contains this MemoryFlow checkout.

    Override with ``MF_SILICAFLUX_ROOT``.  Returns None when the sources are
    not available (MemoryFlow then runs its own RTL and models only)."""
    env = os.environ.get("MF_SILICAFLUX_ROOT")
    cands = [Path(env)] if env else [MF_ROOT.parent]
    for c in cands:
        if (c / "silicaflux.zip").exists() or (c / "memory_controller.sf").exists():
            return c.resolve()
    return None


@dataclass(frozen=True)
class SourceSet:
    key: str
    title: str
    generation: str
    archives: tuple[str, ...] = ()        # zip / tar(.gz) paths relative to the SilicaFlux root
    loose: tuple[str, ...] = ()           # glob patterns relative to the SilicaFlux root
    member_glob: str = "*"                # fnmatch on archive member paths
    silicaflux_core: bool = True          # part of the SilicaFlux architecture proper
    note: str = ""


SOURCE_SETS: dict[str, SourceSet] = {s.key: s for s in [
    SourceSet("sf1", "SilicaFlux v1 cluster (silicaflux.zip)", "Gen-1",
              archives=("silicaflux.zip",),
              note="4 tiles x 1 KiB SRAM, 4-lane SIMD, sequential 4x4 tensor unit, 2x2 NoC; "
                   "the only generation with a complete, elaborating top level"),
    SourceSet("sf25", "SilicaFlux 2.x unit sources (loose .sf files)", "Gen-2.5",
              loose=("*.sf", "SilicaFlux2.0/SilicaFlux2.5/*.sf"),
              note="banked scratchpad controller, pipelined 4x4x4 tensor unit, compute tile, "
                   "8-core cluster top; files appear in two directories, some as diverging variants"),
    SourceSet("sf2_rtl", "SilicaFlux 2.x top/front-end archives", "Gen-2.5",
              archives=("SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl.zip",
                        "SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip",
                        "SilicaFlux2.0/SilicaFlux2.5/silicaflux_alu.zip")),
    SourceSet("sfx_ai", "SilicaFlux-AI GEMM engine (silicafluxai.zip)", "SilicaFlux-AI",
              archives=("SilicaFlux2.0/silicafluxai.zip",),
              note="weight-stationary systolic GEMM engine, sfx_sram_interface, single-command sfx_dma"),
    SourceSet("sf_ml", "SilicaFlux-ML learning controller", "SilicaFlux-ML",
              archives=("SilicaFlux2.0/SilicaFluxML.zip",)),
    SourceSet("testcore", "SilicaFlux TestCore DFT (MBIST/LBIST/TAP)", "SilicaFlux-DFT",
              archives=("SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip",)),
    SourceSet("timinglab", "SilicaFlux TimingLab pipelined drop-ins", "Gen-1 (optimised)",
              archives=("SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip",),
              member_glob="*/rtl/*"),
    SourceSet("memcache", "Generic cache / RAM / SDRAM-FSM library", "library",
              archives=("memory_cache_repo.zip",), silicaflux_core=False,
              note="stand-alone teaching blocks, not instantiated by any SilicaFlux top"),
    SourceSet("soc", "SoC integration example", "library",
              archives=("soc_integration.tar.gz",), silicaflux_core=False),
    SourceSet("cpu", "CPU cores (cpu_core, RISC-V, pipelined)", "library",
              archives=("cpu_core.zip", "RISC-V CPU.zip", "pipelined_cpu.zip"), silicaflux_core=False),
    SourceSet("powerlink", "PowerLink support RTL", "support",
              archives=("silicaflux-powerlink.zip",), silicaflux_core=False),
]}


@dataclass
class SourceFile:
    set_key: str
    origin: str          # "<archive>::<member>" or "<relative loose path>"
    path: str            # extracted path relative to MF_ROOT
    sha256: str
    lines: int

    @property
    def short(self) -> str:
        return self.origin.split("::")[-1]


@dataclass
class Materialised:
    set: SourceSet
    root: Path
    files: list[SourceFile] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def by_origin(self) -> dict[str, SourceFile]:
        return {f.origin: f for f in self.files}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_hdl(name: str) -> bool:
    return name.lower().endswith(HDL_EXT) and "/__MACOSX/" not in "/" + name


def _iter_archive(path: Path):
    """Yield (member_name, bytes) for every regular file of a zip / tar."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.is_dir():
                    yield info.filename, z.read(info)
    else:
        with tarfile.open(path) as t:
            for m in t.getmembers():
                if m.isfile():
                    f = t.extractfile(m)
                    if f is not None:
                        yield m.name, f.read()


def _safe_rel(name: str) -> Path:
    parts = [p for p in Path(name).parts if p not in ("", ".", "..", "/")]
    return Path(*parts)


def materialise(key: str, sf_root: Path | None = None, out_root: Path | None = None) -> Materialised:
    """Extract one source set (idempotent; overwrites the previous copy)."""
    s = SOURCE_SETS[key]
    sf_root = sf_root or silicaflux_root()
    out = (out_root or MF_ROOT / "build" / "sf_src") / key
    m = Materialised(s, out)
    if sf_root is None:
        m.missing.append("SilicaFlux root not found")
        return m
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for arc in s.archives:
        ap = sf_root / arc
        if not ap.exists():
            m.missing.append(arc)
            continue
        tag = Path(arc).stem.replace(" ", "_")
        for name, data in _iter_archive(ap):
            if not _is_hdl(name) or not fnmatch.fnmatch(name, s.member_glob):
                continue
            dst = out / tag / _safe_rel(name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            m.files.append(SourceFile(key, f"{arc}::{name}", str(dst.relative_to(MF_ROOT)), _sha(data),
                                      data.count(b"\n") + 1))
    for pat in s.loose:
        for p in sorted(sf_root.glob(pat)):
            if not p.is_file() or not _is_hdl(p.name):
                continue
            rel = p.relative_to(sf_root)
            data = p.read_bytes()
            dst = out / "loose" / _safe_rel(str(rel))
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            m.files.append(SourceFile(key, str(rel), str(dst.relative_to(MF_ROOT)), _sha(data),
                                      data.count(b"\n") + 1))
    (out / "manifest.json").write_text(json.dumps([asdict(f) for f in m.files], indent=1))
    return m


def materialise_all(keys: list[str] | None = None, sf_root: Path | None = None) -> dict[str, Materialised]:
    return {k: materialise(k, sf_root) for k in (keys or list(SOURCE_SETS))}


def find_file(m: Materialised, origin_suffix: str) -> SourceFile:
    """The unique extracted file whose origin ends with ``origin_suffix``."""
    hits = [f for f in m.files if f.origin.endswith(origin_suffix)]
    if len(hits) != 1:
        raise FileNotFoundError(f"{origin_suffix!r} matched {len(hits)} files in set {m.set.key}")
    return hits[0]
