"""
The application runtime: the stable, hardware-independent API surface XR
applications are written against, plus the OS-style services (spatial
mapping, tracking, audio, input, haptics, scene management, notifications,
permissions, user profiles, application lifecycle, spatial storage) that
back it.
"""

from xr_os.runtime.app import XRApp, XRWorld
from xr_os.runtime.services import (
    LifecycleService,
    NotificationService,
    ProfileService,
    UserProfile,
    XRServices,
)

__all__ = ["XRWorld", "XRApp", "XRServices", "NotificationService", "ProfileService", "UserProfile", "LifecycleService"]
