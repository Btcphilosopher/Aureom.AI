"""XR-OS diagnostic dashboard: a FastAPI status API and a terminal renderer, both reading from one ``XRWorld``."""

from xr_os.dashboard.api import create_dashboard_app
from xr_os.dashboard.cli_dashboard import print_dashboard, render_dashboard, snapshot

__all__ = ["create_dashboard_app", "snapshot", "render_dashboard", "print_dashboard"]
