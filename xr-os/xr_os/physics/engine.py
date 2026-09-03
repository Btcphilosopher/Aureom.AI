"""
XR Physics: gravity, sphere-collider rigid bodies, static planes (the
reconstructed floor/walls/tables from SLAM), grabbing and throwing.

Deliberately simple (sphere colliders, semi-implicit Euler integration) --
real-time correctness at XR frame rates matters more than full 6DoF rigid
body dynamics here, and this is exactly the kind of hot loop the platform
expects to eventually move to a native (Rust/C++) implementation behind the
same API (see ``xr_os/__init__.py``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from xr_os.core.math3d import Vector3

DEFAULT_GRAVITY = Vector3(0.0, -9.81, 0.0)


@dataclass
class StaticPlane:
    """An immovable collision surface, typically the reconstructed floor/wall/table."""

    point: Vector3
    normal: Vector3
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    label: str | None = None

    def signed_distance(self, point: Vector3) -> float:
        n = self.normal.normalized()
        return (point - self.point).dot(n)


@dataclass
class RigidBody:
    """A simplified rigid body: a sphere collider with mass, velocity and restitution."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    position: Vector3 = field(default_factory=Vector3.zero)
    velocity: Vector3 = field(default_factory=Vector3.zero)
    radius: float = 0.1
    mass: float = 1.0
    restitution: float = 0.4  # bounciness, 0 = inelastic, 1 = perfectly elastic
    friction: float = 0.1
    is_static: bool = False
    grabbed_by: str | None = None
    node_id: str | None = None  # optional linked SceneNode to keep in sync

    @property
    def is_grabbed(self) -> bool:
        return self.grabbed_by is not None


@dataclass
class CollisionContact:
    """One collision event, the input to the haptics pipeline: COLLISION -> PHYSICS -> HAPTIC EVENT."""

    body_id: str
    other_id: str  # another body's id, or a StaticPlane's id
    point: Vector3
    normal: Vector3
    impulse: float  # magnitude of the impulse applied, used to scale haptic intensity


class XRPhysicsEngine:
    """A simplified real-time physics world for XR virtual objects."""

    def __init__(self, gravity: Vector3 = DEFAULT_GRAVITY) -> None:
        self.gravity = gravity
        self.bodies: dict[str, RigidBody] = {}
        self.planes: list[StaticPlane] = []
        self._grab_last_position: dict[str, Vector3] = {}

    # -- world setup -------------------------------------------------

    def add_body(self, body: RigidBody) -> RigidBody:
        self.bodies[body.id] = body
        return body

    def remove_body(self, body_id: str) -> None:
        self.bodies.pop(body_id, None)
        self._grab_last_position.pop(body_id, None)

    def add_plane(self, plane: StaticPlane) -> StaticPlane:
        self.planes.append(plane)
        return plane

    def sync_planes_from_spatial_map(self, spatial_map) -> None:
        """Rebuild static collision planes from a ``xr_os.slam.SpatialMap``'s detected planes."""
        self.planes = [StaticPlane(point=p.point, normal=p.normal, label=p.plane_type.value) for p in spatial_map.planes]

    # -- grabbing / throwing -------------------------------------------

    def grab(self, body_id: str, holder_id: str) -> None:
        body = self.bodies[body_id]
        body.grabbed_by = holder_id
        body.velocity = Vector3.zero()
        self._grab_last_position[body_id] = body.position

    def move_grabbed(self, body_id: str, new_position: Vector3, dt: float) -> None:
        """Follow a hand/controller each frame while grabbed; tracks velocity for a later throw."""
        body = self.bodies[body_id]
        if not body.is_grabbed:
            return
        last = self._grab_last_position.get(body_id, body.position)
        if dt > 1e-6:
            body.velocity = (new_position - last) * (1.0 / dt)
        body.position = new_position
        self._grab_last_position[body_id] = new_position

    def release(self, body_id: str, throw_velocity: Vector3 | None = None) -> None:
        body = self.bodies[body_id]
        body.grabbed_by = None
        if throw_velocity is not None:
            body.velocity = throw_velocity
        self._grab_last_position.pop(body_id, None)

    # -- simulation step -------------------------------------------------

    def step(self, dt: float) -> list[CollisionContact]:
        contacts: list[CollisionContact] = []
        dynamic = [b for b in self.bodies.values() if not b.is_static and not b.is_grabbed]

        for body in dynamic:
            body.velocity = body.velocity + self.gravity * dt
            body.position = body.position + body.velocity * dt

        for body in dynamic:
            for plane in self.planes:
                dist = plane.signed_distance(body.position) - body.radius
                if dist < 0:
                    normal = plane.normal.normalized()
                    body.position = body.position - normal * dist  # push out of the surface
                    speed_into = body.velocity.dot(normal)
                    if speed_into < 0:
                        impulse = -(1 + body.restitution) * speed_into
                        body.velocity = body.velocity + normal * impulse
                        # simple tangential friction damping
                        tangent_velocity = body.velocity - normal * body.velocity.dot(normal)
                        body.velocity = body.velocity - tangent_velocity * body.friction
                        contacts.append(
                            CollisionContact(
                                body_id=body.id,
                                other_id=plane.id,
                                point=body.position - normal * body.radius,
                                normal=normal,
                                impulse=abs(impulse) * body.mass,
                            )
                        )

        bodies_list = list(self.bodies.values())
        for i in range(len(bodies_list)):
            for j in range(i + 1, len(bodies_list)):
                a, b = bodies_list[i], bodies_list[j]
                if a.is_static and b.is_static:
                    continue
                delta = b.position - a.position
                dist = delta.length()
                min_dist = a.radius + b.radius
                if dist < min_dist and dist > 1e-9:
                    normal = delta * (1.0 / dist)
                    overlap = min_dist - dist
                    if not a.is_static and not a.is_grabbed:
                        a.position = a.position - normal * (overlap * 0.5)
                    if not b.is_static and not b.is_grabbed:
                        b.position = b.position + normal * (overlap * 0.5)
                    relative_velocity = b.velocity - a.velocity
                    speed_along_normal = relative_velocity.dot(normal)
                    if speed_along_normal < 0:
                        restitution = min(a.restitution, b.restitution)
                        inv_mass_a = 0.0 if (a.is_static or a.is_grabbed) else 1.0 / max(a.mass, 1e-6)
                        inv_mass_b = 0.0 if (b.is_static or b.is_grabbed) else 1.0 / max(b.mass, 1e-6)
                        inv_mass_sum = inv_mass_a + inv_mass_b
                        if inv_mass_sum > 1e-9:
                            j_impulse = -(1 + restitution) * speed_along_normal / inv_mass_sum
                            impulse_vec = normal * j_impulse
                            if inv_mass_a:
                                a.velocity = a.velocity - impulse_vec * inv_mass_a
                            if inv_mass_b:
                                b.velocity = b.velocity + impulse_vec * inv_mass_b
                            contacts.append(
                                CollisionContact(body_id=a.id, other_id=b.id, point=a.position + normal * a.radius, normal=normal, impulse=abs(j_impulse))
                            )
        return contacts
