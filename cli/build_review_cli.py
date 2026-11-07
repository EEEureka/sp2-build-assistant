"""Review and goal-loop CLI adapters. Live collection is read-only and guarded.

The review algorithms also accept saved native evidence, so inspection never
requires a numerical worker, an editor write, or a game restart.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from reference_storage import ReferenceError, file_hash, read_json, write_json
from reference_binding import identity, snapshot_parts, unwrap


COMMANDS = {"regional.review", "parts.observe"} | {
    "build.loop." + action for action in ("init", "status", "review", "amend", "rebind")}
MUTATES = {"build.loop.init", "build.loop.review", "build.loop.amend", "build.loop.rebind"}
# Review works offline with supplied evidence, or collects through the bridge.
LIVE = {"regional.review", "parts.observe"} | MUTATES

FIELDS = {
    "snapshot": ["object", "string"], "mesh": ["object", "string"],
    "partIds": "array", "baseline": "object", "expectedInterfaces": "array",
    "sections": "array", "outputDir": "string", "budget": "object",
    "toleranceMetres": "number", "reference": ["object", "string"],
    "reviewPlan": ["object", "string"], "referenceMesh": ["object", "string"],
    "role": "string", "roles": ["object", "array"], "frame": "object",
    "capturePartIds": "array", "views": "array", "resolution": "object",
    "neighborDistanceM": "number", "overlapToleranceM": "number", "sectionAxis": "integer",
    "referenceHash": "string", "coordinateFrame": "object",
    "journalPath": "string", "userObjective": "string", "source": "string", "goals": "array",
    "report": ["object", "string"], "subjectReview": ["object", "string"],
    "impactReview": ["object", "string"], "affectedPartIds": "array", "reusedPartIds": "array",
    "impactDiscovery": "object",
    "partMapping": "object", "mappingEvidence": "object", "expectedHeadHash": "string",
    "semanticMapping":"object", "protectedFieldMapping":"array",
    "stagnationRounds": "integer", "completionRequirements": "array", "completionEvidence": "array",
    "requestId": "string",
    "shapeEvidence": "object",
    "replacements": "array", "referenceMatches":"array",
    "nativeViews":"object", "nativeCaptureResults":"object", "nativeImageReviews":"object", "captureNativeViews":"boolean", "referencePartIds":"array",
    "detail":"string",
    "taskKind":"string", "phase":"string", "executionJournals":"array",
}


def input_schema(command):
    if command in ("regional.review", "parts.observe"):
        names = ("snapshot", "mesh", "partIds", "baseline", "expectedInterfaces",
                 "sections", "budget", "reviewPlan", "capturePartIds", "neighborDistanceM",
                 "overlapToleranceM", "sectionAxis", "referenceHash", "replacements", "referenceMesh", "referenceMatches")
        if command == "parts.observe":
            names += ("outputDir", "roles", "shapeEvidence", "nativeViews", "nativeCaptureResults", "nativeImageReviews", "captureNativeViews", "referencePartIds", "detail")
        required = ["partIds"]
        description = "Read-only inspection of actual native mesh evidence. Missing snapshot/mesh are collected from the live designer; supplied files are historical unless verified separately."
    else:
        common = ("journalPath", "snapshot", "requestId", "expectedHeadHash", "taskKind", "phase", "executionJournals")
        names = common + {
            "init": ("userObjective", "source", "goals", "referenceHash", "coordinateFrame",
                     "stagnationRounds", "completionRequirements"),
            "status": ("reusedPartIds", "referenceHash", "coordinateFrame", "impactDiscovery"),
            "review": ("report", "subjectReview", "impactReview", "affectedPartIds",
                       "reusedPartIds", "completionEvidence", "referenceHash", "coordinateFrame", "impactDiscovery"),
            "amend": ("goals", "source", "reusedPartIds", "referenceHash", "coordinateFrame", "impactDiscovery"),
            "rebind": ("partMapping", "semanticMapping", "mappingEvidence", "protectedFieldMapping"),
        }[command.rsplit(".", 1)[-1]]
        required = ["journalPath"]
        description = "Append-only goal ledger. Each review derives next goals from subject and affected-part evidence; it does not autonomously author or apply geometry edits."
    properties = {key: {"type": FIELDS[key]} for key in names}
    if "journalPath" in names:
        properties["journalPath"]["minLength"] = 1
    if "roles" in names:
        properties["roles"] = {"type": "object", "description": "Explicit part-ID-to-role annotation, not inferred native ownership."}
    if "detail" in names:
        properties["detail"].update(enum=["summary","full"],default="summary",description="Summary presents current shape/role/relationships first. The immutable full report is available at reportArtifact.path for precise checks and build.loop.review; use full to return all data inline.")
    if "partIds" in properties:
        properties["partIds"].update(minItems=1, uniqueItems=True,
                                     items={"type": "integer", "minimum": 0})
    result={"type": "object", "properties": properties, "required": required,
            "additionalProperties": False, "description": description}
    if command.startswith('build.loop.'):
        from modeling_contracts import enrich_loop
        result=enrich_loop(command,result)
    return result


def output_schema(command):
    ident = {"type": "object", "required": ["craftSessionId", "revision"],
             "properties": {"craftSessionId": {"type": "string"}, "revision": {"type": "integer"}}}
    if command.startswith("build.loop."):
        data = {"type": "object", "required": ["journalPath", "headHash", "loop", "writesIssued"],
                "properties": {"journalPath": {"type": "string"}, "headHash": {"type": "string"},
                               "loop": {"type": "object", "required": ["userObjective", "goals", "completion", "state"]},
                               "nextRoundGoals": {"type": "array"}, "writesIssued": {"const": False}}}
    else:
        data = {"type": "object", "required": ["identity", "subjectChecks", "impactChecks", "coverage", "findings", "relations"],
                "properties": {"identity": ident, "subjectChecks": {"type": "array"},
                               "impactChecks": {"type": "array"}, "coverage": {"type": "object"},
                               "findings": {"type": "array"}, "relations": {"type": "array"},
                               "evidenceFreshness": {"enum": ["supplied_capture_not_live_verified", "live_identity_verified_at_collection"]}}}
    return {"type": "object", "required": ["success", "schemaVersion"],
            "properties": {"success": {"type": "boolean"}, "schemaVersion": {"const": "1"},
                           "data": data, "error": {"type": "object"}},
            "oneOf": [{"properties": {"success": {"const": True}}, "required": ["data"]},
                      {"properties": {"success": {"const": False}}, "required": ["error"]}]}


def _document(value):
    return unwrap(read_json(value) if isinstance(value, str) else value)


def _ensure_identity(value):
    ident = identity(value)
    if ident.get("stateUncertain"):
        raise ReferenceError("state_uncertain", "Inspection needs a certain captured craft state")
    return ident


def _collect(payload, live, include_shape=False):
    request = deepcopy(payload)
    ids = request.get("partIds")
    if not isinstance(ids, list) or not ids or any(type(i) is not int or i < 0 for i in ids):
        raise ReferenceError("invalid_scope", "partIds must be a nonempty array of nonnegative native part IDs")
    for field in ("snapshot", "mesh", "report", "reviewPlan", "referenceMesh", "reference"):
        if field in request and isinstance(request[field], str):
            request[field] = _document(request[field])
    if "baseline" in request:
        for field in ("snapshot", "mesh"):
            if field in request["baseline"]:
                request["baseline"][field] = _document(request["baseline"][field])
    supplied_snapshot, supplied_mesh = "snapshot" in request, "mesh" in request
    if supplied_snapshot and supplied_mesh:
        request["evidenceFreshness"] = "supplied_capture_not_live_verified"
        return request
    if not callable(live):
        raise ReferenceError("live_required", "Supply snapshot and mesh, or use a running designer bridge")
    snapshot = request.get("snapshot") or unwrap(live("craft.snapshot", {"includeXml": True}))
    ident = _ensure_identity(snapshot)
    if not supplied_mesh:
        parts = snapshot_parts(snapshot)
        capture_ids = request.pop("capturePartIds", None) or sorted(map(int, parts))
        if (not isinstance(capture_ids, list) or
                any(isinstance(i, bool) or not isinstance(i, int) or str(i) not in parts for i in capture_ids)):
            raise ReferenceError("invalid_scope", "capturePartIds must identify existing parts")
        maximum = request.get("budget", {}).get("maxCaptureParts", 512)
        if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 2048:
            raise ReferenceError("invalid_input", "budget.maxCaptureParts must be 1..2048")
        if len(capture_ids) > maximum:
            raise ReferenceError("capture_budget_exceeded", "Declare a scoped capture or increase maxCaptureParts; omitted neighbors cannot be accepted as checked",
                                 partCount=len(capture_ids), maximum=maximum)
        captured = unwrap(live("geometry.section", {
            "craftSessionId": ident["craftSessionId"], "expectedRevision": ident["revision"],
            "partIds": capture_ids, "frame": {"kind": "world"},
            "plane": {"origin": [0, 0, 0], "normal": [0, 1, 0]},
            "limit": 1, "export": True, "exportMeshes": True}))
        if _ensure_identity(captured) != ident:
            raise ReferenceError("state_changed", "Mesh and snapshot were captured from different states")
        manifest = captured.get("manifestPath")
        if not manifest:
            raise ReferenceError("mesh_export_missing", "Native mesh export did not return a downloaded manifest")
        mesh_path = Path(manifest).resolve().parent / "meshes.json"
        descriptor = next((f for f in captured.get("files", []) if f.get("name") == "meshes.json"), None)
        if not descriptor or file_hash(mesh_path) != descriptor.get("sha256"):
            raise ReferenceError("mesh_hash_mismatch", "Downloaded native mesh does not match its receipt")
        request["mesh"] = read_json(mesh_path)
        request["captureReceipt"] = {"identity": ident, "sampleId": captured.get("sampleId"),
                                     "manifestPath": manifest, "meshPath": str(mesh_path),
                                     "sha256": descriptor["sha256"]}
    request["snapshot"] = snapshot
    if include_shape and "shapeEvidence" not in request:
        shape_evidence = {}
        limit = request.get("budget", {}).get("maxShapeParts", 16)
        if type(limit) is not int or not 0 <= limit <= 128:
            raise ReferenceError("invalid_input", "budget.maxShapeParts must be 0..128")
        for pid in request.get("partIds", [])[:limit]:
            try:
                shape = unwrap(live("shape.get", {"id": pid}))
                if _ensure_identity(shape) != ident:
                    raise ReferenceError("state_changed", "Shape controls and native mesh were captured from different states")
                shape_evidence[str(pid)] = shape
            except ReferenceError as error:
                if error.code in ("state_changed", "state_uncertain"):
                    raise
                shape_evidence[str(pid)] = {"success": False, "error": {"code": error.code, "message": str(error)}}
        request["shapeEvidence"] = shape_evidence
    current = unwrap(live("craft.snapshot", {"includeXml": False}))
    if _ensure_identity(current) != ident:
        raise ReferenceError("state_changed", "Craft changed during read-only collection; recapture before accepting this review",
                             capturedIdentity=ident, currentIdentity=identity(current))
    request["evidenceFreshness"] = "live_identity_verified_at_collection"
    return request


def dispatch(command, payload, live=None):
    if command.startswith("build.loop."):
        import build_loop
        request = deepcopy(payload)
        for field in ("snapshot", "report", "subjectReview", "impactReview"):
            if field in request and isinstance(request[field], str):
                request[field] = _document(request[field])
        action = command.rsplit(".", 1)[-1]
        return build_loop.dispatch("create" if action == "init" else action, request, context={"live": live})
    request = _collect(payload, live, include_shape=command == "parts.observe")
    if command == "regional.review":
        from regional_geometry import dispatch as review
    elif command == "parts.observe":
        from part_observation import dispatch as review
        request.setdefault("outputDir", str(Path.cwd()/".local"/"observations"))
    else:
        raise ReferenceError("unsupported_command", "Unknown build review command", command=command)
    result = review(command, request, context={"live": live})
    if command == "parts.observe" and request.get("captureNativeViews"):
        if not callable(live):
            raise ReferenceError("live_required", "captureNativeViews requires the current native designer")
        from review_cameras import verify_native_views
        captures = {}
        for camera in result["nativeViewPlan"]["requests"]:
            raw = live("designer.capture", camera["designerCaptureRequest"])
            captured = unwrap(raw)
            if captured.get("identity") != result["identity"]:
                raise ReferenceError("state_changed", "Craft changed while capturing native review views; recapture the region")
            paths = captured.get("recommendedImages", [])
            captures[camera["id"]] = {"result": raw, "imagePath": paths[0] if paths else None}
        result["nativeCaptureResults"] = captures
        result["nativeViewVerification"] = verify_native_views(result["nativeViewPlan"], captures, request.get("nativeImageReviews"))
    result["evidenceFreshness"] = request["evidenceFreshness"]
    if "captureReceipt" in request:
        result["captureReceipt"] = request["captureReceipt"]
    if result.get("reportArtifact", {}).get("path"):
        # A file cannot contain its own cryptographic digest. Persist the report
        # with the artifact identity/path, then return a hash of those exact bytes.
        result["reportArtifact"].pop("sha256", None)
        result["reportArtifact"]["digestScope"] = "persisted_report_bytes_without_embedded_sha256"
        write_json(result["reportArtifact"]["path"], result)
        result["reportArtifact"]["sha256"] = file_hash(result["reportArtifact"]["path"])
    if command == "parts.observe" and request.get("detail", "summary") == "summary" and result.get("reportArtifact"):
        from part_observation import compact_report
        return compact_report(result)
    return result
