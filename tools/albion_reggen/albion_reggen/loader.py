"""Strict loading of register definitions (YAML or JSON) with ``include`` support.

Why a custom loader
-------------------
Stock YAML 1.1 loaders silently mangle exactly the things a register
description is made of:

* ``bits: 7:0`` is parsed as the base-60 integer 420,
* ``no`` / ``on`` / ``off`` are booleans (a field called ``ON`` vanishes),
* ``010`` is an octal literal,
* a repeated mapping key silently overwrites the earlier one.

This loader removes sexagesimal numbers, floats and the YAML-1.1 booleans,
rejects leading-zero integers, and rejects duplicate keys, so what the author
wrote is what the validator sees.  JSON is read with the same duplicate-key
rule.  Every loaded file is hashed (SHA-256 of its bytes) for provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Tuple

from .errors import Collector, Diagnostic, RegDefError

try:  # PyYAML is optional: JSON definitions need only the standard library.
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:  # pragma: no cover - exercised only without PyYAML
    yaml = None  # type: ignore
    _HAVE_YAML = False


class _Dup(Exception):
    pass


_INT_RE = re.compile(r"^[-+]?(?:0b[01_]+|0x[0-9a-fA-F_]+|0|[1-9][0-9_]*)$")
_LEADING_ZERO_RE = re.compile(r"^[-+]?0[0-9_]+$")


def _make_yaml_loader():
    class StrictLoader(yaml.SafeLoader):  # type: ignore[misc]
        pass

    # Rebuild the implicit resolvers from scratch: only null, bool(true/false),
    # and a plain integer grammar remain.  Everything else stays a string.
    StrictLoader.yaml_implicit_resolvers = {}
    StrictLoader.add_implicit_resolver(
        "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))
    StrictLoader.add_implicit_resolver(
        "tag:yaml.org,2002:null", re.compile(r"^(?:null|~)$"), ["n", "~"])
    StrictLoader.add_implicit_resolver(
        "tag:yaml.org,2002:int", _INT_RE, list("-+0123456789"))
    # Integers with a leading zero are ambiguous (octal in YAML 1.1): flag them.
    StrictLoader.add_implicit_resolver(
        "!leadingzero", _LEADING_ZERO_RE, list("-+0"))

    def construct_bool(loader, node):
        return loader.construct_scalar(node) == "true"

    def construct_int(loader, node):
        text = loader.construct_scalar(node).replace("_", "")
        return int(text, 0)

    def construct_leading_zero(loader, node):
        raise yaml.constructor.ConstructorError(
            None, None,
            "integer %r has a leading zero (ambiguous octal); write it in "
            "decimal, 0x hex or 0b binary" % loader.construct_scalar(node),
            node.start_mark)

    def construct_mapping(loader, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    "duplicate key %r" % (key,), key_node.start_mark)
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    StrictLoader.add_constructor("tag:yaml.org,2002:bool", construct_bool)
    StrictLoader.add_constructor("tag:yaml.org,2002:int", construct_int)
    StrictLoader.add_constructor("!leadingzero", construct_leading_zero)
    StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    return StrictLoader


_LOADER = _make_yaml_loader() if _HAVE_YAML else None


def _json_pairs(pairs):
    out: Dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise _Dup(k)
        out[k] = v
    return out


def parse_text(text: str, filename: str) -> Any:
    """Parse YAML or JSON text.  Raises ``RegDefError`` with code E_PARSE."""
    try:
        if filename.lower().endswith(".json"):
            return json.loads(text, object_pairs_hook=_json_pairs)
        if not _HAVE_YAML:
            raise RegDefError([Diagnostic(
                "E_PARSE", "PyYAML is not installed; install it or supply the "
                "definition as .json", filename)])
        return yaml.load(text, Loader=_LOADER)  # noqa: S506 - SafeLoader subclass
    except RegDefError:
        raise
    except _Dup as exc:
        raise RegDefError([Diagnostic("E_PARSE", f"duplicate key {exc}", filename)])
    except Exception as exc:  # yaml/json syntax and constructor errors
        raise RegDefError([Diagnostic("E_PARSE", str(exc).replace("\n", " "), filename)])


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Source:
    """A loaded definition tree: the merged document plus provenance."""

    def __init__(self) -> None:
        #: relative-path -> sha256 of every file read (top file and includes)
        self.files: Dict[str, str] = {}
        #: location map: id(node) is not stable, so we keep origin per include
        self.root: Any = None


def load(path: str) -> Source:
    """Load ``path`` and resolve ``{include: file}`` entries of ``peripherals``.

    Include paths are relative to the including file.  Include cycles and
    missing files are errors.  The returned document is a plain structure in
    which every include has been replaced by the included peripheral mapping,
    annotated with ``_source`` (its path relative to the top file).
    """
    src = Source()
    top_dir = os.path.dirname(os.path.abspath(path))
    stack: List[str] = []

    def rel(p: str) -> str:
        return os.path.relpath(os.path.abspath(p), top_dir).replace(os.sep, "/")

    def read(p: str) -> Any:
        ap = os.path.abspath(p)
        if ap in stack:
            raise RegDefError([Diagnostic(
                "E_INCLUDE", "include cycle: " + " -> ".join(rel(s) for s in stack + [ap]))])
        try:
            with open(ap, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise RegDefError([Diagnostic("E_INCLUDE", f"cannot read {rel(ap)}: {exc}")])
        src.files[rel(ap)] = sha256_bytes(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RegDefError([Diagnostic("E_PARSE", f"not UTF-8: {exc}", rel(ap))])
        doc = parse_text(text, ap)
        stack.append(ap)
        try:
            return resolve(doc, ap)
        finally:
            stack.pop()

    def resolve(doc: Any, owner: str) -> Any:
        if isinstance(doc, dict) and isinstance(doc.get("peripherals"), list):
            out = []
            for i, ent in enumerate(doc["peripherals"]):
                if isinstance(ent, dict) and set(ent.keys()) == {"include"}:
                    inc = os.path.join(os.path.dirname(owner), str(ent["include"]))
                    sub = read(inc)
                    if isinstance(sub, dict):
                        sub = dict(sub)
                        sub.pop("regdef_version", None)
                        sub["_source"] = rel(inc)
                    out.append(sub)
                else:
                    if isinstance(ent, dict):
                        ent = dict(ent)
                        ent.setdefault("_source", rel(owner))
                    out.append(ent)
            doc = dict(doc)
            doc["peripherals"] = out
        return doc

    src.root = read(path)
    return src
