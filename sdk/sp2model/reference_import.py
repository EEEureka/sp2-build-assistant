"""Measure frozen indexed reference meshes without Blender or numeric packages.

The input is inert UTF-8 JSON, never source code. Positions are transformed once
from the declared source frame into task metres. Agent-selected components and
planes become measured contours and station data, not a model-specific preset.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .errors import ModelingError
from .geometry import vector, unit, number, add, sub, scale, dot, cross, rotate, look_rotation
from .mesh import MeshEvidence
from .model_compare import planar_exterior, _basis
from .reference_registry import reference_frame, transform_point
from ._services.reference_storage import digest, file_hash


LIMITS = {"fileBytes": 64 * 1024 * 1024, "vertices": 250000, "triangles": 250000, "meshes": 2048, "sections": 32}


def _fail(code, message, **details):
    raise ModelingError(code, message, details)


def _identifier(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).strip():
        _fail("invalid_reference_mesh", f"{field} must be a nonblank string or integer")
    return value


def _read_mesh(path, frame):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > LIMITS["fileBytes"]:
        _fail("reference_mesh_unavailable", "Use a local mesh JSON file no larger than 64 MiB", path=str(path))
    raw = path.read_bytes()
    if len(raw) > LIMITS["fileBytes"]:
        _fail("reference_mesh_budget", "Reference mesh exceeded its read budget")
    checksum = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8-sig"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError) as exc:
        _fail("invalid_reference_mesh", "Reference must be finite UTF-8 JSON; code and scene files are not executed", reason=str(exc))
    if not isinstance(data, dict):
        _fail("invalid_reference_mesh", "Mesh JSON root must be an object")
    rows = data.get("meshes", [data])
    if not isinstance(rows, list) or not 1 <= len(rows) <= LIMITS["meshes"]:
        _fail("reference_mesh_budget", f"Use 1..{LIMITS['meshes']} explicit mesh records", maximumMeshes=LIMITS["meshes"])
    meshes, inventory, identifiers = [], [], set()
    vertex_count = triangle_count = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _fail("invalid_reference_mesh", "Every mesh record must be an object")
        if any(key in row for key in ("matrix", "matrixWorld", "transform")):
            _fail("unapplied_mesh_transform", "Bake object transforms into exported source-space vertices; only the declared reference frame is applied", meshIndex=index)
        identifier = _identifier(row.get("partId", row.get("id", f"mesh-{index}")), "mesh.partId")
        identity_key = (type(identifier).__name__, identifier)
        if identity_key in identifiers:
            _fail("ambiguous_reference_mesh", "Mesh partIds must be unique", partId=identifier)
        identifiers.add(identity_key)
        vertices, indices = row.get("vertices"), row.get("indices")
        if not isinstance(vertices, list) or len(vertices) < 3 or not isinstance(indices, list) or not indices:
            _fail("invalid_reference_mesh", "Each selected mesh needs vertices and triangle indices", partId=identifier)
        if all(isinstance(value, list) for value in indices):
            if any(len(value) != 3 for value in indices):
                _fail("invalid_reference_mesh", "Nested indices must contain triangle triples")
            indices = [i for triple in indices for i in triple]
        if len(indices) % 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in indices):
            _fail("invalid_reference_mesh", "Indices must be integer triples within the vertex array", partId=identifier)
        vertex_count += len(vertices)
        triangle_count += len(indices) // 3
        if vertex_count > LIMITS["vertices"] or triangle_count > LIMITS["triangles"]:
            _fail("reference_mesh_budget", "Mesh exceeds bounded CPU reference-measurement capacity", maximum=LIMITS)
        points = [transform_point(frame, vector(point, "source vertex")) for point in vertices]
        if any(max(abs(value) for value in point) > 100000 for point in points):
            _fail("invalid_reference_mesh", "Task-space vertex exceeds the 100 km coordinate bound")
        name = row.get("name", str(identifier))
        if not isinstance(name, str) or not name.strip():
            _fail("invalid_reference_mesh", "Mesh names must be nonblank strings")
        meshes.append({"partId": identifier, "vertices": points, "indices": indices})
        inventory.append({"partId": identifier, "name": name, "vertexCount": len(points), "triangleCount": len(indices) // 3,
                          "boundsTaskMetres": {"min": [min(p[i] for p in points) for i in range(3)], "max": [max(p[i] for p in points) for i in range(3)]},
                          "locator": str(path) + "#" + str(identifier)})
    return {"path": str(path), "sha256": checksum}, meshes, inventory


def _selection(selector, inventory):
    keys = [key for key in ("partIds", "meshNames") if key in selector]
    if len(keys) != 1:
        _fail("reference_selection_required", "Select exactly one explicit nonempty partIds or meshNames list; never choose a mesh by bounding box similarity")
    key = keys[0]
    values = selector[key]
    if not isinstance(values, list) or not values:
        _fail("reference_selection_required", f"{key} must be a nonempty list")
    try:
        if len(set(values)) != len(values):
            _fail("ambiguous_reference_mesh", "Selection values must be unique")
    except TypeError:
        _fail("invalid_reference_mesh", "Selection values must be names or part IDs")
    selected = []
    for value in values:
        value = _identifier(value, key)
        matches = [row for row in inventory if (row["partId"] == value and type(row["partId"]) is type(value))] if key == "partIds" else [row for row in inventory if row["name"] == value]
        if len(matches) != 1:
            _fail("ambiguous_reference_mesh", "Every selection must match exactly one mesh", selector=key, value=value, matches=len(matches), nextAction="Inspect mesh inventory and select unique partIds")
        selected.append(matches[0]["partId"])
    return selected


def _planes(spec, selected_meshes):
    identifier = spec.get("id")
    component = spec.get("component")
    if not isinstance(identifier, str) or not identifier.strip() or not isinstance(component, str) or not component.strip():
        _fail("invalid_reference_section", "Every section requires id and component")
    if spec.get("geometryFrame", "task_metres") != "task_metres":
        _fail("reference_frame_mismatch", "Section origins, normals and axes must be in task_metres; use transform_point/direction for source coordinates")
    has_plane = "origin" in spec or "normal" in spec
    has_fractions = "axis" in spec or "fractions" in spec
    if has_plane == has_fractions:
        _fail("invalid_reference_section", "Use origin+normal OR axis+fractions explicitly")
    if has_plane:
        return [{**deepcopy(spec), "origin": list(vector(spec.get("origin"), "section origin")),
                 "normal": list(unit(spec.get("normal"), "section normal"))}]
    axis = unit(spec.get("axis"), "fraction axis")
    fractions = spec.get("fractions")
    if not isinstance(fractions, list) or not 1 <= len(fractions) <= LIMITS["sections"]:
        _fail("invalid_reference_section", "fractions must contain 1..32 explicit positions")
    fractions = [number(value, "fraction", 0, 1) for value in fractions]
    if len(set(fractions)) != len(fractions):
        _fail("invalid_reference_section", "Fraction positions must be distinct")
    points = [p for mesh in selected_meshes for p in mesh["vertices"]]
    low, high = min(dot(p, axis) for p in points), max(dot(p, axis) for p in points)
    if high - low < 1e-8:
        _fail("invalid_reference_section", "Selected mesh has no extent along the declared fraction axis")
    anchor = tuple((min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in range(3))
    return [{**deepcopy(spec), "id": f"{identifier}/{index}", "origin": list(add(anchor, scale(axis, low + fraction * (high-low) - dot(anchor, axis)))),
             "normal": list(axis), "fraction": fraction, "fractionAxisRangeMetres": [low, high]}
            for index, fraction in enumerate(fractions)]


def measure_mesh(mesh_path, frame, sections=None, *, weld_tolerance_m=1e-6):
    """Return inventory or measured feature suggestions without any native write.

    Each section explicitly selects partIds or unique meshNames. Plane origins
    are task metres; optional axis+fractions use the selected mesh's task-space
    extent. ``up`` controls station width/height axes. Generated centres also
    retain the comparison engine's documented boundary_bbox definition.
    """
    frame = reference_frame(frame)
    frame_id = "frame:" + digest(frame)[:24]
    weld = number(weld_tolerance_m, "weld_tolerance_m", 1e-10, .01)
    source, meshes, inventory = _read_mesh(mesh_path, frame)
    report = {"status": "inventory", "source": source, "frame": frame, "frameId": frame_id,
              "geometryFrame": "task_metres", "units": "m", "inventory": inventory, "measurements": [], "features": [],
              "artifactProvenance": "supplied reference mesh JSON with SHA256, not native game mesh",
              "nativeArtifactVerified": False, "limits": LIMITS,
              "coverage": "Explicit selected plane sections only; no guarantee all visually important features have been declared"}
    if sections is None:
        return report
    if not isinstance(sections, list) or not 1 <= len(sections) <= LIMITS["sections"]:
        _fail("invalid_reference_section", "sections requires 1..32 plane specifications")
    expanded = []
    allowed = {"id", "component", "partIds", "meshNames", "origin", "normal", "axis", "fractions", "up", "tolerance_m", "viewId",
               "geometryFrame", "boundaryRule", "parameters", "required", "assumptionAccepted"}
    for spec in sections:
        if not isinstance(spec, dict) or set(spec) - allowed:
            _fail("invalid_reference_section", "Section fields must follow the explicit measurement contract", fields=sorted(set(spec) - allowed) if isinstance(spec, dict) else [])
        identifiers = _selection(spec, inventory)
        selected = [mesh for mesh in meshes if mesh["partId"] in identifiers]
        expanded.extend((plane, selected) for plane in _planes(spec, selected))
    if len(expanded) > LIMITS["sections"] or len({row[0]["id"] for row in expanded}) != len(expanded):
        _fail("reference_mesh_budget", "Expanded sections require unique IDs and at most 32 planes")
    for plane, selected in expanded:
        origin, normal = plane["origin"], plane["normal"]
        tolerance = number(plane.get("tolerance_m", .01), "section tolerance_m", 1e-6, 1000)
        # A file reference is not a game capture. _artifact_verified remains False.
        evidence = MeshEvidence({"captureId": "reference:" + source["sha256"], "exclusions": []},
                                {"identity": {"sourceSha256": source["sha256"]}, "meshes": selected})
        section = evidence.section(origin, normal, weld_tolerance_m=weld)
        rule = plane.get("boundaryRule", "planar_union")
        boundary = planar_exterior(section, boundary_rule=rule)
        measured = {"id": plane["id"], "component": plane["component"], "partIds": [m["partId"] for m in selected],
                    "plane": {"origin": origin, "normal": normal}, "boundary": boundary,
                    "source": source, "status": boundary["status"], "viewId": plane.get("viewId")}
        if "fraction" in plane:
            measured.update(fraction=plane["fraction"], fractionAxisRangeMetres=plane["fractionAxisRangeMetres"])
        report["measurements"].append(measured)
        if boundary["status"] != "complete":
            measured["nextAction"] = "Choose an interior plane, review open mesh topology or explicitly declare cap_boundary; incomplete samples cannot freeze geometry targets"
            continue
        points = [p for segment in boundary["segments"] for p in segment]
        _, _, bx, by = _basis(origin, normal)
        center = tuple(origin)
        for axis in (bx, by):
            values = [dot(sub(p, origin), axis) for p in points]
            center = add(center, scale(axis, (min(values) + max(values)) / 2))
        up = plane.get("up")
        if up is None:
            width_axis, height_axis = bx, by
            up = by
        else:
            q = look_rotation(normal, up)
            width_axis, height_axis = rotate(q, (1, 0, 0)), rotate(q, (0, 1, 0))
            up = height_axis
        bounds = [[min(dot(sub(p, origin), axis) for p in points), max(dot(sub(p, origin), axis) for p in points)] for axis in (width_axis, height_axis)]
        station_center = add(origin, add(scale(width_axis, sum(bounds[0]) / 2), scale(height_axis, sum(bounds[1]) / 2)))
        measured["station"] = {"id": plane["id"], "center": list(station_center), "normal": normal,
                               "width": bounds[0][1]-bounds[0][0], "height": bounds[1][1]-bounds[1][0]}
        measured["profileAxes"] = {"width": list(width_axis), "height": list(height_axis), "up": list(up)}
        measured["boundaryBBoxCenter"] = list(center)
        measured["stationMeaning"] = "Measured boundary bounds, not a guarantee a rectangular native profile reproduces this contour; retain all contour features"
        common = {"component": plane["component"], "evidenceKind": "inferred" if frame["scaleSource"] == "inferred" else "measured", "geometryFrame": "task_metres", "frameId": frame_id,
                  "units": "m", "viewId": plane.get("viewId"), "tolerance_m": tolerance,
                  "required": plane.get("required", True), "parameters": deepcopy(plane.get("parameters", [])),
                  "evidenceSource": {**source, "partIds": measured["partIds"], "sectionId": plane["id"], "kind": "supplied_mesh_section"},
                  "measurementSource": {**source, "frameId": frame_id},
                  "certainty": "inferred" if frame["scaleSource"] == "inferred" else "exact",
                  "assumptionAccepted": plane.get("assumptionAccepted", False)}
        expected_plane = {"origin": origin, "normal": normal, "boundaryRule": rule, "weldToleranceMetres": weld}
        features = [{**deepcopy(common), "id": plane["id"] + ".contour", "kind": "section_contour",
                     "expected": {**expected_plane, "segments": deepcopy(boundary["segments"])}},
                    {**deepcopy(common), "id": plane["id"] + ".center", "kind": "section_center",
                     "expected": {**expected_plane, "center": list(center), "definition": "boundary_bbox"}}]
        for label, axis in (("width", width_axis), ("height", height_axis)):
            values = [dot(p, axis) for p in points]
            for side, value in (("min", min(values)), ("max", max(values))):
                features.append({**deepcopy(common), "id": f"{plane['id']}.{label}.{side}", "kind": "section_boundary",
                                 "expected": {**expected_plane, "axis": list(axis), "side": side, "valueMetres": value}})
        report["features"].extend(features)
    report["status"] = "complete" if all(row["status"] == "complete" for row in report["measurements"]) else "incomplete"
    report["measurementHash"] = digest({"source": source, "frame": frame, "sections": sections, "features": report["features"]})
    return report


def bind_mesh_reference(registry, reference_id, spec, mesh_path, sections, *, replace=False):
    """Freeze measured features only after explicit object/region selection.

    Candidate selection can use {partIds:[...]} or {meshNames:[...]}; a list is
    an explicit partIds selection. Every measured member must be covered by the
    chosen candidate(s), so a selected origin copy cannot silently authorize an
    installed copy of similar dimensions.
    """
    if not isinstance(spec, dict):
        _fail("invalid_reference", "spec must be a reference object")
    report = measure_mesh(mesh_path, spec.get("frame"), sections)
    if report["status"] != "complete":
        _fail("reference_measurement_incomplete", "Incomplete sections cannot become frozen modeling truth", measurements=report["measurements"], nativeWrites=0)
    selected_candidates = spec.get("selectedCandidateIds", [])
    candidates = spec.get("candidates", [])
    if not isinstance(selected_candidates, list) or not selected_candidates or not isinstance(candidates, list):
        _fail("reference_selection_required", "Review mesh inventory and provide selectedCandidateIds with explicit candidate selections")
    chosen = [candidate for candidate in candidates if candidate.get("id") in selected_candidates]
    if len(chosen) != len(selected_candidates):
        _fail("reference_selection_required", "Every selected candidate must exist exactly once")
    authorized = set()
    for candidate in chosen:
        selector = candidate.get("selection")
        selector = {"partIds": selector} if isinstance(selector, list) else selector
        if not isinstance(selector, dict):
            _fail("reference_selection_required", "Selected candidate needs explicit partIds or meshNames")
        authorized.update(_selection(selector, report["inventory"]))
    measured_ids = {identifier for row in report["measurements"] for identifier in row["partIds"]}
    if measured_ids - authorized:
        _fail("reference_scope_mismatch", "Sections contain meshes outside the explicitly selected candidate", measuredPartIds=sorted(measured_ids, key=str), selectedPartIds=sorted(authorized, key=str))
    frozen = deepcopy(spec)
    source = frozen.setdefault("source", {})
    if source.get("kind") not in ("mesh", "blender"):
        _fail("invalid_reference", "A measured mesh reference source.kind must be mesh or blender")
    if file_hash(report["source"]["path"]) != report["source"]["sha256"]:
        _fail("reference_changed", "Mesh file changed while measuring; repeat read-only measurement")
    files = source.setdefault("files", [])
    mesh_path = report["source"]["path"]
    source["files"] = [p for p in files if str(Path(p.get("path") if isinstance(p, dict) else p).expanduser().resolve()) != mesh_path]
    source["files"].append({"path": mesh_path, "expectedSha256": report["source"]["sha256"]})
    source["contentFingerprint"] = report["source"]["sha256"]
    source["measurementHash"] = report["measurementHash"]
    source["geometryFrame"] = "source vertices transformed once by frozen frame"
    features = frozen.setdefault("features", [])
    if not isinstance(features, list):
        _fail("invalid_reference", "features must be a list")
    ids = [f.get("id") for f in features] + [f["id"] for f in report["features"]]
    if len(ids) != len(set(ids)):
        _fail("duplicate_reference_feature", "Generated section IDs collide with existing features; rename sections or remove only explicitly superseded features")
    features.extend(deepcopy(report["features"]))
    measured_scope = {f["component"] for f in report["features"]}
    if not frozen.get("scope"):
        frozen["scope"] = sorted(measured_scope)
    elif measured_scope - set(frozen["scope"]):
        _fail("reference_scope_mismatch", "Measured components are outside the declared reference scope", measuredComponents=sorted(measured_scope), scope=frozen["scope"])
    record = registry.bind(reference_id, frozen, replace=replace)
    return {"reference": record, "measurement": report, "nativeWrites": 0}


BLENDER_EXPORT_EXAMPLE = '''# Run deliberately in Blender; this helper never runs source code.
# Choose the intended installed objects first. Object transforms are baked once.
import bpy, json
meshes = []
for obj in bpy.context.selected_objects:
    if obj.type != "MESH": continue
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        meshes.append({"partId": obj.name, "name": obj.name,
            "vertices": [list(evaluated.matrix_world @ v.co) for v in mesh.vertices],
            "indices": [i for tri in mesh.loop_triangles for i in tri.vertices]})
    finally:
        evaluated.to_mesh_clear()
with open(EXPORT_PATH, "w", encoding="utf-8") as stream:
    json.dump({"meshes": meshes}, stream)
# Declare source units/axes/frame explicitly; no implicit Blender-unit guess.
'''
