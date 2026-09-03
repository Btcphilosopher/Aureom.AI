"""Security & privacy: per-app permissions over sensitive spatial data, and encrypted local-first storage."""

from xr_os.security.permissions import PermissionDeniedError, PermissionManager, PermissionScope, PermissionStatus
from xr_os.security.storage import EncryptedStorage

__all__ = ["PermissionScope", "PermissionStatus", "PermissionDeniedError", "PermissionManager", "EncryptedStorage"]
