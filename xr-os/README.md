# XR-OS

A modular Python platform for spatial computing -- a general-purpose
operating layer for Augmented Reality, Virtual Reality and Mixed Reality
that understands the user's position, environment, objects, interactions
and virtual content. It's built to feel less like an XR application and
more like an operating system for spatial computing.

```
Physical World
    |
Sensors / Cameras / IMU
    |
Spatial Perception
    |
Spatial World Model
    |
XR Runtime
    |
Applications / Experiences
    |
Display + Audio + Haptics
```

> The computer is no longer a screen. The computer understands the space
> around the user.

XR-OS provides the underlying software layer for AR glasses, VR headsets,
MR systems, spatial workstations, industrial visualization, robotics,
gaming, simulation, education, design and future spatial-computing devices.

## Design principles

- **Python for the operating system, not the hot loop.** High-level app
  logic, spatial reasoning, scene management, simulation, AI and developer
  tools live in Python. Anything latency-critical -- rendering, tracking
  fusion, sensor fusion, frame scheduling, device drivers -- is exposed as a
  small, swappable interface (`xr_os.tracking`, `xr_os.slam`,
  `xr_os.physics`) so it can later be backed by a native Rust/C++
  implementation without touching the rest of the platform.
- **Hardware-independent by construction.** Every perception/tracking
  interface (`VisualSlamBackend`, `ObjectDetector`, `InputDevice`,
  `Actuator`, `DigitalTwinSource`, ...) is an abstract contract. Real
  hardware bindings and the deterministic simulator in `xr_os.simulation`
  are just two implementations of the same interface.
- **Spatial data is sensitive by default.** Nothing in `xr_os.security` is
  auto-granted: an application only sees the camera, microphone, spatial
  map, eye-tracking or hand-tracking data it has been explicitly permitted.
- **The whole OS runs without a headset.** `xr_os.simulation` provides a
  deterministic virtual headset, hands, room and camera so applications can
  be developed, demoed and tested on an ordinary computer, in CI, with no
  hardware attached.

## Architecture

```
                         XR-OS
                           |
        +------------------+------------------+
        v                  v                  v
     SENSORS          SPATIAL WORLD         INPUT
        |                  |                  |
        +------------------+------------------+
                           |
                      XR RUNTIME
                           |
        +-------------------+-------------------+
        v                   v                   v
    RENDERING            PHYSICS              AUDIO
        |                   |                   |
        +-------------------+-------------------+
                           |
                SPATIAL APPLICATIONS
                           |
                   HUMAN EXPERIENCE
```

## Module map

| Package | What it is |
|---|---|
| `xr_os.core` | `Vector3` / `Quaternion` / `Transform` math, the universal `SpatialObject`, the `SpatialWorldModel`, and the `EventBus` every subsystem publishes onto. |
| `xr_os.tracking` | `TrackingEngine`: fuses IMU + visual + depth + controller/hand samples into unified head/hand/controller poses. |
| `xr_os.slam` | `SpatialMap`: point clouds, mesh reconstruction, RANSAC plane detection, and the `VisualSlamBackend` interface. |
| `xr_os.anchors` | `SpatialAnchorEngine`: local, persistent, object-, room- and geographic anchors that keep virtual content attached to the real world. |
| `xr_os.modes` | `XRModeManager`: AR / VR / MR, switchable at runtime, each with its own passthrough/collision/visibility capabilities. |
| `xr_os.scene` | `XRSceneGraph`: `ROOM` (mirrored physical geometry) + `VIRTUAL WORLD` (authored content), with transform inheritance, visibility, collision, interaction and per-app permissions. |
| `xr_os.ui` | Spatial UI: `SpatialPanel`, `Button3D`, `Menu`, `Toolbar`, `Notification`, `VirtualKeyboard`, `VoiceInterface`, anchorable to head/hand/room/object/world. |
| `xr_os.input` | `InputEngine`: controllers, hands, gaze, voice, keyboard, mouse, touch, all mapped onto one event vocabulary (`POINT GRAB PINCH CLICK LOOK MOVE ROTATE SPEAK TOUCH`). |
| `xr_os.audio` | `SpatialAudioEngine`: 3D sources, listener, distance attenuation, panning, occlusion, room effects. |
| `xr_os.haptics` | `HapticEngine`: the `COLLISION -> PHYSICS -> HAPTIC EVENT -> ACTUATOR` pipeline. |
| `xr_os.physics` | `XRPhysicsEngine`: gravity, sphere-collider rigid bodies, static planes from the reconstructed room, grabbing, throwing. |
| `xr_os.vision` | Perception interfaces (detection, segmentation, hand/pose/depth) plus genuinely-functional OpenCV baselines and a `ScenePerceptionPipeline` that lifts 2D detections into the world model. |
| `xr_os.memory` | `SpatialMemory`: persistent, hierarchical, SQLite-backed record of previously mapped places, with room re-recognition from a geometric fingerprint. |
| `xr_os.runtime` | `XRWorld` / `XRApp`: the application framework, plus `XRServices` -- the OS-style service locator (mapping, tracking, audio, input, haptics, scene, notifications, permissions, profiles, lifecycle, storage). |
| `xr_os.security` | `PermissionManager` (per-app, per-scope grants) and `EncryptedStorage` (local-first, Fernet-encrypted). |
| `xr_os.multiuser` | Shared spatial experiences over WebSockets/FastAPI: user pose, object ownership, anchors, input events. |
| `xr_os.digital_twin` | `DigitalTwinConnector`: mirrors an external digital twin's live assets/telemetry into the spatial world. |
| `xr_os.simulation` | Deterministic virtual headset, hands, room, camera and sensors -- the whole OS runs headless for dev and CI. |
| `xr_os.dashboard` | A FastAPI diagnostic API and a `rich` terminal dashboard: tracking quality, spatial map, scene, frame timing, network. |

## Install

```bash
cd xr-os
pip install -e .
# optional extras:
pip install -e ".[vision]"      # opencv / torch
pip install -e ".[geometry]"    # open3d (mesh reconstruction, voxel downsampling)
pip install -e ".[dashboard]"   # rich (terminal dashboard)
pip install -e ".[dev]"         # pytest, httpx, ...
```

## Quickstart

```python
from xr_os.runtime.app import XRApp, XRWorld
from xr_os.ui.elements import SpatialPanel

world = XRWorld()
panel = SpatialPanel(position=(1, 0, -2), size=(1.5, 0.8))
world.add(panel)
world.run(max_frames=180)  # ~2s at 90Hz; omit max_frames to run until stopped
```

Run it headless against the deterministic simulator instead of real
hardware:

```python
from xr_os.runtime.app import XRWorld
from xr_os.simulation.sim_env import SimulatedXREnvironment

world = XRWorld()
env = SimulatedXREnvironment(services=world.services)
for _ in range(180):
    env.step(1 / 90)
    world.tick(1 / 90)
```

See `examples/hello_panel.py`, `examples/simulated_room_demo.py` and
`examples/multiuser_demo.py` for complete, runnable programs.

## Testing

```bash
pip install -e ".[dev]"
pytest
```

The suite covers spatial mathematics, the world model, the scene graph,
tracking fusion, SLAM/plane detection, spatial anchors, physics
(gravity/collision/grab/throw), the input engine, spatial audio, haptics,
persistent spatial memory, computer-vision perception, the multi-user
WebSocket protocol, the application runtime, permissions, the dashboard,
and the deterministic simulator itself -- including a determinism test
(two independent simulated runs produce bit-identical trajectories) and a
handful of generous, CI-stable performance benchmarks.

## What's real vs. what's an interface

Everything in this repository runs and is tested. Where a subsystem's real
implementation depends on hardware or a heavyweight model (a specific
headset's SLAM, a production object-detection model, a real haptic glove),
XR-OS ships a small abstract interface plus either a genuinely-functional
classical baseline (e.g. `ColorBlobDetector`, `NaivePlaneDetector`,
`StereoDepthEstimator` -- real OpenCV, not stubs) or a deterministic
simulated implementation (`xr_os.simulation`) -- never a fake that only
looks like it works.
