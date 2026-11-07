"""Shape intents compiled into existing native Plan operations, without writes.

Stations are measured end sections, never Curved control sections. Parallel
planes with independently drifting centres use native three-axis offset while
retaining the declared section normal. Mesh comparison remains mandatory.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .errors import ModelingError
from .geometry import (Section, CORNERS, EDGES, number, vector, unit, dot, sub,
                       add, scale, look_rotation, rotate, magnitude,
                       rotation_distance_degrees)
from ._services.reference_storage import digest


def _fail(code, message, **details):
    raise ModelingError(code, message, details)


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        _fail("invalid_geometry", "Logical name must contain 1..100 nonblank characters")
    return value


def _profile(station):
    """Return validated native section plus explicit corner sampling intent."""
    profile = deepcopy(station.get("profile", {}))
    for key in ("width", "height"):
        if key in station:
            if key in profile and profile[key] != station[key]:
                _fail("ambiguous_profile", f"Conflicting station/profile {key}")
            profile[key] = station[key]
    allowed = {"width", "height", "corner", "corner_radius", "corner_stretch", "trapezium",
               "edge_curvature", "cutting", "smoothing", "sync_adjacent", "thickness_fraction"}
    unknown = sorted(set(profile) - allowed)
    if unknown:
        _fail("unsupported_profile", "Unsupported profile keys must not be silently ignored", fields=unknown,
              nextAction="Use a rectangle/trapezium/chamfer/rounded profile or explicit native shape patch")
    if "width" not in profile or "height" not in profile:
        _fail("invalid_geometry", "Every station needs its own width and height; no global maximum fallback")
    corner = profile.pop("corner", {"kind": "sharp"})
    if not isinstance(corner, dict) or corner.get("kind") not in ("sharp", "chamfer", "round"):
        _fail("invalid_geometry", "profile.corner.kind must be sharp, chamfer or round")
    if set(corner) - {"kind", "distance", "samples"}:
        _fail("invalid_geometry", "Unknown corner fields", fields=sorted(set(corner) - {"kind", "distance", "samples"}))
    kind = corner["kind"]
    if "corner" in station.get("profile", {}) and ("corner_radius" in profile or "corner_stretch" in profile):
        _fail("ambiguous_profile", "Use semantic corner or advanced corner_radius/corner_stretch, not both")
    if kind != "sharp":
        distance = number(corner.get("distance"), "corner.distance metres", 0, 1000)
        if distance <= 0:
            _fail("invalid_geometry", "Chamfer/round distance must be positive")
        profile.update(corner_radius=distance, corner_stretch=False)
    elif "distance" in corner and corner["distance"] != 0:
        _fail("invalid_geometry", "Sharp corners do not have a nonzero distance")
    samples = corner.get("samples", 8 if kind == "round" else 2)
    if type(samples) is not int or not 2 <= samples <= 32 or (kind == "chamfer" and samples != 2):
        _fail("invalid_geometry", "Chamfer uses exactly two endpoints; round uses 2..32 samples")
    if kind == "round" and samples < 3:
        _fail("invalid_geometry", "Round corners require at least three samples; use chamfer for a straight edge")
    section = Section(**profile)
    if section.width <= 0 or section.height <= 0:
        _fail("unsupported_profile", "Loft end sections require positive width and height; use native Cone for a zero tip")
    patch = section.to_patch(0)
    patch["cornerSamples"] = dict.fromkeys(CORNERS, samples)
    patch["edgeSamples"] = dict.fromkeys(EDGES, 8)
    return section, patch, {"cornerKind": kind, "cornerSamples": samples,
                           "interpretation": "hard planar native cuts; requires native geometry and shading validation" if kind == "chamfer" else "native sampled profile; shading not certified"}


def _station(value, index, normal):
    if not isinstance(value, dict):
        _fail("invalid_geometry", "Each station must be an object")
    if set(value) - {"id", "center", "normal", "width", "height", "profile", "featureId", "referenceRegion"}:
        _fail("invalid_geometry", "Unknown station fields", fields=sorted(set(value) - {"id", "center", "normal", "width", "height", "profile", "featureId", "referenceRegion"}))
    station_id = _name(value.get("id", f"station-{index}"))
    center = vector(value.get("center"), "station.center metres")
    axis = unit(value.get("normal", normal), "station.normal")
    if dot(axis, normal) < 1 - 1e-8:
        _fail("unsupported_representation", "Changing section normals cannot be represented by this parallel Body loft",
              stationId=station_id, requestedNormal=list(axis), commonNormal=list(normal),
              expectedError={"status": "unknown", "reason": "No native interpolation fit has been measured"},
              alternatives=["Split at the normal change and define each parallel segment explicitly",
                            "Use a reviewed native Curved fit; its middle section is a control, not an interpolation station"])
    section, patch, semantics = _profile(value)
    return {"id": station_id, "center": list(center), "normal": list(axis), "profile": patch,
            "featureId": value.get("featureId", station_id), "referenceRegion": deepcopy(value.get("referenceRegion")),
            "semantics": semantics}, section


def _semantic_binding(plan, document, parts):
    """Existing Project.after_execution contract, separate from hashed intent."""
    references = [plan._ref(part) for part in parts]
    return {"kind": document["kind"], "compilation": deepcopy(document),
            "parts": references, "actualParts": len(references),
            "poses": {str(ref): deepcopy(plan._poses[ref]) for ref in references},
            "configurations": {str(ref): deepcopy(plan._shapes[ref]["configuration"]) for ref in references if ref in plan._shapes}}


@dataclass(frozen=True)
class GeometryCompilation:
    """Deterministic immutable-by-copy intent. append_to builds a plan only."""
    _document: dict

    def to_dict(self):
        return deepcopy(self._document)

    def append_to(self, plan):
        """Append the exact preview to a Plan, preserving its frame/scope guards.

        Inputs are metres in plan.frame. A non-metre Plan is supported by
        conversion at its public body/pose boundary; shape offsets stay metres.
        No Session.apply, network mutation or native write occurs here.
        """
        document = self.to_dict()
        needed = document["operationCount"]
        if len(plan.operations) + needed > 100:
            _fail("operation_budget_exceeded", "Compiled shape exceeds the remaining native plan budget",
                  required=needed, remaining=100 - len(plan.operations))
        names = [piece["name"] for piece in document["pieces"]]
        if any(name in plan.objects or name in plan.groups for name in names) or document["name"] in plan.groups:
            _fail("duplicate_geometry_name", "Compiled names already exist in this plan")
        with plan._atomic_edit():
            parts = []
            by_feature = {}
            for piece in document["pieces"]:
                q = piece["rotationQuaternion"]
                inverse = (-q[0], -q[1], -q[2], q[3])
                a, b = piece["centers"]
                middle = scale(add(a, b), .5)
                normal = piece["normal"]
                separation = dot(sub(b, a), normal)
                nominal_start = sub(middle, scale(normal, separation / 2))
                nominal_end = add(middle, scale(normal, separation / 2))
                profiles = piece["profiles"]
                sections = [Section(p["width"] / plan.unit_scale, p["height"] / plan.unit_scale) for p in profiles]
                part = plan.body(piece["name"], scale(nominal_start, 1 / plan.unit_scale),
                                 scale(nominal_end, 1 / plan.unit_scale), sections,
                                 up=piece["up"])
                # body established the intended orientation; offset supplies the
                # centre drift in that orientation, without tilting the planes.
                local_delta = rotate(inverse, sub(b, a))
                patch = {"offset": list(local_delta), "sections": deepcopy(profiles)}
                plan.shape(part, patch)
                part.expected.update(startWorld=list(plan.frame.point(a)), endWorld=list(plan.frame.point(b)),
                                     sectionNormalWorld=list(plan.frame.direction(normal)),
                                     sourceCompilation=document["compilationHash"],
                                     geometryStatus="not_assessed")
                parts.append(part)
                for i,cut in enumerate(piece.get('hardCuts',[])):
                    cutter=plan.hole(f"{piece['name']}/hard-cut-{i}",[part],*[v/plan.unit_scale for v in cut['sizeMetres']],position=scale(cut['position'],1/plan.unit_scale),rotation_quaternion=cut['rotationQuaternion'])
                    cutter.expected['hardFaceIntent']=deepcopy(cut['intent'])
                    parts.append(cutter)
                for feature in piece["featureIds"]:
                    by_feature.setdefault(feature, []).append(part)
            group = plan.group(document["name"], parts)
            plan.semantic_shapes[document["name"]] = _semantic_binding(plan, document, parts)
        return {"group": group, "parts": parts, "features": by_feature,
                "compilationHash": document["compilationHash"], "geometryStatus": "not_assessed"}

    def patch_existing(self, plan, parts_by_name, previous_compilation, *, tolerance_m=1e-4, tolerance_deg=.001):
        """Append scoped differential patches for the same native piece topology.

        Bindings are an exact piece-name mapping or ordered list. Every previous
        owned parameter and pose must still match the inspected native baseline.
        Unmentioned native fields are neither reset nor copied from a template.
        No deletion, replacement, connection edit, implicit rebasing or apply is
        performed. Topology changes require a separately reviewed replacement.
        """
        document = self.to_dict()
        previous = (previous_compilation.to_dict() if isinstance(previous_compilation, GeometryCompilation)
                    else deepcopy(previous_compilation))
        if any(p.get('hardCuts') for p in document['pieces']) or any(p.get('hardCuts') for p in previous.get('pieces',[])):
            _fail('hard_face_refine_requires_replacement','Hard-cut loft topology must be explicitly replaced as a complete reviewed component; direct native targets remain available')
        tolerance = number(tolerance_m, "tolerance_m", 0, .01)
        angle_tolerance = number(tolerance_deg, "tolerance_deg", 0, .1)
        for value in (previous, document):
            if not isinstance(value, dict) or value.get("compilationHash") != digest({k: v for k, v in value.items() if k != "compilationHash"}):
                _fail("compilation_integrity_error", "Use an unchanged, hashed compilation preview")
        old_pieces, new_pieces = previous["pieces"], document["pieces"]
        old_names, names = [p["name"] for p in old_pieces], [p["name"] for p in new_pieces]
        if (previous["name"] != document["name"] or previous["kind"] != document["kind"] or old_names != names or
                any(a["stationIds"] != b["stationIds"] for a, b in zip(old_pieces, new_pieces))):
            _fail("topology_change_requires_replacement", "In-place refinement requires identical named pieces and station roles",
                  previousPieceNames=old_names, requestedPieceNames=names,
                  nextAction="Review an explicit create/delete replacement plan; this helper never replaces topology")
        if isinstance(parts_by_name, dict):
            if set(parts_by_name) != set(names):
                _fail("invalid_geometry_binding", "Bind exactly every compiled piece by name", expected=names, actual=list(parts_by_name))
            parts = [parts_by_name[name] for name in names]
        elif isinstance(parts_by_name, (list, tuple)) and len(parts_by_name) == len(names):
            parts = list(parts_by_name)
        else:
            _fail("invalid_geometry_binding", "Use an exact name mapping or ordered list of all compiled native pieces")
        refs = [plan._ref(part) for part in parts]
        if len(set(refs)) != len(refs):
            _fail("invalid_geometry_binding", "Two compiled pieces cannot bind to the same native part")

        def equivalent(expected, actual):
            if isinstance(expected, bool) or expected is None or isinstance(expected, str):
                return type(actual) is type(expected) and actual == expected
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and not isinstance(actual, bool):
                return abs(expected - actual) <= max(tolerance, abs(expected) * 1e-6)
            if isinstance(expected, dict) and isinstance(actual, dict):
                return all(key in actual and equivalent(value, actual[key]) for key, value in expected.items())
            if isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
                return len(expected) == len(actual) and all(equivalent(a, b) for a, b in zip(expected, actual))
            return False

        def piece_offset(piece):
            q = piece["rotationQuaternion"]
            return list(rotate((-q[0], -q[1], -q[2], q[3]), sub(piece["centers"][1], piece["centers"][0])))

        edits = []
        with plan._atomic_edit():
            for old, new, part, ref in zip(old_pieces, new_pieces, parts, refs):
                state = plan._shape_state(part)
                config = state.get("configuration", {})
                if state.get("family") != "fuselage" or len(config.get("sections", [])) != 2:
                    _fail("geometry_binding_mismatch", "Refinement target must still be the two-section native Body", pieceName=old["name"], partId=ref)
                owned = {"offset": piece_offset(old), "sections": old["profiles"]}
                if not equivalent(owned, config):
                    _fail("geometry_baseline_changed", "Current native shape differs from the previous compiled geometry",
                          pieceName=old["name"], partId=ref,
                          nextAction="Inspect the external/native difference and explicitly revise the baseline; no parameters were overwritten")
                position, rotation = plan._known_pose(part)
                old_center = scale(add(*old["centers"]), .5)
                expected_position = plan.frame.point(old_center)
                expected_rotation = plan.frame.orientation(old["rotationQuaternion"])
                if magnitude(sub(position, expected_position)) > tolerance or rotation_distance_degrees(rotation, expected_rotation) > angle_tolerance:
                    _fail("geometry_pose_changed", "Current native pose no longer matches the frozen compilation frame",
                          pieceName=old["name"], partId=ref, expectedPosition=list(expected_position), actualPosition=list(position),
                          nextAction="Review save recentering or external edits; do not fit pieces independently")
                patch = {}
                old_offset, new_offset = piece_offset(old), piece_offset(new)
                if old_offset != new_offset:
                    patch["offset"] = new_offset
                section_updates = []
                for index, (old_profile, new_profile) in enumerate(zip(old["profiles"], new["profiles"])):
                    changed = {key: deepcopy(value) for key, value in new_profile.items()
                               if key != "index" and value != old_profile.get(key)}
                    if changed:
                        section_updates.append({"index": index, **changed})
                if section_updates:
                    patch["sections"] = section_updates
                new_center = scale(add(*new["centers"]), .5)
                pose_changed = new_center != old_center or new["rotationQuaternion"] != old["rotationQuaternion"]
                edits.append((part, old["name"], patch, new_center, new["rotationQuaternion"], pose_changed))
            operation_count = sum(bool(patch) + pose for _, _, patch, _, _, pose in edits)
            if len(plan.operations) + operation_count > 100:
                _fail("operation_budget_exceeded", "Refinement exceeds remaining operation budget", required=operation_count, remaining=100-len(plan.operations))
            for part, _, patch, center, q, pose_changed in edits:
                if patch:
                    plan.shape(part, patch)
                if pose_changed:
                    plan.pose(part, scale(center, 1 / plan.unit_scale), q)
            existing_group = plan.groups.get(document["name"])
            if existing_group is not None and tuple(existing_group._references) != tuple(refs):
                _fail("invalid_geometry_binding", "Existing plan group does not match the refinement bindings")
            group = existing_group or plan.group(document["name"], parts)
            plan.semantic_shapes[document["name"]] = _semantic_binding(plan, document, parts)
        feature_bindings = {}
        for piece, part in zip(new_pieces, parts):
            for feature in piece["featureIds"]:
                feature_bindings.setdefault(feature, []).append(part)
        return {"group": group, "parts": parts, "features": feature_bindings,
                "changedPieceNames": [name for _, name, patch, _, _, moved in edits if patch or moved],
                "unchangedPieceNames": [name for _, name, patch, _, _, moved in edits if not patch and not moved],
                "operationCount": operation_count, "compilationHash": document["compilationHash"],
                "previousCompilationHash": previous["compilationHash"], "geometryStatus": "not_assessed",
                "semantics": "equal-topology differential shape/pose patches; preserved connections and all unmentioned fields"}


def _finish(name, kind, pieces, stations, features, max_parts, reference, limitations):
    if type(max_parts) is not int or not 1 <= max_parts <= 20:
        _fail("invalid_geometry", "max_parts must be 1..20")
    native_count=len(pieces)+sum(len(p.get('hardCuts',[])) for p in pieces)
    if native_count > max_parts:
        _fail("piece_budget_exceeded", "Budget cannot discard required stations or negative features",
              requiredPieces=native_count, budget=max_parts, featureIds=list(features),
              nextAction="Increase the explicit budget or revise the shape contract; no write has occurred")
    if reference is not None:
        if not isinstance(reference, dict) or reference.get("status") != "ready" or not all(reference.get(k) for k in ("referenceId", "version", "contentHash", "frameId")):
            _fail("reference_not_ready", "A dependent shape requires a verified ready reference record")
        reference = {k: deepcopy(reference[k]) for k in ("referenceId", "version", "contentHash", "frameId")}
    document = {"kind": kind, "name": name, "units": "m", "geometryFrame": "plan_frame_metres",
                "pieceCount": len(pieces), "nativePartCount":native_count,"operationCount": 5 * len(pieces)+native_count-len(pieces), "pieces": pieces,
                "stations": stations, "features": features, "reference": reference,
                "nativeRepresentation": "Body segments with fixed parallel section planes and local 3D offset",
                "interpolation": "piecewise linear native end sections; no Curved control station substitution",
                "estimatedError": {"status": "not_measured", "idealEndpointErrorMetres": 0,
                                   "coverage": "Algebraic endpoint mapping only; native tessellation, cuts, corner clamps and exterior require measurement"},
                "limitations": limitations, "nativeMeshStatus": "not_assessed", "shadingStatus":"not_assessed"}
    document["compilationHash"] = digest(document)
    return GeometryCompilation(deepcopy(document))


def _compile_hard_corners(piece,a,b):
    from .hard_surfaces import plane_cut
    kinds=[row['semantics']['cornerKind'] for row in (a,b)]
    if 'chamfer' not in kinds:return
    profiles=piece['profiles'];distances=[]
    for kind,p in zip(kinds,profiles):
        if kind not in ('chamfer','sharp') or p['trapezium']!=0 or any(p['edgeCurvature'].values()) or p.get('hollow') or any(v is not None for v in p.get('cutting',{}).values()):
            _fail('unsupported_hard_chamfer','Hard chamfer currently supports solid rectangular parallel sections; use explicit clip_plane for other bounded native solids')
        radius=list(p['cornerRadius'].values())
        if kind=='sharp' and any(radius):_fail('unsupported_hard_chamfer','Do not mix advanced raw rounded profiles with hard chamfer')
        distance=radius[0] if kind=='chamfer' else 0.
        if distance>min(p['width'],p['height'])/2:_fail('unsupported_hard_chamfer','Hard chamfer distance exceeds the nonoverlapping rectangular-corner domain')
        distances.append(distance)
        p['cornerRadius']=dict.fromkeys(CORNERS,0.)
        p['cornerStretch']=dict.fromkeys(CORNERS,False)
    q=piece['rotationQuaternion'];right=rotate(q,(1,0,0));up=rotate(q,(0,1,0));axis=piece['normal'];centers=piece['centers']
    delta=sub(centers[1],centers[0]);dz=dot(delta,axis)
    corners=[add(c,add(scale(right,sx*p['width']/2),scale(up,sy*p['height']/2))) for c,p in zip(centers,profiles) for sx in (-1,1) for sy in (-1,1)]
    lo=[min(p[i] for p in corners) for i in range(3)];hi=[max(p[i] for p in corners) for i in range(3)]
    cuts=[]
    for sx in (-1,1):
        for sy in (-1,1):
            d=[(p['width']+p['height'])/2-distance for p,distance in zip(profiles,distances)]
            slope=-(d[1]-d[0]+sx*dot(delta,right)+sy*dot(delta,up))/dz
            n=unit(add(add(scale(right,sx),scale(up,sy)),scale(axis,slope)))
            origin=add(centers[0],add(scale(right,sx*profiles[0]['width']/2),scale(up,sy*(profiles[0]['height']/2-distances[0]))))
            preview=plane_cut(origin,n,lo,hi,max_cutters=16)
            intent={k:v for k,v in preview.items() if k!='cutters'}
            cuts.extend({**c,'intent':intent} for c in preview['cutters'])
    piece['hardCuts']=cuts
    piece['hardFaceIntent']={'kind':'planar_chamfer','geometry':'one plane per corner; actual intermediate native vertices require verification','shading':'hard; actual vertex normals require verification'}


def compile_loft(name, stations, *, normal=(0, 0, 1), up=(0, 1, 0), max_parts=20, reference=None):
    """Compile measured parallel sections; centres and local dimensions survive."""
    name = _name(name)
    normal, up = unit(normal, "normal"), unit(up, "up")
    q = look_rotation(normal, up)
    up = rotate(q, (0, 1, 0))
    if not isinstance(stations, (list, tuple)) or not 2 <= len(stations) <= 21:
        _fail("invalid_geometry", "Use 2..21 explicitly measured stations")
    normalized = [_station(row, i, normal)[0] for i, row in enumerate(stations)]
    ids = [row["id"] for row in normalized]
    if len(ids) != len(set(ids)):
        _fail("invalid_geometry", "Station IDs must be unique")
    pieces, features = [], {}
    for index, (a, b) in enumerate(zip(normalized, normalized[1:])):
        delta = sub(b["center"], a["center"])
        if dot(delta, normal) < .001 or magnitude(delta) > 1000:
            _fail("invalid_geometry", "Stations must increase along the normal by at least 0.001 m and span at most 1000 m", stationIds=[a["id"], b["id"]])
        profiles = [deepcopy(a["profile"]), deepcopy(b["profile"])]
        for i, profile in enumerate(profiles):
            profile["index"] = i
        piece_name = f"{name}/segment-{index}"
        feature_ids = list(dict.fromkeys([a["featureId"], b["featureId"]]))
        pieces.append({"name": piece_name, "stationIds": [a["id"], b["id"]],
                       "centers": [a["center"], b["center"]], "normal": list(normal), "up": list(up),
                       "rotationQuaternion": list(q), "profiles": profiles, "featureIds": feature_ids})
        _compile_hard_corners(pieces[-1],a,b)
        for row in (a, b):
            features.setdefault(row["featureId"], {"pieceNames": [], "stationIds": [], "parameters": [], "referenceRegions": []})
            f = features[row["featureId"]]
            if piece_name not in f["pieceNames"]:
                f["pieceNames"].append(piece_name)
            if row["id"] not in f["stationIds"]:
                f["stationIds"].append(row["id"])
                f["parameters"].extend([f"stations/{row['id']}/center", f"stations/{row['id']}/profile"])
                f["referenceRegions"].append(row["referenceRegion"])
    return _finish(name, "loft", pieces, normalized, features, max_parts, reference,
                   ["Different station normals and arbitrary polygons are not silently approximated",
                    "Native corner clamps, cap topology and joins require native mesh verification",
                    "Adjacent pieces are grouped logically; connections must be explicitly planned"])


def compile_prism(name, *, start, end, width, height, normal=None, up=(0, 1, 0), profile=None, max_parts=1, reference=None):
    """A fixed section extruded between centres; normal may differ from travel."""
    normal = unit(sub(vector(end), vector(start))) if normal is None else normal
    p = deepcopy(profile or {})
    p.update(width=width, height=height)
    return compile_loft(name, [{"id": "start", "center": start, "profile": p},
                               {"id": "end", "center": end, "profile": p}],
                        normal=normal, up=up, max_parts=max_parts, reference=reference)


def compile_recess(name, *, start, end, width, height, opening_width, floor_height,
                   opening_center=0, normal=None, up=(0, 1, 0), max_parts=3, reference=None):
    """Open-topped U channel extruded through its complete length using 3 Bodies.

    Width/height/opening are in the fixed section plane. No boolean capability
    is invented: the empty region is represented by explicit surrounding solids.
    """
    name = _name(name)
    a, b = vector(start), vector(end)
    normal = unit(sub(b, a)) if normal is None else unit(normal)
    q = look_rotation(normal, up)
    right, upper = rotate(q, (1, 0, 0)), rotate(q, (0, 1, 0))
    width = number(width, "width", .003, 1000)
    height = number(height, "height", .003, 1000)
    opening_width = number(opening_width, "opening_width", .001, width)
    floor_height = number(floor_height, "floor_height", .001, height)
    opening_center = number(opening_center, "opening_center")
    left = opening_center - opening_width / 2
    right_edge = opening_center + opening_width / 2
    left_width, right_width = left + width / 2, width / 2 - right_edge
    if min(left_width, right_width, height - floor_height) < .001:
        _fail("invalid_recess", "U channel requires two positive side walls and a positive open height, each >= 0.001 m")
    wall_height = height - floor_height
    specs = [("floor", 0, -height / 2 + floor_height / 2, width, floor_height),
             ("left-wall", -width / 2 + left_width / 2, floor_height / 2, left_width, wall_height),
             ("right-wall", width / 2 - right_width / 2, floor_height / 2, right_width, wall_height)]
    pieces, stations, features = [], [], {}
    for role, x, y, w, h in specs:
        shift = add(scale(right, x), scale(upper, y))
        part = compile_prism(f"{name}/{role}", start=add(a, shift), end=add(b, shift), width=w, height=h,
                             normal=normal, up=up, max_parts=1).to_dict()
        for piece in part["pieces"]:
            piece["featureIds"] = [role, "opening"]
            pieces.append(piece)
        stations.extend(part["stations"])
        features[role] = {"pieceNames": [p["name"] for p in part["pieces"]], "parameters": [role]}
    features["opening"] = {"kind": "negative_space", "required": True,
                           "pieceNames": [p["name"] for p in pieces],
                           "sectionBounds": {"left": left, "right": right_edge, "bottom": -height / 2 + floor_height, "top": height / 2},
                           "parameters": ["opening_width", "opening_center", "floor_height"],
                           "verification": "Check empty-region probes across the extrusion and open top; bounding box cannot certify this feature"}
    return _finish(name, "recess", pieces, stations, features, max_parts, reference,
                   ["Rectangular open-top channel only, through the complete extrusion; no blind pocket or arbitrary boolean claimed",
                    "Three pieces touch at explicit boundaries; native connections and exterior union must be reviewed separately",
                    "Negative-space probes and native surface checks are required after construction"])


def refine_loft(compilation, station_updates, *, protected_station_ids=()):
    """Return a new preview preserving all unmentioned profiles and centres.

    Updates are keyed by stable station ID, use merge semantics, and never
    mutate an existing craft or reset advanced profile properties silently.
    """
    document = compilation.to_dict() if isinstance(compilation, GeometryCompilation) else deepcopy(compilation)
    if document.get("kind") != "loft" or not isinstance(station_updates, dict):
        _fail("invalid_refinement", "refine_loft requires a loft and updates keyed by station ID")
    if any(p.get('hardCuts') for p in document['pieces']) or any(isinstance(v,dict) and v.get('profile',{}).get('corner',{}).get('kind')=='chamfer' for v in station_updates.values()):
        _fail('hard_face_refine_requires_replacement','Hard chamfer changes require an explicitly budgeted component replacement, preserving its complete cutter targets')
    known = {row["id"] for row in document["stations"]}
    if set(station_updates) - known or set(station_updates) & set(protected_station_ids):
        _fail("protected_geometry", "Unknown or protected station update", changed=sorted(station_updates), protected=list(protected_station_ids))
    rows = []
    patch_names = {"cornerRadius": "corner_radius", "cornerStretch": "corner_stretch", "edgeCurvature": "edge_curvature",
                   "syncAdjacent": "sync_adjacent", "thicknessFraction": "thickness_fraction"}
    for row in document["stations"]:
        profile = {patch_names.get(k, k): deepcopy(v) for k, v in row["profile"].items()
                   if k not in ("index", "cornerSamples", "edgeSamples")}
        original = {"id": row["id"], "center": row["center"], "normal": row["normal"], "profile": profile,
                    "featureId": row["featureId"], "referenceRegion": row["referenceRegion"]}
        update = station_updates.get(row["id"], {})
        if set(update) - {"center", "width", "height", "profile"}:
            _fail("invalid_refinement", "Only centre and profile changes are supported in local refinement")
        original.update({k: deepcopy(v) for k, v in update.items() if k != "profile"})
        if "corner" in update.get("profile", {}):
            for key in ("corner_radius", "corner_stretch"):
                original["profile"].pop(key, None)
        original["profile"].update(deepcopy(update.get("profile", {})))
        for key in ("width", "height"):
            if key in update:
                original["profile"][key] = update[key]
                original.pop(key, None)
        rows.append(original)
    reference = None if document["reference"] is None else {**document["reference"], "status": "ready"}
    result = compile_loft(document["name"], rows, normal=document["pieces"][0]["normal"],
                          up=document["pieces"][0]["up"], max_parts=document["pieceCount"], reference=reference)
    # Sampling is authored geometry too; preserve it unless the caller selected
    # a new explicit semantic corner mode in that station's profile.
    updated = result.to_dict()
    for before, after in zip(document["stations"], updated["stations"]):
        if "corner" not in station_updates.get(before["id"], {}).get("profile", {}):
            for key in ("cornerSamples", "edgeSamples"):
                after["profile"][key] = deepcopy(before["profile"][key])
            after["semantics"] = deepcopy(before["semantics"])
    lookup = {s["id"]: s for s in updated["stations"]}
    for piece in updated["pieces"]:
        for index, station_id in enumerate(piece["stationIds"]):
            piece["profiles"][index] = {**deepcopy(lookup[station_id]["profile"]), "index": index}
    updated.pop("compilationHash", None)
    updated["refinement"] = {"previousCompilationHash": document["compilationHash"], "changedStationIds": sorted(station_updates),
                             "protectedStationIds": list(protected_station_ids), "semantics": "merge; native result not_assessed"}
    updated["compilationHash"] = digest(updated)
    return GeometryCompilation(updated)
