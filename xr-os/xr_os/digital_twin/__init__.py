"""
Digital Twin mode: connect XR-OS to an external digital twin (a factory, a
building, a piece of infrastructure) and walk around/inspect a virtual
representation of it, kept live via telemetry.

    FACTORY -> DIGITAL TWIN -> XR-OS -> ENGINEER
"""

from xr_os.digital_twin.twin import DigitalTwinConnector, DigitalTwinSource, HttpJsonTwinSource, StaticTwinSource, TwinAsset

__all__ = ["TwinAsset", "DigitalTwinSource", "HttpJsonTwinSource", "StaticTwinSource", "DigitalTwinConnector"]
