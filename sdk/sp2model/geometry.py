"""Finite, explicit geometry for the native SP2 modelling plan.

Positions use metres at the protocol boundary. Quaternions are xyzw. Frames
contain a frozen rigid pose; scale is intentionally not a coordinate system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from collections.abc import Mapping
from .errors import ModelingError


class GeometryError(ModelingError, ValueError):
    """An intent cannot be represented with the supported native geometry."""
    def __init__(self, message):
        ModelingError.__init__(self, "invalid_geometry", message)


def number(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GeometryError(f"{name} must be a finite number")
    value = float(value)
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise GeometryError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def vector(value, name="vector", length=3):
    if isinstance(value, (str, bytes, Mapping)):
        raise GeometryError(f"{name} requires {length} numbers")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise GeometryError(f"{name} requires {length} numbers") from exc
    if len(values) != length:
        raise GeometryError(f"{name} requires {length} numbers")
    return tuple(number(v, name) for v in values)


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scale(a, value):
    return tuple(x * value for x in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def magnitude(a):
    return math.sqrt(dot(a, a))


def unit(a, name="axis"):
    a = vector(a, name)
    length = magnitude(a)
    if length < 1e-12:
        raise GeometryError(f"{name} must have nonzero length")
    return scale(a, 1.0 / length)


def quaternion(value, name="rotation_quaternion"):
    q = vector(value, name, 4)
    length = magnitude(q)
    if abs(length - 1) > 1e-6:
        raise GeometryError(f"{name} must be a unit xyzw quaternion")
    return scale(q, 1.0 / length)


def normalized_rotation(value, name="rotation_quaternion"):
    """Normalize a finite nonzero rotation for comparison, without magnitude bias."""
    q = vector(value, name, 4)
    largest = max(abs(v) for v in q)
    if largest == 0:
        raise GeometryError(f"{name} must have nonzero norm")
    q = tuple(v / largest for v in q)
    length = math.hypot(*q)
    return tuple(v / length for v in q)


def rotation_distance_degrees(first, second):
    """Physical rotation angle, stable for tiny differences and q == -q."""
    a = normalized_rotation(first, "actual rotation")
    b = normalized_rotation(second, "target rotation")
    if dot(a, b) < 0:
        b = tuple(-v for v in b)
    # Unit-quaternion chord lengths avoid acos's loss of tiny rotations.
    return math.degrees(4 * math.atan2(math.hypot(*sub(a, b)), math.hypot(*add(a, b))))


def multiply(a, b):
    """Compose unit quaternions: b acts first, then a."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return quaternion((aw*bx + ax*bw + ay*bz - az*by,
                       aw*by - ax*bz + ay*bw + az*bx,
                       aw*bz + ax*by - ay*bx + az*bw,
                       aw*bw - ax*bx - ay*by - az*bz))


def rotate(q, v):
    u, w = q[:3], q[3]
    return add(add(scale(u, 2*dot(u, v)), scale(v, w*w-dot(u, u))), scale(cross(u, v), 2*w))


def axis_angle(axis, *, angle_deg=None, angle_rad=None):
    if (angle_deg is None) == (angle_rad is None):
        raise GeometryError("Specify exactly one of angle_deg or angle_rad")
    angle = math.radians(number(angle_deg, "angle_deg")) if angle_deg is not None else number(angle_rad, "angle_rad")
    return quaternion((*scale(unit(axis), math.sin(angle/2)), math.cos(angle/2)))


def look_rotation(forward, up):
    """Map local +Z to forward; project the requested up onto its normal plane."""
    z = unit(forward, "end - start")
    y_hint = unit(up, "up")
    x = unit(cross(y_hint, z), "up cross forward (choose a nonparallel up)")
    y = cross(z, x)
    m = [[x[i], y[i], z[i]] for i in range(3)]
    trace = sum(m[i][i] for i in range(3))
    if trace > 0:
        s = 2 * math.sqrt(trace + 1)
        return quaternion(((m[2][1]-m[1][2])/s, (m[0][2]-m[2][0])/s, (m[1][0]-m[0][1])/s, s/4))
    i = max(range(3), key=lambda j: m[j][j])
    j, k = (i + 1) % 3, (i + 2) % 3
    s = 2 * math.sqrt(max(0, 1 + m[i][i] - m[j][j] - m[k][k]))
    q = [0., 0., 0., 0.]
    q[i], q[j], q[k], q[3] = s/4, (m[j][i]+m[i][j])/s, (m[k][i]+m[i][k])/s, (m[k][j]-m[j][k])/s
    return quaternion(q)


@dataclass(frozen=True)
class Frame:
    """Frozen rigid pose in world metres; native craft/part poses are captured once."""
    kind: str = "world"
    position: tuple = (0., 0., 0.)
    rotation_quaternion: tuple = (0., 0., 0., 1.)
    _binding: tuple | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.kind not in ("world", "custom"):
            raise GeometryError("Frame kind must be world or custom; capture a craft/part pose first")
        object.__setattr__(self, "position", vector(self.position, "frame.position"))
        object.__setattr__(self, "rotation_quaternion", quaternion(self.rotation_quaternion))
        if self._binding is not None:
            if isinstance(self._binding, (str, bytes)):
                raise GeometryError("Frame binding requires an identity tuple")
            try:
                binding = tuple(self._binding)
            except TypeError as exc:
                raise GeometryError("Frame binding requires an identity tuple") from exc
            if len(binding) != 4 or any(not isinstance(v, (str, int, float, bool, type(None))) for v in binding):
                raise GeometryError("Frame binding requires four immutable identity values")
            object.__setattr__(self, "_binding", binding)
        if self.kind == "world" and (self.position != (0., 0., 0.) or self.rotation_quaternion != (0., 0., 0., 1.)):
            raise GeometryError("World frame has identity pose; use Frame.custom for an offset pose")

    @classmethod
    def world(cls):
        return cls()

    @classmethod
    def custom(cls, position=(0, 0, 0), rotation_quaternion=(0, 0, 0, 1)):
        return cls("custom", position, rotation_quaternion)

    @classmethod
    def from_pose(cls, pose, binding=None):
        """Capture a native pose with optional instance/session/revision binding.

        The binding is SDK metadata only. It is validated by the Session and
        never emitted as part of a native transform frame.
        """
        return cls("custom", pose["position"], pose["rotationQuaternion"], binding)

    def point(self, value):
        return add(self.position, rotate(self.rotation_quaternion, vector(value)))

    def direction(self, value):
        return rotate(self.rotation_quaternion, vector(value))

    def orientation(self, value):
        return multiply(self.rotation_quaternion, quaternion(value))

    def child(self, position=(0, 0, 0), rotation_quaternion=(0, 0, 0, 1)):
        """Freeze a local child pose in this frame; position always uses metres.

        The child quaternion acts in this frame's local axes. Native capture
        binding is inherited, so deriving a child cannot revive a stale frame.
        """
        return Frame("custom", self.point(position), self.orientation(rotation_quaternion), self._binding)

    def translated(self, local_metres):
        """Return a child shifted along local axes, preserving orientation."""
        return self.child(position=local_metres)

    def rotated(self, axis, *, angle_deg=None, angle_rad=None):
        """Rotate local axes about this origin; specify exactly one angle unit."""
        return self.child(rotation_quaternion=axis_angle(axis, angle_deg=angle_deg, angle_rad=angle_rad))

    def to_dict(self):
        if self.kind == "world":
            return {"kind": "world"}
        return {"kind": "custom", "position": list(self.position), "rotationQuaternion": list(self.rotation_quaternion)}


CORNERS = ("topLeft", "topRight", "bottomRight", "bottomLeft")
EDGES = ("top", "right", "bottom", "left")


def _named(value, names, label, validate):
    if isinstance(value, Mapping):
        if set(value) != set(names):
            raise GeometryError(f"{label} must specify exactly {', '.join(names)}")
        return tuple(validate(value[k], f"{label}.{k}") for k in names)
    return tuple(validate(value, label) for _ in names)


def _boolean(value, label):
    if not isinstance(value, bool):
        raise GeometryError(f"{label} must be boolean")
    return value


@dataclass(frozen=True)
class Section:
    """Native fuselage section. Distances use the plan's length unit.

    corner_radius is a distance unless corner_stretch is true, in which case it
    is a fraction. Curved's middle Section is a control shape, not a measured
    surface cross-section. Cuts are fractions, None means native automatic.
    """
    width: float
    height: float
    corner_radius: object = 0.
    corner_stretch: object = False
    trapezium: float = 0.
    edge_curvature: object = 0.
    cutting: object = None
    smoothing: bool | None = None
    sync_adjacent: bool | None = None
    thickness_fraction: float = .1

    def __post_init__(self):
        object.__setattr__(self, "width", number(self.width, "width", 0))
        object.__setattr__(self, "height", number(self.height, "height", 0))
        radii = _named(self.corner_radius, CORNERS, "corner_radius", lambda v, n: number(v, n, 0))
        stretch = _named(self.corner_stretch, CORNERS, "corner_stretch", _boolean)
        if any(s and r > 1 for r, s in zip(radii, stretch)):
            raise GeometryError("Stretched corner radii must be fractions in [0, 1]")
        object.__setattr__(self, "corner_radius", radii)
        object.__setattr__(self, "corner_stretch", stretch)
        object.__setattr__(self, "trapezium", number(self.trapezium, "trapezium", -1, 1))
        object.__setattr__(self, "edge_curvature", _named(self.edge_curvature, EDGES, "edge_curvature", lambda v, n: number(v, n, 0, 1)))
        cuts = _named(self.cutting, EDGES, "cutting", lambda v, n: None if v is None else number(v, n, 0, 1))
        if (cuts[0] or 0)+(cuts[2] or 0) >= 1 or (cuts[1] or 0)+(cuts[3] or 0) >= 1:
            raise GeometryError("Opposite cuts must sum to less than one")
        object.__setattr__(self, "cutting", cuts)
        for key in ("smoothing", "sync_adjacent"):
            if getattr(self, key) is not None:
                _boolean(getattr(self, key), key)
        object.__setattr__(self, "thickness_fraction", number(self.thickness_fraction, "thickness_fraction", .01, 1))

    def to_patch(self, index, *, unit_scale=1., role="end"):
        if role not in ("end", "cone_tip", "curve_control"):
            raise GeometryError("Unknown native section role")
        if role != "end" and (self.smoothing is not None or self.sync_adjacent is not None):
            raise GeometryError(f"{role} has no smoothing or sync_adjacent capability")
        if role == "curve_control" and any(v is not None for v in self.cutting):
            raise GeometryError("curve_control has no cutting capability")
        result = {"index": index, "width": number(self.width*unit_scale, "width metres", 0, 1000),
                  "height": number(self.height*unit_scale, "height metres", 0, 1000),
                  "trapezium": self.trapezium, "thicknessFraction": self.thickness_fraction,
                  "cornerRadius": {k: number(v if s else v*unit_scale, "corner radius", 0, 1 if s else 1000) for k, v, s in zip(CORNERS, self.corner_radius, self.corner_stretch)},
                  "cornerStretch": dict(zip(CORNERS, self.corner_stretch)),
                  "edgeCurvature": dict(zip(EDGES, self.edge_curvature))}
        if role == "end":
            result.update(smoothing=False if self.smoothing is None else self.smoothing,
                          syncAdjacent=False if self.sync_adjacent is None else self.sync_adjacent)
        if role != "curve_control":
            result["cutting"] = dict(zip(EDGES, self.cutting))
        return result
