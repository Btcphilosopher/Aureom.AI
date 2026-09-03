"""
Simulation mode: the complete OS runs without a physical headset. A virtual
headset, hands, room, objects and sensors let applications be developed and
tested -- deterministically, for CI -- on an ordinary computer.
"""

from xr_os.simulation.sim_env import SimulatedXREnvironment
from xr_os.simulation.virtual_devices import VirtualCamera, VirtualHands, VirtualHeadset, VirtualRoom

__all__ = ["VirtualHeadset", "VirtualHands", "VirtualRoom", "VirtualCamera", "SimulatedXREnvironment"]
