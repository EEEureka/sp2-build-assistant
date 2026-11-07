"""Stdlib adapter from the public CLI live transport to guarded fit callbacks."""
import hashlib
import json
from pathlib import Path
import uuid

from .fit_parameters import check_plan


class NativeFitError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details


def make_live(live, payload):
    """Adapt live(command,args)->bridge envelope; never access game craft files."""
    plan = check_plan(payload["plan"])
    candidate = payload["candidate"]
    if payload.get("frame", {"kind": "world"}) != {"kind": "world"}:
        raise NativeFitError("unsupported_fit_frame", "Native fit translation bindings and proxy meshes require the world frame")
    required = set(plan.get("frozenPartIds", []))
    for operation in candidate.get("operations", []):
        required.update(operation.get("partIds", [operation.get("partId")]))
    scoped = set(payload.get("partIds", []))
    if not scoped:
        scoped.update(required)
    if not scoped or any(type(i) is not int or i < 0 for i in scoped):
        raise NativeFitError("invalid_fit_scope", "Native fit requires an explicit nonempty part scope")
    if not required <= scoped:
        raise NativeFitError("incomplete_fit_scope", "Native fit exports must include every affected and frozen part", missingPartIds=sorted(required - scoped))
    parts = sorted(scoped)
    initial, latest, exported = {}, {}, {}
    journal_path = str(Path(payload.get("journalPath") or (Path.home() / ".sp2build" / "fit-runs" / (candidate["candidateHash"] + ".jsonl"))).expanduser().resolve())
    if journal_path:
        from .run_journal import status
        previous = status(journal_path)
        if previous["pendingWrites"]:
            raise NativeFitError("reconcile_required", "Fit journal has a result-unknown operation; reconcile it before another write", pendingWrites=previous["pendingWrites"])
        if previous["state"] == "failed":
            raise NativeFitError("new_plan_required", "This fit run failed. Preserve its journal and prepare a new reviewed plan before another write")

    def journal(event, **data):
        if journal_path:
            from .run_journal import append
            append(journal_path, event, runId=payload.get("runId", candidate["candidateHash"]), planHash=plan["planHash"], **data)

    def failed_write(command, request, error):
        details = getattr(error, "details", {})
        details = dict(details) if isinstance(details, dict) else {}
        operation_id = details.get("operationId")
        failure = {"code": getattr(error, "code", "transport_failed"), "message": str(error), "details": details}
        operation, query_error = None, None
        if isinstance(operation_id, str) and operation_id:
            try:
                result = live("operation.status", {"id": operation_id})
                if not isinstance(result, dict) or not result.get("success") or not isinstance(result.get("data"), dict):
                    raise NativeFitError("status_unavailable", "The original operation status was not returned")
                operation = result["data"]
                if operation.get("operationId") != operation_id:
                    raise NativeFitError("operation_mismatch", "Status returned another operation")
            except Exception as status_error:
                operation = None
                query_error = {"code": getattr(status_error, "code", "status_failed"), "message": str(status_error)}
        terminal_failed = operation is not None and operation.get("state") in ("failed", "cancelled")
        rejected = not operation_id and details.get("writeDisposition") == "rejected_before_acceptance"
        if terminal_failed or rejected:
            journal("write_failed" if terminal_failed else "write_rejected", requestId=request, command=command,
                    operationId=operation_id, error=failure, operation=operation, state="failed", nextAction="new_plan_required")
            raise NativeFitError("new_plan_required", "Native fit write failed; preserve candidates and prepare a new reviewed plan",
                                 requestId=request, operationId=operation_id, error=failure, operation=operation) from error
        # Completed/expired status is not a validated receipt. Keep the pending
        # request until explicit readback reconciliation; never replay it here.
        journal("write_result_unknown", requestId=request, command=command, operationId=operation_id,
                error=failure, operation=operation, statusQueryError=query_error, state="reconcileRequired")
        raise NativeFitError("result_unknown", "Native fit write outcome needs reconciliation; query the original operation and do not replay",
                             requestId=request, operationId=operation_id, error=failure) from error

    def call(command, args, mutates=False):
        body = dict(args)
        request = uuid.uuid4().hex
        if mutates:
            body["requestId"] = request
            journal("write_prepared", requestId=request, command=command, args=body, state="applying")
        try:
            response = live(command, body)
        except Exception as error:
            if mutates:
                failed_write(command, request, error)
            raise
        if not isinstance(response, dict) or not response.get("success") or not isinstance(response.get("data"), dict):
            error = response.get("error", {}) if isinstance(response, dict) else {}
            error = error if isinstance(error, dict) else {}
            details = dict(error.get("details", {})) if isinstance(error.get("details"), dict) else {}
            if isinstance(response, dict):
                for key in ("operationId", "writeDisposition"):
                    if key in response:
                        details[key] = response[key]
            failure = NativeFitError(error.get("code", "native_fit_failed"), error.get("message", "Native fit command failed"), **details)
            if mutates:
                failed_write(command, request, failure)
            raise failure
        if mutates:
            journal("write_completed", requestId=request, command=command, operationId=response.get("operationId"),
                    result=response["data"], state="applying")
        return response["data"]

    def guard(identity):
        return {"craftSessionId": identity["craftSessionId"], "expectedRevision": identity["revision"]}

    def export_mesh(identity):
        result = call("geometry.section", {**guard(identity), "partIds": parts, "frame": payload.get("frame", {"kind": "world"}),
                      "plane": {"origin": [0, 0, 0], "normal": [0, 1, 0]}, "limit": 1,
                      "includeHidden": bool(payload.get("includeHidden", False)), "export": True, "exportMeshes": True})
        if result.get("identity") != identity or result.get("staleAtDelivery") or not result.get("complete"):
            raise NativeFitError("incomplete_native_geometry", "Native fit requires complete same-revision mesh exports", exclusions=result.get("exclusions"))
        directory = result.get("outputDirectory")
        if not directory:
            raise NativeFitError("native_mesh_not_downloaded", "Global CLI must download exported mesh artifacts before fit evaluation")
        path = Path(directory) / "meshes.json"
        if not path.is_file():
            raise NativeFitError("native_mesh_missing", "Geometry export did not contain meshes.json", directory=directory)
        blob = path.read_bytes()
        metadata = next((f for f in result.get("files", []) if f.get("name") == "meshes.json"), {})
        if metadata.get("sha256") != hashlib.sha256(blob).hexdigest() or metadata.get("bytes") != len(blob):
            raise NativeFitError("native_mesh_integrity", "Native mesh artifact does not match the bridge receipt")
        mesh = json.loads(blob.decode("utf-8-sig"))
        if mesh.get("identity") != identity or mesh.get("geometryStamp") != result["geometryStamp"]:
            raise NativeFitError("native_mesh_identity", "Native mesh receipt and exported identity differ")
        exported.update(mesh=mesh, geometryStamp=result["geometryStamp"], receipt=result)
        return dict(exported)

    def snapshot():
        value = call("craft.snapshot", {"includeXml": True})
        current_ids = {part["id"] for part in value["parts"]}
        if not set(parts) <= current_ids:
            raise NativeFitError("fit_scope_changed", "A bound fit part is missing from the current craft")
        geometry = export_mesh(value["identity"])
        value["geometryStamp"] = geometry["geometryStamp"]
        if not initial:
            initial.update(value)
            # Validate the effective native starting values before any write.
        latest.clear(); latest.update(value)
        return value

    def checkpoint(identity):
        # Read all explicit native bindings before checkpoint/apply. Advisory
        # constants cannot stand in for native fields during a physical fit.
        values = read_parameters(plan["parameters"])
        for p in plan["parameters"]:
            if abs(values[p["name"]] - p["value"]) > float(payload.get("parameterTolerance", 1e-6)):
                raise NativeFitError("fit_baseline_changed", "Effective native parameter differs from the frozen plan", parameter=p["name"])
        return call("craft.checkpoint.create", {**guard(identity), "name": "reference-fit " + candidate["candidateHash"][:12]}, True)

    def apply_operations(operations, identity):
        return call("batch.apply", {**guard(identity), "operations": operations}, True)

    def read_parameters(parameters):
        current = call("craft.snapshot", {"includeXml": False})
        if latest and current["identity"] != latest["identity"]:
            raise NativeFitError("state_changed", "Craft changed during fit readback")
        now = {p["id"]: p for p in current["parts"]}
        before = {p["id"]: p for p in initial.get("parts", [])}
        values = {}
        for p in parameters:
            binding = p.get("binding", {}); kind = binding.get("kind")
            if kind == "translation":
                axis = "xyz".index(binding["axis"])
                differences = [now[part]["position"][axis] - before[part]["position"][axis] for part in binding["partIds"]]
                if max(differences) - min(differences) > float(payload.get("parameterTolerance", 1e-6)):
                    raise NativeFitError("native_translation_not_rigid", "Native group positions did not share the candidate translation", parameter=p["name"])
                values[p["name"]] = p["value"] + sum(differences) / len(differences)
            elif kind == "property":
                result = call("properties.get", {"id": binding["partId"], "fields": [binding["propertyId"]]})
                fields = result["parts"][0]["fields"]
                field = next((f for f in fields if f["propertyId"] == binding["propertyId"] and f.get("valueAvailable")), None)
                if result.get("identity") != current["identity"] or field is None or not isinstance(field.get("value"), (int, float)):
                    raise NativeFitError("native_parameter_unavailable", "Fit property readback was missing, stale or nonnumeric", parameter=p["name"])
                values[p["name"]] = field["value"]
            elif kind == "fuselageSection":
                result = call("shape.get", {"id": binding["partId"]})
                configuration = result["shape"].get("configuration", {})
                section = next((s for s in configuration.get("sections", []) if s["index"] == binding["sectionIndex"]), None)
                if result.get("identity") != current["identity"] or section is None:
                    raise NativeFitError("native_parameter_unavailable", "Fit section readback was missing or stale", parameter=p["name"])
                values[p["name"]] = section[binding["field"]]
            else:
                raise NativeFitError("unbound_native_parameter", "Every parameter needs an explicit native binding for fit.apply", parameter=p["name"])
        return values

    def rollback(checkpoint_value, identity):
        return call("craft.rollback", {**guard(identity), "checkpointId": checkpoint_value["id"]}, True)

    return {"snapshot": snapshot, "checkpoint": checkpoint, "apply": apply_operations, "export_mesh": export_mesh,
            "read_parameters": read_parameters, "rollback": rollback, "journalPath": journal_path, "record": journal}
