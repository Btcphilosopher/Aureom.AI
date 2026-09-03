"""
Spatial mathematics primitives used throughout XR-OS.

These are deliberately small, numpy-backed, and dependency-free of pydantic
so they can be used both inside data models (as plain tuples on the wire)
and in hot loops (tracking fusion, physics, scene-graph transform folding).

This is the one module in the whole platform where a future Rust/C++
implementation would plug in first (see ``xr_os.tracking`` and
``xr_os.physics`` for where the hot loops that depend on it live).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

Vec3Tuple = tuple[float, float, float]
QuatTuple = tuple[float, float, float, float]  # (x, y, z, w)


@dataclass(frozen=True, slots=True)
class Vector3:
    """A point or direction in 3D space, in meters, right-handed Y-up."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def zero(cls) -> "Vector3":
        return cls(0.0, 0.0, 0.0)

    @classmethod
    def one(cls) -> "Vector3":
        return cls(1.0, 1.0, 1.0)

    @classmethod
    def from_array(cls, arr: Iterable[float]) -> "Vector3":
        x, y, z = (float(v) for v in arr)
        return cls(x, y, z)

    @classmethod
    def from_tuple(cls, t: Vec3Tuple) -> "Vector3":
        return cls(float(t[0]), float(t[1]), float(t[2]))

    def as_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=np.float64)

    def as_tuple(self) -> Vec3Tuple:
        return (self.x, self.y, self.z)

    def __add__(self, other: "Vector3") -> "Vector3":
        return Vector3.from_array(self.as_array() + other.as_array())

    def __sub__(self, other: "Vector3") -> "Vector3":
        return Vector3.from_array(self.as_array() - other.as_array())

    def __mul__(self, scalar: float) -> "Vector3":
        return Vector3.from_array(self.as_array() * scalar)

    __rmul__ = __mul__

    def __neg__(self) -> "Vector3":
        return self * -1.0

    def dot(self, other: "Vector3") -> float:
        return float(np.dot(self.as_array(), other.as_array()))

    def cross(self, other: "Vector3") -> "Vector3":
        return Vector3.from_array(np.cross(self.as_array(), other.as_array()))

    def length(self) -> float:
        return float(np.linalg.norm(self.as_array()))

    def distance_to(self, other: "Vector3") -> float:
        return (self - other).length()

    def normalized(self) -> "Vector3":
        n = self.length()
        if n < 1e-12:
            return Vector3.zero()
        return self * (1.0 / n)

    def lerp(self, other: "Vector3", t: float) -> "Vector3":
        t = max(0.0, min(1.0, t))
        return self + (other - self) * t


@dataclass(frozen=True, slots=True)
class Quaternion:
    """Orientation as a unit quaternion, Hamilton convention, (x, y, z, w)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    @classmethod
    def identity(cls) -> "Quaternion":
        return cls(0.0, 0.0, 0.0, 1.0)

    @classmethod
    def from_tuple(cls, t: QuatTuple) -> "Quaternion":
        return cls(float(t[0]), float(t[1]), float(t[2]), float(t[3]))

    @classmethod
    def from_axis_angle(cls, axis: Vector3, angle_rad: float) -> "Quaternion":
        axis = axis.normalized()
        half = angle_rad * 0.5
        s = math.sin(half)
        return cls(axis.x * s, axis.y * s, axis.z * s, math.cos(half))

    @classmethod
    def from_euler(cls, roll: float, pitch: float, yaw: float) -> "Quaternion":
        """Roll (X), pitch (Y), yaw (Z), intrinsic, radians."""
        cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
        cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
        cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
        return cls(
            x=sr * cp * cy - cr * sp * sy,
            y=cr * sp * cy + sr * cp * sy,
            z=cr * cp * sy - sr * sp * cy,
            w=cr * cp * cy + sr * sp * sy,
        )

    def as_tuple(self) -> QuatTuple:
        return (self.x, self.y, self.z, self.w)

    def normalized(self) -> "Quaternion":
        n = math.sqrt(self.x**2 + self.y**2 + self.z**2 + self.w**2)
        if n < 1e-12:
            return Quaternion.identity()
        return Quaternion(self.x / n, self.y / n, self.z / n, self.w / n)

    def conjugate(self) -> "Quaternion":
        return Quaternion(-self.x, -self.y, -self.z, self.w)

    def multiply(self, other: "Quaternion") -> "Quaternion":
        """Compose rotations: self applied after other (self * other)."""
        x1, y1, z1, w1 = self.x, self.y, self.z, self.w
        x2, y2, z2, w2 = other.x, other.y, other.z, other.w
        return Quaternion(
            x=w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            y=w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            z=w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w=w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        )

    __mul__ = multiply

    def rotate(self, v: Vector3) -> Vector3:
        qv = Quaternion(v.x, v.y, v.z, 0.0)
        result = self.multiply(qv).multiply(self.conjugate())
        return Vector3(result.x, result.y, result.z)

    def to_matrix(self) -> np.ndarray:
        x, y, z, w = self.x, self.y, self.z, self.w
        return np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ],
            dtype=np.float64,
        )

    def slerp(self, other: "Quaternion", t: float) -> "Quaternion":
        t = max(0.0, min(1.0, t))
        a = np.array(self.as_tuple())
        b = np.array(other.as_tuple())
        dot = float(np.dot(a, b))
        if dot < 0.0:
            b = -b
            dot = -dot
        if dot > 0.9995:
            result = a + t * (b - a)
            return Quaternion.from_tuple(tuple(result)).normalized()
        theta_0 = math.acos(max(-1.0, min(1.0, dot)))
        theta = theta_0 * t
        sin_theta_0 = math.sin(theta_0)
        s0 = math.cos(theta) - dot * math.sin(theta) / sin_theta_0
        s1 = math.sin(theta) / sin_theta_0
        result = s0 * a + s1 * b
        return Quaternion.from_tuple(tuple(result)).normalized()


@dataclass(frozen=True, slots=True)
class Transform:
    """A rigid(+scale) transform: position, rotation, scale."""

    position: Vector3 = Vector3.zero()
    rotation: Quaternion = Quaternion.identity()
    scale: Vector3 = Vector3.one()

    @classmethod
    def identity(cls) -> "Transform":
        return cls(Vector3.zero(), Quaternion.identity(), Vector3.one())

    def combine(self, child: "Transform") -> "Transform":
        """Compose ``child`` (local) under ``self`` (parent) into world space."""
        world_scale = Vector3(
            self.scale.x * child.scale.x,
            self.scale.y * child.scale.y,
            self.scale.z * child.scale.z,
        )
        scaled_pos = Vector3(
            child.position.x * self.scale.x,
            child.position.y * self.scale.y,
            child.position.z * self.scale.z,
        )
        world_pos = self.position + self.rotation.rotate(scaled_pos)
        world_rot = self.rotation.multiply(child.rotation)
        return Transform(world_pos, world_rot, world_scale)

    def transform_point(self, point: Vector3) -> Vector3:
        scaled = Vector3(point.x * self.scale.x, point.y * self.scale.y, point.z * self.scale.z)
        return self.position + self.rotation.rotate(scaled)

    def inverse(self) -> "Transform":
        inv_rot = self.rotation.conjugate()
        inv_scale = Vector3(
            1.0 / self.scale.x if self.scale.x else 0.0,
            1.0 / self.scale.y if self.scale.y else 0.0,
            1.0 / self.scale.z if self.scale.z else 0.0,
        )
        inv_pos = inv_rot.rotate(-self.position)
        inv_pos = Vector3(inv_pos.x * inv_scale.x, inv_pos.y * inv_scale.y, inv_pos.z * inv_scale.z)
        return Transform(inv_pos, inv_rot, inv_scale)
