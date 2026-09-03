"""
Multi-user XR: shared spatial experiences over WebSockets.

    USER A -> SHARED WORLD <- USER B

Synchronizes user pose (head/hands), shared virtual object ownership,
input events (gestures/voice), and spatial anchors across connected clients.
"""

from xr_os.multiuser.protocol import AnchorSync, Envelope, MessageType, ObjectSync, UserState
from xr_os.multiuser.server import SharedWorldServer, create_app

__all__ = ["MessageType", "Envelope", "UserState", "ObjectSync", "AnchorSync", "SharedWorldServer", "create_app"]
