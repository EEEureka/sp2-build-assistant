"""Object-oriented, side-effect-free compiler for native modelling batches."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from contextlib import contextmanager
import json
import uuid

from .geometry import (Frame, Section, GeometryError, add, sub, scale, vector,
                       number, magnitude, quaternion, axis_angle, look_rotation,
                       rotate, multiply)
from .semantic import SphericalPlanMixin
from .wings import WingPlanMixin


@dataclass(frozen=True)
class PlannedPart:
    name: str
    temporary_id: str
    expected: dict
    _owner: str = field(repr=False)

    def to_dict(self):
        return {"name": self.name, "temporaryId": self.temporary_id, "expected": deepcopy(self.expected)}


@dataclass(frozen=True)
class PlannedGroup:
    """Logical ordered members; grouping does not connect or modify native parts."""
    name: str
    parts: tuple
    _owner: str = field(repr=False)
    _references: tuple = field(repr=False)

    def __iter__(self):
        return iter(self.parts)

    def __len__(self):
        return len(self.parts)

    def __getitem__(self, index):
        return self.parts[index]


@dataclass(frozen=True)
class PlannedSetter:
    variable: str
    key: str
    _owner: str = field(repr=False)


class Plan(SphericalPlanMixin,WingPlanMixin):
    """A frozen-baseline plan. Construction and Python iteration never write.

    ``writable`` bounds existing objects; new objects belong to this plan.
    None delegates scope review to the Session's preview. Native dependency
    and indirect-change guards are still required at execution time.
    """
    def __init__(self, session, frame=None, length_unit="m", writable=None, variables=()):
        if length_unit not in {"m", "cm", "mm"}:
            raise GeometryError("length_unit must be m, cm or mm")
        if frame is not None and not isinstance(frame, Frame):
            raise GeometryError("frame must be a captured Frame")
        self.session = session
        self.frame = frame or Frame.world()
        validate_frame = getattr(session, "_validate_frame", None)
        if callable(validate_frame):
            validate_frame(self.frame)
        self.length_unit = length_unit
        self.unit_scale = {"m": 1., "cm": .01, "mm": .001}[length_unit]
        self.baseline_identity = deepcopy(session.identity)
        self.frozen_baseline_identity = deepcopy(self.baseline_identity)
        self._baseline = deepcopy(session._snapshot)
        self._owner = uuid.uuid4().hex
        self.operations = []
        self.objects = {}
        self.groups = {}
        self._shapes = {}
        self.semantic_shapes = {}
        self._mechanical = {}
        self._shape_sources = {}
        self._poses = {p["id"]: {"position": deepcopy(p["position"]), "rotationQuaternion": deepcopy(p["rotationQuaternion"])}
                       for p in self._baseline.get("parts", []) if "position" in p and "rotationQuaternion" in p}
        self.expectations = []
        self._deleted = set()
        self.writable_part_ids = None if writable is None else frozenset(session._resolve_ref(p) for p in writable)
        if isinstance(variables,str):raise GeometryError("variables must be an explicit collection of native Setter names")
        try:variables=tuple(variables)
        except TypeError:raise GeometryError("variables must be an explicit collection of native Setter names") from None
        if any(not isinstance(v,str) or not v.strip() for v in variables):
            raise GeometryError("variables must explicitly list reviewed native Setter names")
        self.variable_names=frozenset(variables)
        native_vars=self._baseline.get("variables") or {}
        self._setter_names=[row["attributes"].get("variable") for row in native_vars.get("children",[]) if row.get("element",row.get("name"))=="Setter"]
        self._setter_keys=list(range(len(self._setter_names)))

    def _current(self):
        if self.session.identity != self.frozen_baseline_identity:
            raise GeometryError("Plan baseline changed; create a new plan from the inspected session")

    def _ref(self, value, *, writable=True):
        self._current()
        if isinstance(value, PlannedPart):
            if value._owner != self._owner or self.objects.get(value.name) is not value:
                raise GeometryError("Planned object belongs to another plan")
            ref = value.temporary_id
        else:
            ref = self.session._resolve_ref(value)
            if writable and self.writable_part_ids is not None and ref not in self.writable_part_ids:
                raise GeometryError(f"Part {ref} is outside this plan's writable objects")
        if ref in self._deleted:
            raise GeometryError("Object was deleted earlier in this plan")
        return ref

    def _refs(self, values):
        values = self._members(values)
        refs = [self._ref(v) for v in values]
        if not refs or len(set(refs)) != len(refs):
            raise GeometryError("Provide a nonempty set of distinct objects")
        return refs

    def _members(self, values):
        if isinstance(values, PlannedGroup):
            if values._owner != self._owner or self.groups.get(values.name) is not values:
                raise GeometryError("Logical group belongs to another plan")
            return list(values.parts)
        if isinstance(values, (set, frozenset)):
            raise GeometryError("Use an ordered list or tuple; transform anchors depend on member order")
        if isinstance(values, (list, tuple)):
            return [part for item in values for part in self._members(item)]
        return [values]

    @contextmanager
    def _atomic_edit(self):
        """Keep an invalid multi-object construction from leaving a partial plan."""
        operation_count = len(self.operations)
        objects, groups, shapes, poses = dict(self.objects), dict(self.groups), deepcopy(self._shapes), deepcopy(self._poses)
        deleted, semantics, mechanical = set(self._deleted), deepcopy(self.semantic_shapes), deepcopy(self._mechanical)
        setter_names, setter_keys = list(self._setter_names), list(self._setter_keys)
        shape_sources=dict(self._shape_sources)
        try:
            yield
        except Exception:
            del self.operations[operation_count:]
            self.objects, self.groups, self._shapes = objects, groups, shapes
            self._poses = poses
            self._deleted, self.semantic_shapes = deleted, semantics
            self._mechanical = mechanical
            self._setter_names, self._setter_keys = setter_names, setter_keys
            self._shape_sources=shape_sources
            raise

    def _append(self, *operations):
        if len(self.operations)+len(operations) > 100:
            raise GeometryError("Plan exceeds 100 native operations; use explicit separate plans and verify each boundary")
        self.operations.extend(deepcopy(operations))

    def _name(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise GeometryError("Object name must be 1..128 nonblank characters")
        if name in self.objects or name in self.groups:
            raise GeometryError(f"Duplicate logical name: {name}")

    def _point(self, value):
        result = self.frame.point(scale(vector(value, "position"), self.unit_scale))
        if magnitude(result) > 100000:
            raise GeometryError("World position must be within 100000 metres of the origin")
        return result

    @staticmethod
    def _state(template, name):
        node = template.get("defaultState", {})
        return next((x for x in node.get("children", []) if x.get("element", x.get("name")) == name), None)

    def _create(self, name, template, position, rotation, patch, expected):
        self._current()
        self._name(name)
        temporary = "model:"+name
        part = PlannedPart(name, temporary, deepcopy(expected), self._owner)
        operations = [
            {"kind": "part.add", "templateId": template["id"], "temporaryId": temporary,
             "position": list(position), "rotation": [0, 0, 0], "rootOnly": True},
            {"kind": "part.update", "partId": temporary, "symmetric": False,
             "changes": [{"path": "Part", "attribute": "scale", "value": [1, 1, 1]}]},
            {"kind": "shape.update", "partId": temporary, "patch": patch, "symmetric": False},
            {"kind": "transform.apply", "partIds": [temporary], "mode": "absolute",
             "frame": {"kind": "world"}, "position": list(position), "rotationQuaternion": list(rotation), "symmetric": False},
        ]
        self._append(*operations)
        self.objects[name] = part
        self._shapes[temporary] = {"family": expected["family"], "configuration": deepcopy(patch)}
        self._poses[temporary] = {"position": list(position), "rotationQuaternion": list(rotation)}
        return part

    def group(self, name, parts):
        """Give explicit members a logical name; creates no native connection."""
        self._name(name)
        members = self._members(parts)
        refs = self._refs(members)
        group = PlannedGroup(name, tuple(members), self._owner, tuple(refs))
        self.groups[name] = group
        return group

    def native_part(self, name, template_id, *, position=(0,0,0), rotation_quaternion=(0,0,0,1)):
        """Create one discovered native template root, retaining native defaults."""
        self._current(); self._name(name)
        template=self.session.template(template_id)
        if not template.get("creatable"):
            raise GeometryError("This native template is not creatable in the current level")
        parts=template["schema"]["parts"]
        if len(parts)!=1:
            raise GeometryError("This constructor accepts single-part templates; multi-part native assemblies need explicit group mapping")
        point=self._point(position);q=self.frame.orientation(rotation_quaternion);temporary="model:"+name
        expected={"family":"native","type":parts[0]["partType"],"implementationStrategy":"native_template_with_original_defaults","geometryStatus":"not_assessed"}
        part=PlannedPart(name,temporary,expected,self._owner)
        self._append({"kind":"part.add","templateId":template_id,"temporaryId":temporary,"position":list(point),"rotation":[0,0,0]},
                     {"kind":"transform.apply","partIds":[temporary],"mode":"absolute","frame":{"kind":"world"},"position":list(point),"rotationQuaternion":list(q),"symmetric":False})
        self.objects[name]=part;self._poses[temporary]={"position":list(point),"rotationQuaternion":list(q)}
        return part

    def retype(self, part, part_type, *, name, accept_connection_loss=False):
        """Explicit native structural replacement; old references are retired."""
        self._name(name);ref=self._ref(part)
        if accept_connection_loss is not True or not isinstance(part_type,str) or not part_type.strip():
            raise GeometryError("Retype needs a native part_type and explicit accept_connection_loss=True")
        temporary="model:"+name
        replacement=PlannedPart(name,temporary,{"family":"native","type":part_type,"geometryStatus":"not_assessed"},self._owner)
        self._append({"kind":"part.retype","partId":ref,"partType":part_type,"acceptConnectionLoss":True,"temporaryId":temporary})
        self._deleted.add(ref);self.objects[name]=replacement
        return replacement

    def _known_pose(self, part):
        ref = self._ref(part)
        row = self._poses.get(ref, {})
        if "position" not in row or "rotationQuaternion" not in row:
            raise GeometryError("Object has no known planned pose; inspect and rebind it before relative copying")
        return vector(row["position"]), quaternion(row["rotationQuaternion"])

    def _transform_known_poses(self, refs, q_world, pivot_world, shift_world):
        for ref in refs:
            pose = self._poses.get(ref)
            if pose is not None:
                pose["position"] = list(add(add(pivot_world, rotate(q_world, sub(pose["position"], pivot_world))), shift_world))
                pose["rotationQuaternion"] = list(multiply(q_world, quaternion(pose["rotationQuaternion"])))
            part = next((p for p in self.objects.values() if p.temporary_id == ref), None)
            if part is not None:
                for key in ("position", "startWorld", "endWorld"):
                    if key in part.expected:
                        part.expected[key] = list(add(add(pivot_world, rotate(q_world, sub(part.expected[key], pivot_world))), shift_world))
                if "rotationQuaternion" in part.expected:
                    part.expected["rotationQuaternion"] = list(multiply(q_world, quaternion(part.expected["rotationQuaternion"])))

    def _invalidate_poses(self, refs):
        for ref in refs:
            self._poses.pop(ref, None)
            part = next((p for p in self.objects.values() if p.temporary_id == ref), None)
            if part is not None:
                for key in ("position", "rotationQuaternion", "startWorld", "endWorld"):
                    part.expected.pop(key, None)

    def copy(self, source, name, *, translation=(0, 0, 0), rotation_quaternion=None, pivot=None):
        """Copy exact members with internal connections, detached from external edges.

        Native symmetry is unlinked on the copies. Native derived hosts and
        dependents must all be explicit group members. Translation and pivot
        use the plan frame/units; rotation is a delta in that frame.
        """
        self._name(name)
        members = self._members(source)
        refs = self._refs(members)
        as_group = isinstance(source, (PlannedGroup, list, tuple))
        names = [name+"."+str(i+1) for i in range(len(members))] if as_group else [name]
        for child_name in names:
            self._name(child_name)
        shift_local = scale(vector(translation, "translation"), self.unit_scale)
        q_local = quaternion((0, 0, 0, 1) if rotation_quaternion is None else rotation_quaternion)
        pivot_local = None if pivot is None else scale(vector(pivot, "pivot"), self.unit_scale)
        transform = rotation_quaternion is not None or any(shift_local)
        copied = []
        for member, ref, child_name in zip(members, refs, names):
            if isinstance(member, PlannedPart):
                expected = deepcopy(member.expected)
            else:
                row = next((p for p in self._baseline.get("parts", []) if p["id"] == ref), {})
                expected = {k: deepcopy(row[k]) for k in ("position", "rotationQuaternion", "type") if k in row}
                expected.update(deepcopy(self._poses.get(ref, {})))
                expected["family"] = self._existing_family(ref) or "unmapped"
            expected.update(clonedFrom=ref, geometryStatus="not_assessed")
            copied.append(PlannedPart(child_name, "model:"+child_name, expected, self._owner))
        if transform:
            frame_q = self.frame.rotation_quaternion
            inverse_frame = (-frame_q[0], -frame_q[1], -frame_q[2], frame_q[3])
            q_world = multiply(multiply(frame_q, q_local), inverse_frame)
            pivot_world = self.frame.point(pivot_local) if pivot_local is not None else self._known_pose(members[0])[0] if rotation_quaternion is not None else (0, 0, 0)
            shift_world = self.frame.direction(shift_local)
            for part in copied:
                for key in ("position", "startWorld", "endWorld"):
                    if key in part.expected:
                        part.expected[key] = list(add(add(pivot_world, rotate(q_world, sub(part.expected[key], pivot_world))), shift_world))
                if "rotationQuaternion" in part.expected:
                    part.expected["rotationQuaternion"] = list(multiply(q_world, quaternion(part.expected["rotationQuaternion"])))
        operations = [{"kind": "part.clone", "partIds": refs, "temporaryIds": [p.temporary_id for p in copied]}]
        if transform:
            op = {"kind": "transform.apply", "partIds": [p.temporary_id for p in copied], "mode": "delta",
                  "frame": self.frame.to_dict(), "translation": list(shift_local), "rotationQuaternion": list(q_local), "symmetric": False}
            if pivot_local is not None:
                op["pivot"] = list(pivot_local)
            operations.append(op)
        self._append(*operations)
        for original, part, ref in zip(members, copied, refs):
            self.objects[part.name] = part
            if "position" in part.expected and "rotationQuaternion" in part.expected:
                self._poses[part.temporary_id] = {"position": deepcopy(part.expected["position"]), "rotationQuaternion": deepcopy(part.expected["rotationQuaternion"])}
            if ref in self._shapes:
                self._shapes[part.temporary_id] = deepcopy(self._shapes[ref])
            elif part.expected.get('family') in ('fuselage','wing'):
                self._shape_sources[part.temporary_id]=self._shape_sources.get(ref,original)
        if as_group:
            return self.group(name, copied)
        return copied[0]

    @staticmethod
    def _count(count):
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
            raise GeometryError("count must be an integer 1..100, counting new copies only")
        return count

    def linear_array(self, source, name, count, step):
        """Create count new copies at step, 2*step, ..., count*step."""
        self._name(name)
        self._count(count)
        step = vector(step, "step")
        if magnitude(step) == 0:
            raise GeometryError("Array step must be nonzero")
        with self._atomic_edit():
            members = []
            for index in range(1, count+1):
                members.extend(self._members(self.copy(source, name+"_"+str(index), translation=scale(step, index))))
            return self.group(name, members)

    def radial_array(self, source, name, count, axis, *, angle_deg=None, angle_rad=None, pivot=(0, 0, 0)):
        """Create count new copies; supplied angle is the step, not total sweep."""
        self._name(name)
        self._count(count)
        axis_angle(axis, angle_deg=angle_deg, angle_rad=angle_rad)
        angle = number(angle_deg, "angle_deg") if angle_deg is not None else number(angle_rad, "angle_rad")
        if angle == 0:
            raise GeometryError("Radial array angle step must be nonzero")
        period = 360. if angle_deg is not None else 2*3.141592653589793
        if abs(angle)*count >= period-1e-9:
            raise GeometryError("Array sweep must stay below one full turn to avoid overlapping the source")
        with self._atomic_edit():
            members = []
            for index in range(1, count+1):
                q = axis_angle(axis, **({"angle_deg": angle*index} if angle_deg is not None else {"angle_rad": angle*index}))
                members.extend(self._members(self.copy(source, name+"_"+str(index), rotation_quaternion=q, pivot=pivot)))
            return self.group(name, members)

    def body(self, name, start, end, sections, style="Body", up=(0, 1, 0)):
        if style not in ("Body", "Cone", "Curved"):
            raise GeometryError("Native fuselage style must be Body, Cone or Curved")
        sections = list(sections)
        count = 3 if style == "Curved" else 2
        if len(sections) != count or any(not isinstance(s, Section) for s in sections):
            raise GeometryError(f"{style} requires exactly {count} Section objects")
        if not any(s.width > 0 and s.height > 0 for s in sections):
            raise GeometryError("At least one section needs positive width and height")
        requested_style=style
        strategy="native_"+style.lower()
        if style=="Cone":
            # Native Cone's second Slice is a curve control and its actual
            # terminal tip is always zero. A nonzero requested end therefore
            # uses native Body, which represents a frustum with exact ends.
            if sections[1].width!=0 or sections[1].height!=0:
                style="Body"
                strategy="native_body_truncated_cone"
            else:
                strategy="native_sharp_cone"
        a, b = self._point(start), self._point(end)
        length = number(magnitude(sub(b, a)), "native length metres", .001, 1000)
        q = look_rotation(sub(b, a), self.frame.direction(up))
        roles = ["end", "curve_control", "end"] if style == "Curved" else ["end", "cone_tip" if style == "Cone" else "end"]
        section_patches = [s.to_patch(i, unit_scale=self.unit_scale, role=roles[i]) for i, s in enumerate(sections)]
        patch = {"offset": [0, 0, length], "autoResize": False, "hollow": False, "glass": False, "sections": section_patches}
        if style=="Cone":patch["noseconeRoundness"]=0
        expected = {"family": "fuselage", "style": requested_style, "nativeStyle":style, "implementationStrategy":strategy, "lengthMetres": length,
                    "startWorld": list(a), "endWorld": list(b), "position": list(scale(add(a, b), .5)),
                    "rotationQuaternion": list(q), "sections": deepcopy(section_patches),
                    "sectionRoles": roles, "geometryStatus": "not_assessed"}
        return self._create(name, self.session._resolve_template(style), scale(add(a, b), .5), q, patch, expected)

    def cone(self, name, start, end, sections, up=(0, 1, 0)):
        return self.body(name, start, end, sections, style="Cone", up=up)

    def curved(self, name, start, end, sections, up=(0, 1, 0)):
        return self.body(name, start, end, sections, style="Curved", up=up)

    def wing(self, name, span, root_chord, tip_chord, position=(0, 0, 0), rotation_quaternion=(0, 0, 0, 1), *, root_offset=0, tip_offset=0, airfoil=None):
        """Single unbent native wing: span is local +X; chord is local +/-Z.

        This writes a two-section wing, clears the rounded tip and uses the
        selected native template's airfoil unless explicitly supplied. Position
        is the native part origin. Chord offsets move section centres along
        local +Z and are distances, not sweep angles.
        """
        dimensions = [number(v*self.unit_scale, n, .001, 1000) for v, n in
                      [(number(span, "span"), "span metres"), (number(root_chord, "root_chord"), "root chord metres"), (number(tip_chord, "tip_chord"), "tip chord metres")]]
        span_m, root_m, tip_m = dimensions
        offsets = [number(number(v, "chord offset")*self.unit_scale, "chord offset metres", -1000, 1000) for v in (root_offset, tip_offset)]
        template = self.session._resolve_template("Wing")
        state = self._state(template, "JWing.State")
        slices = [] if state is None else [x for x in state.get("children", []) if x.get("element", x.get("name")) == "Slice"]
        if airfoil is None:
            airfoil = slices[0].get("attributes", {}).get("airfoil") if slices else None
        if not isinstance(airfoil, str) or not airfoil.strip() or len(airfoil) > 128:
            raise GeometryError("Wing template has no usable root airfoil; specify a discovered native airfoil")
        patch = {"flipped": False, "wingtip": None, "replaceSections": [
            {"spanPosition": 0., "chord": root_m, "offset": offsets[0], "airfoil": airfoil, "smoothJoin": False, "bendDegrees": 0.},
            {"spanPosition": span_m, "chord": tip_m, "offset": offsets[1], "airfoil": None, "smoothJoin": False, "bendDegrees": 0.}]}
        p, q = self._point(position), self.frame.orientation(rotation_quaternion)
        expected = {"family": "wing", "spanMetres": span_m, "rootChordMetres": root_m,
                    "tipChordMetres": tip_m, "airfoil": airfoil, "position": list(p),
                    "rotationQuaternion": list(q), "geometryStatus": "not_assessed"}
        return self._create(name, template, p, q, patch, expected)

    def wing_control(self, name, wing, span_range, chord_fraction=(.25, .25), *, style="StandardFlap",
                     max_deflection_deg=None, flap_deflection_deg=None, brake_top_deg=None, brake_bottom_deg=None):
        """Create and attach a native control surface to a wing surface receiver.

        Span is measured along the native wing from its root, in plan units.
        Chord fractions are dimensionless. Native overlap checks remain active.
        """
        self._name(name)
        wing_ref = self._ref(wing)
        if style not in ("StandardFlap", "FowlerFlap", "Slat", "BrakeFlap"):
            raise GeometryError("Unsupported native wing control style")
        span = [number(v*self.unit_scale, "control span metres", 0, 1000) for v in vector(span_range, "span_range", 2)]
        if span[1]-span[0] < .001:
            raise GeometryError("Control span must increase by at least 0.001 metre")
        chord = [number(v, "chord_fraction", .05, .4 if style == "Slat" else .8) for v in vector(chord_fraction, "chord_fraction", 2)]
        patch = {"spanRange": span, "chordFraction": chord}
        if max_deflection_deg is not None:
            if style == "BrakeFlap":
                raise GeometryError("BrakeFlap uses flap_deflection_deg/brake_top_deg/brake_bottom_deg")
            # ShapeCodec exposes the same public angle for flap and Slat;
            # the native adapter maps Slat to its deflectionDegrees XML field.
            patch["maxDeflectionDegrees"] = number(max_deflection_deg, "max_deflection_deg", 0, 90)
        brake = {"flapDeflectionDegrees": flap_deflection_deg, "brakeTopDegrees": brake_top_deg, "brakeBottomDegrees": brake_bottom_deg}
        if style != "BrakeFlap" and any(v is not None for v in brake.values()):
            raise GeometryError("Brake angle parameters apply only to BrakeFlap")
        patch.update({k: number(v, k, 0, 90) for k, v in brake.items() if v is not None})
        temporary = "model:"+name
        expected = {"family": "controlSurface", "style": style, "wing": wing_ref, "spanRangeMetres": span,
                    "chordFraction": chord, "geometryStatus": "not_assessed"}
        part = PlannedPart(name, temporary, expected, self._owner)
        self._append({"kind": "wing.control.add", "wingPartId": wing_ref, "style": style, "temporaryId": temporary, "patch": patch})
        self.objects[name] = part
        self._shapes[temporary] = {"family": "controlSurface", "configuration": deepcopy(patch)}
        return part

    def clip_plane(self, name, targets, origin, normal, bounds_min, bounds_max, *, max_cutters=16, padding_m=.002):
        """Plan a hard native plane cut on explicit targets and finite bounds.

        Removes the positive half-space; returns the exact bounded Hole plan.
        Lengths use plan units. Existing holes/materials/connections are retained.
        Native rebuild and MeshEvidence.planar_face checks remain mandatory.
        """
        from .hard_surfaces import append_plane_cut
        return append_plane_cut(self,name,targets,origin,normal,bounds_min,bounds_max,max_cutters=max_cutters,padding_m=padding_m)

    def hole(self, name, targets, width, height, depth, position=(0, 0, 0), rotation_quaternion=(0, 0, 0, 1)):
        """Create a bounded native Hole with an explicit fuselage target set.

        Size describes the native cutter envelope in its local XYZ axes, not
        the eventual visible aperture after intersection with the target body.
        """
        self._name(name)
        refs = self._refs(targets)
        dimensions = [number(number(v, n)*self.unit_scale, n+" metres", .01, 10)
                      for v, n in ((width, "width"), (height, "height"), (depth, "depth"))]
        p, q = self._point(position), self.frame.orientation(rotation_quaternion)
        template = self.session._resolve_template("Hole")
        temporary = "model:"+name
        expected = {"family": "hole", "sizeMetres": dimensions, "targetParts": refs,
                    "position": list(p), "rotationQuaternion": list(q), "geometryStatus": "not_assessed"}
        part = PlannedPart(name, temporary, expected, self._owner)
        self._append({"kind": "hole.create", "templateId": template["id"], "temporaryId": temporary,
                      "targetPartIds": refs, "position": list(p), "rotationQuaternion": list(q), "size": dimensions})
        self.objects[name] = part
        self._poses[temporary] = {"position": list(p), "rotationQuaternion": list(q)}
        return part

    def material(self, parts, material_id, *, slots=(0,), patch=None):
        """Assign a material, or clone it with a patch for these explicit slots.

        A patch appends a new palette material; it never edits the shared source.
        Native resource/value validation and append-only scope checks still apply.
        """
        resolve = getattr(self.session, "_resolve_material", None)
        if callable(resolve):
            material_id = resolve(material_id)
        elif not isinstance(material_id, (int, bool)):
            material_id = getattr(material_id, "id", None)
        if isinstance(material_id, bool) or not isinstance(material_id, int) or material_id < 0:
            raise GeometryError("material_id must be a discovered nonnegative native material ID")
        slots = list(slots)
        if not slots or any(isinstance(s, bool) or not isinstance(s, int) or s < 0 for s in slots) or len(set(slots)) != len(slots):
            raise GeometryError("slots must be distinct nonnegative integer indices")
        op = {"kind": "appearance.set", "mode": "assign" if patch is None else "clone", "materialId": material_id,
              "partIds": self._refs(parts), "slots": slots}
        if patch is not None:
            if not isinstance(patch, dict) or not patch:
                raise GeometryError("Material clone patch requires a nonempty typed dictionary")
            try:
                json.dumps(patch, allow_nan=False)
            except (ValueError, TypeError) as exc:
                raise GeometryError("Material patch requires finite JSON values") from exc
            op["patch"] = deepcopy(patch)
        self._append(op)
        return self

    def update_hole(self, part, *, size=None, targets=None, position=None, rotation_quaternion=None):
        """Update a native rectangular Hole with explicit bounded intent."""
        op = {"kind": "hole.update", "partId": self._ref(part)}
        if size is not None:
            op["size"] = [number(v*self.unit_scale, "hole size metres", .01, 10) for v in vector(size, "size")]
        if targets is not None:
            op["targetPartIds"] = self._refs(targets)
        if position is not None:
            op["position"] = list(self._point(position))
        if rotation_quaternion is not None:
            op["rotationQuaternion"] = list(self.frame.orientation(rotation_quaternion))
        if len(op) == 2:
            raise GeometryError("Supply a Hole size, targets or pose to update")
        self._append(op)
        if isinstance(part, PlannedPart):
            for source, target in (("size", "sizeMetres"), ("targetPartIds", "targetParts"), ("position", "position"), ("rotationQuaternion", "rotationQuaternion")):
                if source in op:
                    part.expected[target] = deepcopy(op[source])
        ref = op["partId"]
        if ref in self._poses:
            self._poses[ref].update({key: deepcopy(op[key]) for key in ("position", "rotationQuaternion") if key in op})
        return self

    def scale(self, parts, factors):
        """Set absolute native local XYZ object scale; positions do not change.

        This is distinct from native shape dimensions. Native derived/group
        effects are guarded by the same explicit scope and final readback.
        """
        factors = [number(v, "absolute object scale", .01, 100) for v in vector(factors, "factors")]
        refs = self._refs(parts)
        self._append(*[{"kind": "part.update", "partId": ref, "symmetric": False,
                        "changes": [{"path": "Part", "attribute": "scale", "value": factors}]} for ref in refs])
        for part in self._members(parts):
            if isinstance(part, PlannedPart):
                part.expected["objectScale"] = list(factors)
        return self

    def _shape_state(self, part):
        ref = self._ref(part)
        if ref not in self._shapes:
            if ref in self._shape_sources:
                self._shapes[ref]=deepcopy(self.session.shape(self._shape_sources[ref]))
                return deepcopy(self._shapes[ref])
            if isinstance(part, PlannedPart):
                raise GeometryError("Native shape dimensions are unavailable for this planned object")
            reader = getattr(self.session, "shape", None)
            if not callable(reader):
                raise GeometryError("Session cannot inspect the native shape for dimension editing")
            self._shapes[ref] = deepcopy(reader(part))
        return deepcopy(self._shapes[ref])

    def dimensions(self, part, *, width=None, height=None, length=None, span=None, root_chord=None, tip_chord=None):
        """Set native parameter dimensions, never infer them from a world AABB.

        Fuselage width/height scale existing section sizes proportionally to
        their maximum, retaining taper; Curved's control is not a measured
        surface section. Length is local Z separation. Wing span scales native
        span stations; chord values edit the endpoint sections explicitly.
        Object scale remains separate and may affect the resulting geometry.
        """
        if all(v is None for v in (width, height, length, span, root_chord, tip_chord)):
            raise GeometryError("Specify at least one native dimension")
        state = self._shape_state(part)
        family, config = state.get("family"), state.get("configuration", {})
        patch = {}
        if family == "fuselage":
            if any(v is not None for v in (span, root_chord, tip_chord)):
                raise GeometryError("Fuselage dimensions are width, height and local-Z length")
            sections = config.get("sections", [])
            if not sections:
                raise GeometryError("Native fuselage sections are unavailable")
            updates = {i: {"index": i} for i in range(len(sections))}
            for key, requested in (("width", width), ("height", height)):
                if requested is not None:
                    target = number(number(requested, key)*self.unit_scale, key+" metres", .001, 1000)
                    maximum = max(number(section[key], "native "+key, 0, 1000) for section in sections)
                    if maximum <= 0:
                        raise GeometryError("Cannot infer tapered dimension from zero native extent")
                    for i, section in enumerate(sections):
                        updates[i][key] = section[key]*target/maximum
            if any(len(update)>1 for update in updates.values()):
                patch["sections"] = list(updates.values())
            if length is not None:
                patch["length"] = number(number(length, "length")*self.unit_scale, "length metres", .001, 1000)
        elif family == "wing":
            if any(v is not None for v in (width, height, length)):
                raise GeometryError("Wing dimensions are span, root_chord and tip_chord")
            sections = config.get("sections", config.get("replaceSections", []))
            if len(sections) < 2:
                raise GeometryError("Native wing sections are unavailable")
            updates = {i: {"index": i} for i in range(len(sections))}
            if span is not None:
                target = number(number(span, "span")*self.unit_scale, "span metres", .001, 1000)
                maximum = number(sections[-1]["spanPosition"], "native span", .001, 1000)
                positions = [section["spanPosition"]*target/maximum for section in sections]
                if any(b-a < .001 for a, b in zip(positions, positions[1:])):
                    raise GeometryError("Scaled wing stations would be less than 0.001 metre apart")
                for i, position in enumerate(positions):
                    updates[i]["spanPosition"] = position
            for i, requested in ((0, root_chord), (len(sections)-1, tip_chord)):
                if requested is not None:
                    updates[i]["chord"] = number(number(requested, "chord")*self.unit_scale, "chord metres", .001, 1000)
            patch["sections"] = [update for update in updates.values() if len(update)>1]
        else:
            raise GeometryError("Native dimension editing currently supports fuselage and wing shapes")
        return self.shape(part, patch)

    def move(self, parts, translation, *, symmetric=False):
        refs = self._refs(parts)
        if not isinstance(symmetric, bool):
            raise GeometryError("symmetric must be boolean")
        self._append({"kind": "transform.apply", "partIds": refs, "mode": "delta", "frame": self.frame.to_dict(),
                      "translation": list(scale(vector(translation), self.unit_scale)), "symmetric": symmetric})
        self._transform_known_poses(refs, (0, 0, 0, 1), (0, 0, 0), self.frame.direction(scale(vector(translation), self.unit_scale)))
        return self

    def rotate(self, parts, axis, *, angle_deg=None, angle_rad=None, pivot=None, symmetric=False):
        refs = self._refs(parts)
        if not isinstance(symmetric, bool):
            raise GeometryError("symmetric must be boolean")
        op = {"kind": "transform.apply", "partIds": refs, "mode": "delta", "frame": self.frame.to_dict(),
              "rotationQuaternion": list(axis_angle(axis, angle_deg=angle_deg, angle_rad=angle_rad)), "symmetric": symmetric}
        if pivot is not None:
            op["pivot"] = list(scale(vector(pivot), self.unit_scale))
        self._append(op)
        frame_q = self.frame.rotation_quaternion
        q_world = multiply(multiply(frame_q, tuple(op["rotationQuaternion"])), (-frame_q[0], -frame_q[1], -frame_q[2], frame_q[3]))
        try:
            pivot_world = self.frame.point(op["pivot"]) if pivot is not None else self._known_pose(self._members(parts)[0])[0]
        except GeometryError:
            self._invalidate_poses(refs)
        else:
            self._transform_known_poses(refs, q_world, pivot_world, (0, 0, 0))
        return self

    def pose(self, parts, position, rotation_quaternion, *, symmetric=False):
        """Set the first object's absolute pose; remaining objects move rigidly."""
        if not isinstance(symmetric, bool):
            raise GeometryError("symmetric must be boolean")
        refs = self._refs(parts)
        target_position = self._point(position)
        target_q = self.frame.orientation(rotation_quaternion)
        self._append({"kind": "transform.apply", "partIds": refs, "mode": "absolute", "frame": self.frame.to_dict(),
                      "position": list(scale(vector(position), self.unit_scale)),
                      "rotationQuaternion": list(quaternion(rotation_quaternion)), "symmetric": symmetric})
        try:
            old_position, old_q = self._known_pose(self._members(parts)[0])
        except GeometryError:
            self._invalidate_poses(refs)
        else:
            q_world = multiply(target_q, (-old_q[0], -old_q[1], -old_q[2], old_q[3]))
            self._transform_known_poses(refs, q_world, old_position, sub(target_position, old_position))
        self._poses[refs[0]] = {"position": list(target_position), "rotationQuaternion": list(target_q)}
        return self

    def properties(self, part, patch, *, symmetric=False):
        return self._patch("properties.set", part, patch, symmetric)

    def mechanical(self,part,*,start=None,end=None,length=None,anchor='start',direction=None,radius_multiplier=None,boot_a=None,boot_b=None):
        """Edit native shaft endpoints in plan coordinates/units, not object scale.

        length is an absolute world endpoint spacing. Connected endpoints stay
        fixed unless their reviewed native hosts were explicitly moved first.
        radius_multiplier is the game's dimensionless Radius UI property.
        """
        from .geometry import unit
        ref=self._ref(part)
        if length is not None and (start is not None or end is not None):raise GeometryError('Use endpoint targets OR length/anchor/direction')
        if length is None and direction is not None:raise GeometryError('direction requires length')
        if anchor not in ('start','end','center'):raise GeometryError('anchor must be start, end or center')
        current=self._mechanical.get(ref)
        needs_current=length is not None or ((start is None)!=(end is None))
        if current is None and not isinstance(part,PlannedPart):
            current=deepcopy(self.session.mechanical(part));self._mechanical[ref]=current
        if needs_current and current is None:raise GeometryError('A planned shaft needs both explicit endpoints before length editing')
        op={'kind':'mechanical.update','partId':ref}
        if length is not None:
            distance=number(number(length,'length')*self.unit_scale,'endpoint spacing metres',.01,1000)
            a,b=(tuple(e['worldPosition']) for e in current['endpoints'])
            axis=unit(sub(b,a) if direction is None else self.frame.direction(direction),'shaft direction')
            if anchor=='start':b=add(a,scale(axis,distance))
            elif anchor=='end':a=sub(b,scale(axis,distance))
            else:
                center=scale(add(a,b),.5);a=sub(center,scale(axis,distance/2));b=add(center,scale(axis,distance/2))
            op.update(startWorld=list(a),endWorld=list(b))
        else:
            if start is not None:op['startWorld']=list(self._point(start))
            if end is not None:op['endWorld']=list(self._point(end))
        if radius_multiplier is not None:op['radiusMultiplier']=number(radius_multiplier,'native radius multiplier',.5,2)
        for key,value in (('bootA',boot_a),('bootB',boot_b)):
            if value is not None:
                if type(value) is not bool:raise GeometryError(key+' must be boolean')
                op[key]=value
        if len(op)==2:raise GeometryError('Provide endpoints, length, radius_multiplier or boots')
        if current is None:current={'endpoints':[{},{}]}
        else:current=deepcopy(current)
        for i,key in enumerate(('startWorld','endWorld')):
            if key in op:current['endpoints'][i]['worldPosition']=deepcopy(op[key])
        if all('worldPosition' in e for e in current['endpoints']):
            number(magnitude(sub(current['endpoints'][0]['worldPosition'],current['endpoints'][1]['worldPosition'])),'endpoint spacing metres',.01,1000)
        self._append(op);self._mechanical[ref]=current
        self._invalidate_poses([ref])  # Native beam recentres its part origin.
        return self

    def shape(self, part, patch, *, symmetric=False):
        """Advanced typed shape patch; native field units are metres/degrees/fractions."""
        return self._patch("shape.update", part, patch, symmetric)

    def replace_wing_sections(self,part,sections):
        from .wings import WingSection
        state=self._shape_state(part)
        if state.get('family')!='wing':raise GeometryError('Complete section replacement is supported for native wings; fixed fuselage roles use indexed patches')
        sections=list(sections)
        if not 2<=len(sections)<=32 or any(not isinstance(s,WingSection) for s in sections):raise GeometryError('Use 2..32 WingSection objects')
        patches=[s.to_patch(self.unit_scale) for s in sections]
        if patches[0]['spanPosition']!=0 or any(b['spanPosition']-a['spanPosition']<.001 for a,b in zip(patches,patches[1:])):raise GeometryError('Wing stations must start at zero and strictly increase')
        if patches[0]['airfoil'] is None or any('chord' not in s or 'offset' not in s for s in (patches[0],patches[-1])):raise GeometryError('Root/tip need chord and offset; root also needs an airfoil')
        return self.shape(part,{'replaceSections':patches})

    def clear_cutting(self,part,*,section_indices,edges=('top','right','bottom','left'),mode='automatic'):
        state=self._shape_state(part)
        if state.get('family')!='fuselage' or mode not in ('automatic','nominal_boundary'):raise GeometryError('Use native fuselage cutting with mode automatic or nominal_boundary')
        indices=list(section_indices)
        if not indices or len(set(indices))!=len(indices):raise GeometryError('Use explicit distinct native section indices')
        if isinstance(edges,str) or not edges or set(edges)-{'top','right','bottom','left'}:raise GeometryError('Use an explicit list of native section edge names')
        sections=state['configuration']['sections'];style=part.expected.get('nativeStyle') if isinstance(part,PlannedPart) else state.get('style')
        for i in indices:
            if type(i) is not int or not 0<=i<len(sections):raise GeometryError('Section index is outside the native part')
            if style=='Curved' and i==1:raise GeometryError('Curved control sections have no cutting capability')
        return self.shape(part,{'sections':[{'index':i,'cutting':{edge:None if mode=='automatic' else 0 for edge in edges}} for i in indices]})

    def _patch(self, kind, part, patch, symmetric):
        if not isinstance(patch, dict) or not patch or len(patch) > 100:
            raise GeometryError("patch must contain 1..100 discovered typed fields")
        if not isinstance(symmetric, bool):
            raise GeometryError("symmetric must be boolean")
        try:
            json.dumps(patch, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise GeometryError("Patch must contain finite JSON values") from exc
        ref = self._ref(part)
        updated_shape = None
        if kind == "shape.update" and ref in self._shapes:
            updated_shape = deepcopy(self._shapes[ref])
            config = updated_shape["configuration"]
            for key, value in patch.items():
                if key == "sections":
                    sections = config.get("sections", config.get("replaceSections", []))
                    if not isinstance(value, list) or not value:
                        raise GeometryError("Section patches require a nonempty indexed list")
                    for update in value:
                        if not isinstance(update, dict) or type(update.get("index")) is not int or not 0 <= update["index"] < len(sections):
                            raise GeometryError("Section patch index is outside the native shape")
                        sections[update["index"]].update(deepcopy(update))
                elif key == "replaceSections":
                    config.pop("sections", None)
                    config[key] = deepcopy(value)
                elif key == "length" and "offset" in config:
                    config["offset"][2] = number(value, "length metres", .001, 1000)*(-1 if config["offset"][2]<0 else 1)
                    config[key] = value
                else:
                    config[key] = deepcopy(value)
        self._append({"kind": kind, "partId": ref, "patch": patch, "symmetric": symmetric})
        if updated_shape is not None:
            self._shapes[ref] = updated_shape
        return self

    def connect(self, source, target, source_point=None, target_point=None, *, shape_policy="preserve", symmetric=False):
        a, b = self._ref(source), self._ref(target)
        if a == b:
            raise GeometryError("Cannot connect an object to itself")
        if shape_policy not in ("preserve", "native_resize"):
            raise GeometryError("shape_policy must be preserve or native_resize")
        if (source_point is None) != (target_point is None):
            raise GeometryError("Supply both attach point IDs or neither for native unambiguous selection")
        for value in (() if source_point is None else (source_point, target_point)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GeometryError("Attach point IDs must be nonnegative integers from native discovery")
        if not isinstance(symmetric, bool):
            raise GeometryError("symmetric must be boolean")
        operations = []
        if shape_policy == "preserve":
            for obj, ref in ((source, a), (target, b)):
                family = obj.expected.get("family") if isinstance(obj, PlannedPart) else self._existing_family(ref)
                if family == "fuselage":
                    operations.append({"kind": "shape.update", "partId": ref, "patch": {"autoResize": False}, "symmetric": symmetric})
                elif family is None:
                    raise GeometryError("Cannot certify preserve policy for an unknown part family; inspect/rebind the object")
        op = {"kind": "connection.auto" if source_point is None else "connection.connect", "partA": a, "partB": b, "symmetric": symmetric}
        if source_point is not None:
            op.update(attachPointA=source_point, attachPointB=target_point)
        operations.append(op)
        self._append(*operations)
        if shape_policy != "preserve":
            self._invalidate_poses([a, b])
        return self

    def _existing_family(self, ref):
        parts = self._baseline.get("parts", [])
        for part in parts:
            if part.get("id") == ref:
                native_type = part.get("partType", part.get("type", ""))
                return "fuselage" if native_type.startswith("JFuselage") else "wing" if native_type.startswith("JWing") else "other" if native_type else None
        return None

    def mirror_group(self, source, name, linked=True):
        """Mirror exact members using the reviewed native designer mirror plane.

        Returns a named group of new parts in source order. Internal native
        connections and dependencies are retained; external edges are detached.
        Include each host, dependent and cutter target explicitly. Sources must
        not already belong to native symmetry groups. Native modifier hooks and
        attachment mappings determine the result, so new poses/shapes require
        the receipt's measured native readback before further relative editing.
        """
        if not isinstance(linked, bool):
            raise GeometryError("linked must be a boolean")
        self._name(name)
        members = self._members(source)
        refs = self._refs(members)
        names = [name+"."+str(i+1) for i in range(len(members))]
        for child_name in names:
            self._name(child_name)
        mirrored = []
        for member, ref, child_name in zip(members, refs, names):
            original = member.expected if isinstance(member, PlannedPart) else next(
                (row for row in self._baseline.get("parts", []) if row["id"] == ref), {})
            expected = {key: deepcopy(original[key]) for key in ("family", "style", "type") if key in original}
            expected.update(mirroredFrom=ref, geometryStatus="not_assessed")
            mirrored.append(PlannedPart(child_name, "model:"+child_name, expected, self._owner))
        with self._atomic_edit():
            self._append({"kind": "part.mirror", "partIds": refs,
                          "temporaryIds": [part.temporary_id for part in mirrored], "linked": linked})
            for part in mirrored:
                self.objects[part.name] = part
            return self.group(name, mirrored)

    def mirror(self, part, *, linked=True, plane="native"):
        """Create a native mirror using the previewed craft mirror plane.

        Explicit arbitrary planes are unsupported by this native operation.
        Session preview/execution must require native mode 'Mirrored'; radial
        and disabled modes do not satisfy this operation. linked=False
        unlinks the resulting whole symmetry group after creating its peers.
        """
        if plane != "native" or not isinstance(linked, bool):
            raise GeometryError("Use plane='native' and boolean linked; arbitrary-plane mirroring is unsupported")
        ref = self._ref(part)
        ops = [{"kind": "symmetry.create", "partId": ref}]
        if not linked:
            ops.append({"kind": "symmetry.unlink", "partId": ref})
        self._append(*ops)
        return self

    def align(self, parts, source, source_point, target, target_point, *, offset=(0, 0, 0), axis="opposedNormals", symmetric=False):
        """Align native attach points; does not connect or impose an extra roll."""
        refs, a, b = self._refs(parts), self._ref(source), self._ref(target)
        if a not in refs or b in refs:
            raise GeometryError("Source must move with the group and target must be outside it")
        if axis not in ("opposedNormals", "jointAxes") or not isinstance(symmetric, bool):
            raise GeometryError("Unsupported alignment axis or symmetric flag")
        if (source_point is None) != (target_point is None):
            raise GeometryError("Supply both attach point IDs or neither for native unambiguous selection")
        for point in (() if source_point is None else (source_point, target_point)):
            if isinstance(point, bool) or not isinstance(point, int) or point < 0:
                raise GeometryError("Attachment IDs must be nonnegative native IDs")
        op = {"kind": "transform.align", "partIds": refs, "sourcePartId": a,
              "targetPartId": b, "offset": list(scale(vector(offset), self.unit_scale)), "axis": axis, "symmetric": symmetric}
        if source_point is not None:
            op.update(sourcePointId=source_point, targetPointId=target_point)
        self._append(op)
        self._invalidate_poses(refs)
        return self

    def align_to(self, parts, source, target, *, source_point=None, target_point=None, offset=(0, 0, 0), axis="opposedNormals", symmetric=False):
        return self.align(parts, source, source_point, target, target_point, offset=offset, axis=axis, symmetric=symmetric)

    def delete(self, part, *, assembly=False, symmetric=False):
        if not isinstance(assembly, bool) or not isinstance(symmetric, bool):
            raise GeometryError("assembly and symmetric must be booleans")
        ref = self._ref(part)
        self._append({"kind": "part.delete", "partId": ref, "assembly": assembly, "symmetric": symmetric})
        self._deleted.add(ref)
        return self

    def expect(self, part, *, length_m=None, span_m=None, position_m=None, dimensions_m=None,
               rotation_quaternion=None, tolerance_m=.01, tolerance_deg=.01, sections=None, connected_to=None, endpoints_m=None):
        ref = self._ref(part, writable=False)
        tolerance = number(tolerance_m, "tolerance_m", 0)
        if all(v is None for v in (length_m, span_m, position_m, dimensions_m, rotation_quaternion, sections, connected_to, endpoints_m)):
            raise GeometryError("Supply at least one explicit target")
        result = {"part": ref, "toleranceMetres": tolerance}
        if endpoints_m is not None:
            try:values=list(endpoints_m)
            except TypeError:raise GeometryError("endpoints_m requires two world-metre points") from None
            if len(values)!=2:
                raise GeometryError("endpoints_m requires start and end world-metre points")
            result["endpointsWorldMetres"]=[list(vector(value,"endpoint world metres")) for value in values]
        if length_m is not None:
            result["lengthMetres"] = number(length_m, "length_m", .001, 1000)
        if span_m is not None:
            result["spanMetres"] = number(span_m, "span_m", .001, 1000)
        if position_m is not None:
            result["positionWorldMetres"] = list(vector(position_m, "position_m"))
        if dimensions_m is not None:
            result["dimensionsMetres"] = [number(v, "dimension metres", 0, 100000) for v in vector(dimensions_m, "dimensions_m")]
        if rotation_quaternion is not None:
            result["rotationQuaternion"] = list(quaternion(rotation_quaternion))
            result["toleranceDegrees"] = number(tolerance_deg, "tolerance_deg", 0, 180)
        if sections is not None:
            sections = list(sections)
            if not sections:
                raise GeometryError("sections must contain at least one explicit section target")
            result["sections"] = []
            for section in sections:
                if not isinstance(section, dict) or set(section)-{"axis", "offset_m", "width_m", "height_m", "tolerance_m"}:
                    raise GeometryError("Section target has unknown fields")
                if not {"axis", "offset_m", "width_m", "height_m"}.issubset(section):
                    raise GeometryError("Section target requires axis, offset_m, width_m and height_m")
                if section["axis"] not in ("x", "y", "z"):
                    raise GeometryError("Section axis must be x, y or z in the actual part frame")
                result["sections"].append({"axis": section["axis"], "offsetMetres": number(section["offset_m"], "offset_m"),
                    "widthMetres": number(section["width_m"], "width_m", 0), "heightMetres": number(section["height_m"], "height_m", 0),
                    "toleranceMetres": number(section.get("tolerance_m", tolerance), "section tolerance_m", 0)})
        if connected_to is not None:
            targets = [self._ref(target, writable=False) for target in self._members(connected_to)]
            if not targets or ref in targets or len(set(targets)) != len(targets):
                raise GeometryError("Connection targets must be distinct other parts")
            result["connectedTo"] = targets
        self.expectations.append(result)
        return self

    def expect_section(self, part, axis, offset_m, width_m, height_m, *, tolerance_m=.002):
        return self.expect(part, sections=[{"axis": axis, "offset_m": offset_m, "width_m": width_m,
                                           "height_m": height_m, "tolerance_m": tolerance_m}])

    def edit_attribute(self, attribute, value=None, *, action="set", new_name=None):
        """Apply a discovered native field; None/empty follows native omission."""
        from .native_state import StateAttribute
        if not isinstance(attribute, StateAttribute):
            raise GeometryError("Use a field discovered by session.state(part).node(...).attribute(...)")
        if attribute.read_only or attribute.structural_operation:
            raise GeometryError("This native field is read-only or requires a structural operation")
        if action not in ("set", "remove", "rename"):
            raise GeometryError("Native attribute action must be set, remove or rename")
        if action == "rename" and (not isinstance(new_name, str) or not new_name):
            raise GeometryError("Attribute rename requires new_name")
        ref = self._ref(attribute.part)
        change = {"action":action, "path":attribute.path, "attribute":attribute.name}
        if action == "set": change["value"] = deepcopy(value)
        if action == "rename": change["newName"] = new_name
        if self.operations and self.operations[-1]["kind"] == "native.state" and self.operations[-1]["partId"] == ref:
            self.operations[-1]["changes"].append(change)
        else:
            self._append({"kind":"native.state", "partId":ref, "changes":[change]})
        return self

    def input(self, controller, **patch):
        from .objects import ControllerRef
        if not isinstance(controller,ControllerRef):raise GeometryError("Select a controller with session.inputs(part)")
        ref=self._ref(controller.part)
        allowed={"input","activation_group","invert","min","max","zero_on_deactivate","invert_type","invert_on_mirror"}
        if not patch or set(patch)-allowed:raise GeometryError("Unknown or empty input-controller patch")
        for key,value in patch.items():
            if key in ("invert","zero_on_deactivate","invert_on_mirror") and type(value) is not bool:raise GeometryError(key+" must be boolean")
            if key in ("min","max"):number(value,key)
            if key=="input" and (not isinstance(value,str) or not value.strip()):raise GeometryError("input must be native expression or axis text")
            if key=="invert_type" and value not in ("Axis","Output"):raise GeometryError("invert_type must be Axis or Output")
            if key=="activation_group":
                if type(value) is int:
                    if value<0 or value>8:raise GeometryError("activation_group index must be 0..8")
                    patch[key]=str(value)
                elif not isinstance(value,str) or not value.strip():raise GeometryError("activation_group must be an index or native boolean expression")
        names={"activation_group":"activationGroup","zero_on_deactivate":"zeroOnDeactivate","invert_type":"invertType","invert_on_mirror":"invertOnMirror"}
        changes=[{"action":"set","path":f"InputController.State[{controller.index}]","attribute":names.get(k,k),"value":deepcopy(v)} for k,v in patch.items()]
        self._append({"kind":"native.state","partId":ref,"changes":changes})
        return self

    def output(self, output, *, action="bind", variable=None, priority=None, activator=None):
        from .objects import OutputRef
        if not isinstance(output,OutputRef) or action not in ("bind","update","unbind"):
            raise GeometryError("Select a native output definition and bind/update/unbind action")
        op={"kind":"output."+action,"partId":self._ref(output.part),"modifier":output.modifier,"modifierIndex":output.modifier_index,"outputId":output.output_id}
        for key,value in (("variable",variable),("priority",priority),("activator",activator)):
            if value is not None:op[key]=value
        if priority is not None and type(priority) is not int:raise GeometryError("Output priority must be an integer")
        self._append(op);return self

    def _setter_index(self, setter):
        from .objects import SetterRef
        if isinstance(setter,PlannedSetter):
            if setter._owner!=self._owner:raise GeometryError("Setter belongs to another plan")
            key=setter.key
        elif isinstance(setter,SetterRef):
            if setter._instance!=self.session.client.instance["instanceId"] or setter._identity!=self.frozen_baseline_identity:
                raise GeometryError("Setter handle is stale or from another instance")
            key=setter.index
        else:raise GeometryError("Use a SetterRef from session.variables or this plan's new Setter")
        if key not in self._setter_keys:raise GeometryError("Setter was already deleted in this plan")
        return self._setter_keys.index(key)

    def _variable_scope(self, *names):
        if any(name not in self.variable_names for name in names):raise GeometryError("Declare every reviewed Setter name in session.plan(variables=[...])")

    def add_variable(self, variable, function, *, priority=0, activator=None):
        self._current();self._variable_scope(variable)
        if not isinstance(function,str) or type(priority) is not int:raise GeometryError("Setter function must be native expression text and priority an integer")
        op={"kind":"variable.add","variable":variable,"function":function,"priority":priority}
        if activator is not None:op["activator"]=activator
        self._append(op);setter=PlannedSetter(variable,uuid.uuid4().hex,self._owner)
        self._setter_keys.append(setter.key);self._setter_names.append(variable);return setter

    def update_variable(self, setter, *, variable=None, function=None, priority=None, activator=None):
        self._current();index=self._setter_index(setter)
        self._variable_scope(self._setter_names[index],self._setter_names[index] if variable is None else variable)
        patch={k:v for k,v in (("variable",variable),("function",function),("priority",priority),("activator",activator)) if v is not None}
        if not patch or priority is not None and type(priority) is not int:raise GeometryError("Use a nonempty Setter patch and integer priority")
        self._append({"kind":"variable.update","index":index,**patch})
        if variable is not None:self._setter_names[index]=variable
        return self

    def delete_variable(self, setter):
        self._current();index=self._setter_index(setter);self._variable_scope(self._setter_names[index])
        self._append({"kind":"variable.delete","index":index});self._setter_keys.pop(index);self._setter_names.pop(index);return self

    def rename_variable(self,setter,new_name,*,references):
        """Rename one Setter and only the explicitly approved native references.

        Use a fresh plan and inspect session.logic_dependencies(variable=...).
        Output declarations are independent providers; this does not rename them
        or arbitrary mod-specific expression strings automatically.
        """
        from .logic import rename_identifier
        if self.operations:raise GeometryError('Reviewed variable migration needs a fresh dedicated plan')
        index=self._setter_index(setter);old=self._setter_names[index]
        graph=self.session.logic_dependencies(variable=old);approved=list(references)
        if any(row not in graph['references'] for row in approved):raise GeometryError('Migration references must be exact currently discovered native graph rows')
        if graph['parseFailures']:raise GeometryError('Some expression references could not be parsed; review those failures before migration')
        setters={s.index:s for s in self.session.variables()}
        with self._atomic_edit():
            self.update_variable(setter,variable=new_name)
            for row in approved:
                replacement=rename_identifier(row['expression'],old,new_name)
                if row['kind']=='setter':self.update_variable(setters[row['setterIndex']],**{row['field']:replacement})
                else:
                    part=self.session.inspect().part(id=row['partId']);state=self.session.state(part)
                    node=next((n for n in state.nodes() if n.path==row['path']),None)
                    if node is None or node.attribute(row['field']).value!=row['expression']:raise GeometryError('Reference path or source expression changed; inspect and review again')
                    self.edit_attribute(node.attribute(row['field']),replacement)
        return self

    def reorder_variables(self, setters):
        self._current();order=[self._setter_index(s) for s in setters]
        if sorted(order)!=list(range(len(self._setter_keys))):raise GeometryError("List every current Setter exactly once")
        self._variable_scope(*self._setter_names)
        self._append({"kind":"variable.reorder","order":order})
        self._setter_keys=[self._setter_keys[i] for i in order];self._setter_names=[self._setter_names[i] for i in order];return self

    def expect_connected(self, source, target):
        return self.expect(source, connected_to=target)

    def expect_probe(self, part, point_world_m, *, inside):
        """Request a solid-point test; native evidence must establish suitability."""
        if not isinstance(inside, bool):
            raise GeometryError("inside must be a boolean")
        self.expectations.append({"part": self._ref(part, writable=False),
            "probes": [{"pointWorldMetres": list(vector(point_world_m, "point_world_m")), "inside": inside}]})
        return self

    def to_dict(self):
        return deepcopy({"schemaVersion": "sp2model.plan/1", "baselineIdentity": self.frozen_baseline_identity,
                         "frame": self.frame.to_dict(), "lengthUnit": self.length_unit,
                         "writablePartIds": None if self.writable_part_ids is None else sorted(self.writable_part_ids),
                         "variableNames": sorted(self.variable_names),
                         "semanticShapes": self.semantic_shapes,
                         "operations": self.operations, "objects": {k: v.to_dict() for k, v in self.objects.items()},
                         "groups": {name: {"name": name, "partIds": [ref for ref in group._references if ref not in self._deleted]} for name, group in self.groups.items()},
                         "expectations": self.expectations})

    def preview(self):
        return self.session._preview(self)

    def apply(self, preview_token):
        return self.session._apply(self, preview_token)
