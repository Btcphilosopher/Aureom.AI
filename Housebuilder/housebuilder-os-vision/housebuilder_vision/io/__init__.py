"""Export, optional IFC adapter and SQLite persistence.

* :mod:`.export` - ``export_project``: project.json / results.json, twin.glb (visual only),
  CSV tables with formula-injection protection, optional IFC, README and a sha256 manifest.
* :mod:`.ifc_adapter` - ``export_ifc``: conceptual IFC4 model (approx. LOD 100-200) with declared
  omissions; ``ifcopenshell`` is imported lazily (``AdapterUnavailable`` when missing).
* :mod:`.persistence` - ``ProjectStore``: SQLite store for validated project state, the image
  registry and the reproducibility run log.

Importing this package never imports ``ifcopenshell``.
"""

from .export import (
    CSV_INJECTION_PREFIXES,
    EXPORT_INFORMATION_LEVEL,
    FICTIONAL_LABEL,
    FORMATS,
    GLB_NOTICE,
    PROVENANCE_NOTE,
    ExportedFile,
    ExportManifest,
    canonical_json,
    canonical_sha256,
    csv_bytes,
    engine_version,
    engine_versions,
    export_project,
    is_fictional_rate,
    sanitize_cell,
    sha256_hex,
)
from .ifc_adapter import (
    IFC_INFORMATION_LEVEL,
    IFC_INSTALL_HINT,
    IFC_OMISSIONS,
    INFORMATION_PSET,
    AdapterUnavailable,
    IfcExportReport,
    export_ifc,
    ifc_available,
    provenance_counts,
)
from .persistence import (
    DATA_DIR_ENV,
    STORE_SCHEMA_VERSION,
    ImageRecord,
    ProjectNotFound,
    ProjectStore,
    ProjectSummary,
    StoredRun,
    StoreError,
    default_db_path,
)

__all__ = [
    "CSV_INJECTION_PREFIXES", "EXPORT_INFORMATION_LEVEL", "FICTIONAL_LABEL", "FORMATS", "GLB_NOTICE",
    "PROVENANCE_NOTE", "ExportedFile", "ExportManifest", "canonical_json", "canonical_sha256", "csv_bytes",
    "engine_version", "engine_versions", "export_project", "is_fictional_rate", "sanitize_cell", "sha256_hex",
    "IFC_INFORMATION_LEVEL", "IFC_INSTALL_HINT", "IFC_OMISSIONS", "INFORMATION_PSET", "AdapterUnavailable",
    "IfcExportReport", "export_ifc", "ifc_available", "provenance_counts",
    "DATA_DIR_ENV", "STORE_SCHEMA_VERSION", "ImageRecord", "ProjectNotFound", "ProjectStore", "ProjectSummary",
    "StoredRun", "StoreError", "default_db_path",
]
