"""
Performance benchmarks.

These assert generous upper bounds (not tight timing gates) so they stay
stable in CI while still catching a real algorithmic regression -- e.g. an
accidental O(n^3) creeping into the physics broad phase.
"""

import time

from xr_os.core.math3d import Vector3
from xr_os.physics.engine import RigidBody, StaticPlane, XRPhysicsEngine
from xr_os.simulation.sim_env import SimulatedXREnvironment


def test_physics_step_scales_reasonably_with_body_count():
    engine = XRPhysicsEngine()
    engine.add_plane(StaticPlane(point=Vector3.zero(), normal=Vector3(0, 1, 0)))
    for i in range(100):
        engine.add_body(RigidBody(position=Vector3(i * 0.05, 1.0 + (i % 5) * 0.1, 0), radius=0.05))

    start = time.perf_counter()
    for _ in range(120):  # ~1.3s of simulated time at 90Hz
        engine.step(1 / 90)
    elapsed = time.perf_counter() - start

    assert elapsed < 10.0  # generous: real-time XR needs ~11ms/frame at this scale, not 83ms


def test_simulated_environment_runs_a_second_of_frames_quickly():
    env = SimulatedXREnvironment()
    start = time.perf_counter()
    env.run(steps=90)  # 1 simulated second at 90Hz
    elapsed = time.perf_counter() - start
    assert elapsed < 15.0


def test_scene_graph_raycast_scales_to_hundreds_of_nodes(scene_graph):
    from xr_os.core.math3d import Transform
    from xr_os.scene.nodes import ModelNode

    for i in range(500):
        node = ModelNode(f"obj_{i}", local_transform=Transform(Vector3(i * 0.1, 10, 10)))
        scene_graph.add_virtual(node)
    target = ModelNode("target", local_transform=Transform(Vector3(0, 0, -2)))
    scene_graph.add_virtual(target)

    start = time.perf_counter()
    for _ in range(200):
        scene_graph.raycast(Vector3.zero(), Vector3(0, 0, -1))
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
