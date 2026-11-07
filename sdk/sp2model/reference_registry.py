"""Durable, versioned modeling references without a Blender dependency.

This registry records reviewed evidence. It does not infer object identity from
similar dimensions, nor claim a photograph is exact geometry. Source mutations
are checked before dependent work and explicit updates retain old versions.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from .errors import ModelingError
from .geometry import (number, vector, unit, dot, cross, add, scale, sub,
                       quaternion, rotate)
from ._services.reference_storage import digest, file_hash, read_json, write_json


def _error(code, message, **details):
    raise ModelingError(code, message, details)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        _error("invalid_reference", f"{field} requires nonblank text")
    return value


def reference_frame(value):
    """Normalize a similarity frame. Units/scale are explicit, never guessed.

    ``basis`` columns map source unit axes to task axes and may be left handed.
    Rotation and basis are alternatives. Task-space distances are metres.
    """
    if not isinstance(value, dict):
        _error("invalid_reference_frame", "frame must be an object")
    required = {"units", "scale", "origin", "axes", "handedness", "scaleSource"}
    missing = sorted(required - value.keys())
    if missing:
        _error("invalid_reference_frame", "Explicit source frame is required", missing=missing)
    if value["units"] not in ("m", "cm", "mm"):
        _error("invalid_reference_frame", "units must be m, cm or mm")
    if value["handedness"] not in ("right", "left"):
        _error("invalid_reference_frame", "handedness must be right or left")
    if value["scaleSource"] not in ("measured", "user", "inferred"):
        _error("invalid_reference_frame", "scaleSource must be measured, user or inferred")
    axes = value["axes"]
    if not isinstance(axes, dict) or set(axes) != {"x", "y", "z"}:
        _error("invalid_reference_frame", "axes must describe x, y and z")
    axes = {key: _text(axes[key], f"axes.{key}") for key in ("x", "y", "z")}
    factor = number(value["scale"], "scale", 1e-12, 1e12)
    origin = list(vector(value["origin"], "frame.origin"))
    if "basis" in value:
        if "rotationQuaternion" in value:
            _error("invalid_reference_frame", "Use basis or rotationQuaternion, not both")
        basis = tuple(vector(row, "frame.basis axis") for row in value["basis"])
        if len(basis) != 3 or any(abs(dot(a, b) - (1 if i == j else 0)) > 1e-7
                                  for i, a in enumerate(basis) for j, b in enumerate(basis)):
            _error("invalid_reference_frame", "basis requires three orthonormal column vectors")
    else:
        if "rotationQuaternion" not in value:
            _error("invalid_reference_frame", "Specify rotationQuaternion or basis explicitly")
        q = quaternion(value["rotationQuaternion"])
        basis = tuple(rotate(q, axis) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    determinant = dot(cross(basis[0], basis[1]), basis[2])
    if (determinant > 0) != (value["handedness"] == "right"):
        _error("invalid_reference_frame", "basis determinant does not match declared handedness")
    result = {"units": value["units"], "scale": factor, "origin": origin,
              "basis": [list(v) for v in basis], "axes": axes,
              "handedness": value["handedness"], "scaleSource": value["scaleSource"]}
    result["metresPerUnit"] = {"m": 1., "cm": .01, "mm": .001}[value["units"]] * factor
    return result


def transform_point(frame, point, *, inverse=False):
    """Use the one frozen reference frame; no per-object alignment is fitted."""
    p = vector(point)
    factor = frame["metresPerUnit"]
    if inverse:
        delta = sub(p, frame["origin"])
        return [dot(delta, axis) / factor for axis in frame["basis"]]
    delta = tuple(sum(frame["basis"][j][i] * p[j] * factor for j in range(3)) for i in range(3))
    return list(add(frame["origin"], delta))


def transform_direction(frame, direction, *, inverse=False):
    p = unit(direction)
    if inverse:
        return [dot(p, axis) for axis in frame["basis"]]
    return [sum(frame["basis"][j][i] * p[j] for j in range(3)) for i in range(3)]


def _source(value):
    if not isinstance(value, dict) or value.get("kind") not in ("mesh", "blender", "photos", "text"):
        _error("invalid_reference", "source.kind must be mesh, blender, photos or text")
    result = deepcopy(value)
    _text(result.get("locator"), "source.locator")
    paths = result.get("files", [])
    if not isinstance(paths, list):
        _error("invalid_reference", "source.files must be a list of local paths")
    result["files"] = []
    for item in paths:
        path = item["path"] if isinstance(item, dict) else item
        actual = file_hash(path)
        if isinstance(item, dict) and item.get("expectedSha256") is not None and item["expectedSha256"] != actual:
            _error("reference_changed", "Reference source changed after geometry measurement", path=str(path), expected=item["expectedSha256"], actual=actual)
        result["files"].append({"path": str(Path(path).expanduser().resolve()), "sha256": actual})
    if result["kind"] == "text":
        _text(result.get("text"), "source.text")
    elif not result["files"] and not result.get("contentFingerprint"):
        _error("invalid_reference", "A mesh/photo/Blender source needs files or a live contentFingerprint")
    return result


def _normalize(spec):
    if not isinstance(spec, dict):
        _error("invalid_reference", "Reference spec must be an object")
    source = _source(spec.get("source"))
    frame = reference_frame(spec.get("frame"))
    candidates = deepcopy(spec.get("candidates", []))
    if not isinstance(candidates, list) or any(not isinstance(c, dict) for c in candidates):
        _error("invalid_reference", "candidates must be objects")
    ids = [_text(c.get("id"), "candidate.id") for c in candidates]
    if len(set(ids)) != len(ids):
        _error("invalid_reference", "Candidate IDs must be unique")
    for c in candidates:
        _text(c.get("locator"), "candidate.locator")
        if "transform" not in c or "selection" not in c:
            _error("invalid_reference", "Each candidate requires transform and selection", candidateId=c["id"])
    selected = deepcopy(spec.get("selectedCandidateIds", []))
    if not isinstance(selected, list) or len(set(selected)) != len(selected) or set(selected) - set(ids):
        _error("invalid_reference", "selectedCandidateIds must name distinct listed candidates")
    if source["kind"] in ("mesh", "blender") and not candidates:
        _error("invalid_reference", "Mesh/Blender references require explicit object or connected-region candidates")
    unresolved = deepcopy(spec.get("unresolved", []))
    if not isinstance(unresolved, list):
        _error("invalid_reference", "unresolved must be a list")
    if candidates and not selected:
        unresolved.append({"kind": "selection", "message": "Select the intended candidate explicitly",
                           "nextAction": "Inspect candidate locations/previews and bind selectedCandidateIds"})
    rationale = spec.get("selectionReason", "")
    if selected and not str(rationale).strip():
        unresolved.append({"kind": "selection_reason", "nextAction": "Record why this selection meets the user constraints"})
    uncertainties = deepcopy(spec.get("uncertainties", []))
    assumptions = deepcopy(spec.get("assumptions", []))
    if not isinstance(uncertainties, list) or not isinstance(assumptions, list):
        _error("invalid_reference", "uncertainties and assumptions must be lists")
    assumption_ids = {a.get("id") for a in assumptions if isinstance(a, dict) and a.get("accepted") is True and a.get("reason")}
    for item in uncertainties:
        if not isinstance(item, dict) or not item.get("id") or not item.get("description"):
            _error("invalid_reference", "Each uncertainty requires id and description")
        if "interval" in item:
            interval = vector(item["interval"], "uncertainty.interval", 2)
            if interval[0] > interval[1]:
                _error("invalid_reference", "Uncertainty interval must be ordered")
        if item.get("critical") is True and item["id"] not in assumption_ids and not item.get("resolvedBy"):
            unresolved.append({"kind": "uncertainty", "id": item["id"], "nextAction": "Provide evidence or explicitly accept a documented assumption"})
    features = deepcopy(spec.get("features", []))
    if not isinstance(features, list) or any(not isinstance(f, dict) for f in features):
        _error("invalid_reference", "features must be objects")
    feature_ids = [_text(f.get("id"), "feature.id") for f in features]
    if len(set(feature_ids)) != len(feature_ids):
        _error("invalid_reference", "Feature IDs must be unique")
    for f in features:
        _text(f.get("component"), "feature.component")
        if f.get("evidenceKind") not in ("measured", "user", "inferred", "assumption"):
            _error("invalid_reference", "Feature evidenceKind must distinguish measured/user/inferred/assumption", featureId=f["id"])
        if f.get("evidenceKind") in ("inferred", "assumption") and f.get("exact") is True:
            _error("invalid_reference", "Inferred geometry cannot be marked exact", featureId=f["id"])
        if source["kind"] in ("photos", "text") and f.get("evidenceKind") == "measured" and not f.get("measurementSource"):
            _error("invalid_reference", "Photo/text measurements require explicit measurementSource", featureId=f["id"])
    frame_id = "frame:" + digest(frame)[:24]
    for f in features:
        if f.get("frameId", frame_id) != frame_id:
            _error("reference_frame_mismatch", "Feature belongs to a different frame", featureId=f["id"])
        if f.get("geometryFrame", "task_metres") != "task_metres" or f.get("units", "m") != "m":
            _error("reference_frame_mismatch", "Normalize feature geometry to the frozen task frame in metres before binding", featureId=f["id"])
        f["frameId"] = frame_id
        f["geometryFrame"], f["units"] = "task_metres", "m"
    result = {"source": source, "frame": frame, "frameId": frame_id,
              "candidates": candidates, "selectedCandidateIds": selected,
              "selectionReason": rationale, "constraints": deepcopy(spec.get("constraints", [])),
              "scope": deepcopy(spec.get("scope", [])), "uncertainties": uncertainties,
              "assumptions": assumptions, "features": features, "unresolved": unresolved,
              "status": "unresolved" if unresolved else "ready", "views": deepcopy(spec.get("views", []))}
    digest(result)  # Reject non-JSON / nonfinite evidence before persistence.
    return result


class ReferenceRegistry:
    """One registry JSON file; writes are atomic and old reference versions remain."""
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    def _read(self):
        if not self.path.exists():
            return {"kind": "sp2model.reference-registry", "schemaVersion": 1, "references": {}}
        return read_json(self.path, "sp2model.reference-registry")

    def bind(self, reference_id, spec, *, replace=False):
        if not isinstance(reference_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", reference_id):
            _error("invalid_reference_id", "Use a stable 1..128 character reference ID")
        normalized = _normalize(spec)
        content_hash = digest(normalized)
        before_hash = file_hash(self.path) if self.path.exists() else None
        data = self._read()
        versions = data["references"].setdefault(reference_id, [])
        if versions and versions[-1]["contentHash"] == content_hash:
            return deepcopy(versions[-1])
        if versions and not replace:
            _error("reference_changed", "Explicit replace=True is required to version a changed reference",
                   referenceId=reference_id, previousVersion=versions[-1]["version"], nextAction="Review differences and bind with replace=True")
        record = {"referenceId": reference_id, "version": len(versions) + 1,
                  "contentHash": content_hash, **normalized}
        versions.append(record)
        write_json(self.path, data, expected_hash=before_hash, overwrite=before_hash is not None)
        return deepcopy(record)

    def inspect(self, reference_id, version=None):
        versions = self._read()["references"].get(reference_id, [])
        if not versions:
            _error("reference_not_found", "Bind the reference before dependent construction", referenceId=reference_id)
        if version is not None and (type(version) is not int or not 1 <= version <= len(versions)):
            _error("reference_version_not_found", "Requested reference version is unavailable", referenceId=reference_id, version=version)
        record = versions[-1] if version is None else versions[version - 1]
        actual_hash = digest({key: value for key, value in record.items() if key not in ("referenceId", "version", "contentHash")})
        if actual_hash != record.get("contentHash") or record.get("referenceId") != reference_id:
            _error("reference_integrity_error", "Frozen reference record changed outside explicit versioning",
                   referenceId=reference_id, version=record.get("version"), expected=record.get("contentHash"), actual=actual_hash)
        return deepcopy(record)

    def verify(self, reference_id, spec=None, *, version=None):
        record = self.inspect(reference_id, version)
        changes = []
        for item in record["source"]["files"]:
            try:
                current = file_hash(item["path"])
            except (OSError, ValueError):
                current = None
            if current != item["sha256"]:
                changes.append({"kind": "source_file", "path": item["path"], "expected": item["sha256"], "actual": current})
        if spec is not None:
            current_hash = digest(_normalize(spec))
            if current_hash != record["contentHash"]:
                changes.append({"kind": "manifest", "expected": record["contentHash"], "actual": current_hash})
        return {"referenceId": reference_id, "version": record["version"], "contentHash": record["contentHash"],
                "status": "changed" if changes else record["status"], "changes": changes,
                "liveSourceRevalidated": spec is not None or bool(record["source"]["files"]),
                "limitation": None if record["source"]["files"] else "Live object transforms/selection require a fresh source spec; a persisted content fingerprint alone cannot poll Blender."}

    def require_ready(self, reference_id, *, scope=None, version=None, spec=None):
        report = self.verify(reference_id, spec, version=version)
        if report["status"] != "ready":
            _error("reference_not_ready", "Reference is unresolved or changed; dependent writes are blocked", **report,
                   nextAction="Inspect reference, supply missing evidence or explicitly bind a new version")
        record = self.inspect(reference_id, version)
        if scope is not None:
            requested = [scope] if isinstance(scope, str) else list(scope)
            if set(requested) - set(record["scope"]):
                _error("reference_scope_mismatch", "Measurement/construction scope differs from reference scope", requested=requested, referenceScope=record["scope"])
        return record

    def preview(self, reference_id, mesh, camera, output_directory, *, view_id, version=None, renderer=None):
        """Render a declared selected mesh with the existing CPU renderer.

        Caller supplies the mesh for the selection; an optional source meshHash
        is checked. This is generated evidence, never a claim an Agent viewed it.
        """
        record = self.require_ready(reference_id, version=version)
        _text(view_id, "view_id")
        if not isinstance(camera, dict) or camera.get("projection") != "orthographic":
            _error("invalid_reference_view", "Frozen local comparison previews must be orthographic")
        expected = record["source"].get("meshHash")
        if expected and expected != digest(mesh):
            _error("reference_mesh_mismatch", "Preview mesh is not the frozen source mesh")
        if not isinstance(mesh, dict) or "vertices" not in mesh:
            _error("invalid_reference_mesh", "Preview requires a canonical selected mesh with vertices and triangles")
        transformed = deepcopy(mesh)
        transformed["vertices"] = [transform_point(record["frame"], p) for p in mesh["vertices"]]
        if renderer is None:
            from ._services.reference_render import render
            renderer = render
        try:
            rendered = renderer({"mesh": transformed, "camera": camera, "units": "m",
                                 "outputDirectory": str(output_directory), "includeBuffers": False})
        except ImportError as exc:
            _error("reference_worker_required", "Reference preview needs the installed numerical worker",
                   nextAction="Invoke the existing reference render worker and pass its renderer callback; no Blender is needed", dependency=str(exc))
        verified_camera = rendered["camera"]
        # The established renderer validates the camera; check all selected
        # vertices against that identical view, including viewport clipping.
        matrix, params = verified_camera["worldToCamera"], verified_camera["orthographic"]
        def in_view(p):
            xyz = [sum(matrix[i][j] * p[j] for j in range(3)) + matrix[i][3] for i in range(3)]
            x = params["scaleX"] * xyz[0] + params["cx"]
            y = -params["scaleY"] * xyz[1] + params["cy"]
            return (verified_camera["near"] <= xyz[2] <= verified_camera["far"] and
                    0 <= x < verified_camera["width"] and 0 <= y < verified_camera["height"])
        visible = int(rendered["visiblePixelCount"])
        clipped = any(not in_view(p) for p in transformed["vertices"])
        files = rendered.get("files", {})
        report = {"referenceId": reference_id, "version": record["version"], "contentHash": record["contentHash"],
                  "frameId": record["frameId"], "viewId": view_id, "camera": verified_camera,
                  "meshHash": digest(mesh), "visiblePixelCount": visible, "targetOutsideView": clipped,
                  "status": "empty" if not visible else "clipped" if clipped else "generated",
                  "provided": False, "viewed": "not_assessed", "evaluated": "not_assessed", "files": files}
        write_json(Path(output_directory) / "reference-preview.json", report)
        return report
