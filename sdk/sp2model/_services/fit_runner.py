"""Immutable fit plans, proxy gating and a guarded native apply/readback loop."""
import hashlib
import json
import math

from .fit_parameters import freeze_plan, check_plan, validate_proxy, native_operations


def plan(payload):
    frozen = freeze_plan(payload)
    proxy = validate_proxy(frozen["proxyCalibration"], frozen["parameters"], frozen["gameVersion"], frozen["shapeFamily"])
    return {"plan": frozen, "proxyValidation": proxy, "status": "planned",
            "precisionStatus": "eligible_for_native_validation" if proxy["valid"] else "advisory_only",
            "nativeAcceptanceProven": False}


def evaluate(payload):
    from .fit_optimizer import optimize
    frozen = check_plan(payload["plan"]) if "plan" in payload else freeze_plan(payload)
    proxy = validate_proxy(frozen["proxyCalibration"], frozen["parameters"], frozen["gameVersion"], frozen["shapeFamily"])
    if frozen["requireNativePrecision"] and not proxy["valid"]:
        return {"planHash": frozen["planHash"], "stopReason": "proxy_invalid", "proxyValidation": proxy,
                "candidates": [], "best": None, "operations": [], "acceptanceStatus": "incomplete", "nativeAcceptanceProven": False}
    result = optimize(frozen["parameters"], frozen["model"], frozen["budget"], frozen["tolerances"],
                      float(payload.get("robustScale", 1.)), float(payload.get("regularization", 0.)))
    operations = native_operations(frozen["parameters"], result["best"]["values"])
    locked = set(frozen.get("frozenPartIds", []))
    for operation in operations:
        affected = operation.get("partIds", [operation.get("partId")])
        if locked.intersection(affected):
            raise ValueError("fit candidate affects a frozen part")
    result.update(planHash=frozen["planHash"], proxyValidation=proxy, operations=operations,
                  acceptanceStatus="pending_native_validation" if operations else "advisory_only", nativeAcceptanceProven=False)
    result["candidateHash"] = _candidate_hash(frozen["planHash"], result["best"]["values"], operations)
    return result


def _candidate_hash(plan_hash, values, operations):
    return hashlib.sha256(json.dumps({"planHash": plan_hash, "values": values, "operations": operations},
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_candidate(frozen, candidate):
    if not candidate.get("best"):
        raise ValueError("fit candidate is missing its best parameter values")
    values = candidate["best"]["values"]
    if set(values) != {p["name"] for p in frozen["parameters"]}:
        raise ValueError("fit candidate parameter names differ from the immutable plan")
    for p in frozen["parameters"]:
        value = values[p["name"]]
        if type(value) not in (int, float) or not math.isfinite(value) or not p["min"] <= value <= p["max"] or p["frozen"] and value != p["value"]:
            raise ValueError("fit candidate violates a frozen parameter or parameter domain")
    operations = native_operations(frozen["parameters"], values)
    if operations != candidate.get("operations") or candidate.get("planHash") != frozen["planHash"] or candidate.get("candidateHash") != _candidate_hash(frozen["planHash"], values, operations):
        raise ValueError("fit candidate operations do not match the immutable parameter bindings")
    for operation in operations:
        if set(operation.get("partIds", [operation.get("partId")])).intersection(frozen.get("frozenPartIds", [])):
            raise ValueError("fit candidate affects a frozen part")
    return candidate


def verify(payload):
    frozen = check_plan(payload["plan"])
    candidate = validate_candidate(frozen, payload["candidate"])
    comparison = payload.get("comparison", {})
    native = payload.get("nativeValidation", {})
    failures = []
    identity = native.get("actualIdentity")
    baseline = frozen.get("identity")
    if not identity or not baseline or identity.get("craftSessionId") != baseline.get("craftSessionId") or identity.get("revision", 0) <= baseline.get("revision", 0):
        failures.append("native_identity_or_revision_unproven")
    if not native.get("geometryStamp"):
        failures.append("native_geometry_stamp_missing")
    if comparison.get("actualIdentity") != identity or comparison.get("geometryStamp") != native.get("geometryStamp"):
        failures.append("comparison_native_identity_mismatch")
    if comparison.get("evaluationStatus") != "pass":
        failures.append("actual_geometry_tolerance_not_met")
    values = native.get("actualParameterValues", {})
    parameter_tolerance = float(payload.get("parameterTolerance", 1e-6))
    if not math.isfinite(parameter_tolerance) or parameter_tolerance < 0:
        raise ValueError("parameterTolerance must be finite and nonnegative")
    for p in frozen["parameters"]:
        target = p["value"] if p["frozen"] else candidate["best"]["values"][p["name"]]
        measured = values.get(p["name"])
        if not isinstance(measured, (int, float)) or not math.isfinite(measured) or abs(measured - target) > parameter_tolerance:
            failures.append("frozen_parameter_changed" if p["frozen"] else "native_parameter_readback_mismatch")
    if frozen["requireNativePrecision"]:
        proxy = payload.get("proxyComparison", {})
        allowed = frozen["proxyCalibration"]["errorBudget"]
        if proxy.get("evaluationStatus") != "pass" or proxy.get("maxError") is None or proxy["maxError"] > allowed:
            failures.append("proxy_invalid")
    if payload.get("requireIndependentView", True):
        evidence = native.get("independentViewEvidence", [])
        from .projection import camera_spec
        primary_cameras = [camera_spec(camera) for camera in (
            frozen["model"].get("camera"), (frozen.get("validation") or {}).get("camera")) if camera]
        def independent_camera(camera):
            if not camera:
                return False
            candidate_camera = camera_spec(camera)
            for primary in primary_cameras:
                if candidate_camera["cameraHash"] == primary["cameraHash"]:
                    return False
                a, b = primary["worldToCamera"], candidate_camera["worldToCamera"]
                # Changing zoom, principal point, clipping, or rolling an
                # orthographic image cannot create another physical viewpoint.
                same_direction = sum(a[2][i] * b[2][i] for i in range(3)) > 1 - 1e-8
                if primary["projection"] == candidate_camera["projection"] == "orthographic" and same_direction:
                    return False
                if primary["projection"] == candidate_camera["projection"] == "perspective":
                    center_a = [-sum(a[j][i] * a[j][3] for j in range(3)) for i in range(3)]
                    center_b = [-sum(b[j][i] * b[j][3] for j in range(3)) for i in range(3)]
                    if same_direction and sum((x - y) ** 2 for x, y in zip(center_a, center_b)) < 1e-16:
                        return False
            return True
        valid_views = [v for v in evidence if v.get("evaluationStatus") == "pass" and v.get("actualIdentity") == identity and
                       v.get("geometryStamp") == native.get("geometryStamp") and v.get("cameraFrozen") and
                       independent_camera(v.get("camera")) and
                       any(r.get("metrics", {}).get("silhouette", {}).get("status") == "measured" and
                           any(c.get("metric", "").startswith("silhouette.") for c in r.get("checks", [])) for r in v.get("regions", []))]
        if not valid_views:
            failures.append("independent_view_missing")
    passed = not failures
    return {"acceptanceStatus": "verified" if passed else "incomplete", "nativeAcceptanceProven": passed,
            "stopReason": "tolerance_met" if passed else "proxy_invalid" if "proxy_invalid" in failures else "native_validation_incomplete",
            "failures": sorted(set(failures)), "actualIdentity": identity, "geometryStamp": native.get("geometryStamp")}


def apply(payload, live, worker_call):
    """Host-only callback protocol; the isolated worker never writes to a game.

    live is a mapping of callables snapshot(), checkpoint(identity),
    apply(operations, identity), export_mesh(identity), read_parameters(parameters),
    and optional rollback(checkpoint, identity). Snapshot/readback must use the
    public bridge and current native mesh. All callbacks return their data object.
    payload.validation is a reference.compare payload without actualMesh/identity.
    """
    frozen = check_plan(payload["plan"])
    candidate = validate_candidate(frozen, payload["candidate"])
    validation = frozen.get("validation")
    if not validation or payload.get("validation", validation) != validation:
        raise ValueError("native apply requires validation targets/tolerances frozen in fit.plan")
    before = live["snapshot"]()
    identity = before["identity"]
    if identity != frozen.get("identity") or frozen.get("geometryStamp") and before.get("geometryStamp") != frozen["geometryStamp"]:
        return {"acceptanceStatus": "incomplete", "stopReason": "state_changed", "nativeAcceptanceProven": False}
    if candidate.get("stopReason") in ("underconstrained", "proxy_invalid") or not candidate.get("operations"):
        return {"acceptanceStatus": "incomplete", "stopReason": candidate.get("stopReason", "no_candidate_operations"), "nativeAcceptanceProven": False}
    baseline_export = live["export_mesh"](identity)
    compare_before = dict(validation)
    compare_before.update(actualMesh=baseline_export["mesh"], actualIdentity=identity, geometryStamp=baseline_export["geometryStamp"])
    baseline_comparison = worker_call("reference.compare", compare_before)
    checkpoint = live["checkpoint"](identity)
    # A result-unknown exception is intentionally not replayed or automatically
    # rolled back; the host journals the operation ID before attempting recovery.
    receipt = live["apply"](candidate["operations"], identity)
    after = live["snapshot"]()
    if after["identity"] != receipt["identity"]:
        return {"acceptanceStatus": "incomplete", "stopReason": "state_changed", "checkpoint": checkpoint,
                "receipt": receipt, "nativeAcceptanceProven": False}
    exported = live["export_mesh"](after["identity"])
    validation = dict(validation)
    holdouts = validation.pop("independentViews", [])
    validation.update(actualMesh=exported["mesh"], actualIdentity=after["identity"], geometryStamp=exported["geometryStamp"])
    comparison = worker_call("reference.compare", validation)
    independent = []
    for view in holdouts:
        view_payload = dict(view)
        view_payload.setdefault("referenceMesh", validation.get("referenceMesh"))
        view_payload.update(actualMesh=exported["mesh"], actualIdentity=after["identity"], geometryStamp=exported["geometryStamp"])
        independent.append(worker_call("reference.compare", view_payload))
    native = {"actualIdentity": after["identity"], "geometryStamp": exported["geometryStamp"],
              "actualParameterValues": live["read_parameters"](frozen["parameters"]),
              "independentViewEvidence": independent}
    proxy_comparison = worker_call("fit.proxyCompare", {"plan": frozen, "candidate": candidate, "actualMesh": exported["mesh"]}) if frozen["requireNativePrecision"] else None
    verified = worker_call("fit.verify", {"plan": frozen, "candidate": candidate, "comparison": comparison, "nativeValidation": native,
                       "proxyComparison": proxy_comparison, "requireIndependentView": payload.get("requireIndependentView", True),
                       "parameterTolerance": payload.get("parameterTolerance", 1e-6)})
    # Passing a loose target must not retain a candidate that worsened a measured
    # regional maximum. Compare the same immutable metric definitions both times.
    before_values = {(r["id"], name): metric.get("max", metric.get("residual"))
                     for r in baseline_comparison.get("regions", []) for name, metric in r.get("metrics", {}).items()}
    worse = []
    for region in comparison.get("regions", []):
        for name, metric in region.get("metrics", {}).items():
            old, new = before_values.get((region["id"], name)), metric.get("max", metric.get("residual"))
            if isinstance(old, (int, float)) and isinstance(new, (int, float)) and new > old + float(payload.get("degradationTolerance", 1e-8)):
                worse.append(region["id"] + "." + name)
    if worse:
        verified.update(nativeAcceptanceProven=False, acceptanceStatus="incomplete", stopReason="candidate_worsened", degradedMetrics=worse)
    verified.update(checkpoint=checkpoint, receipt=receipt, comparison=comparison, baselineComparison=baseline_comparison,
                    independentViewEvidence=independent, proxyComparison=proxy_comparison, journalPath=live.get("journalPath"))
    if not verified["nativeAcceptanceProven"] and payload.get("rollbackOnFailure", True) and "rollback" in live:
        current = live["snapshot"]()
        if current["identity"] != after["identity"]:
            verified["stopReason"] = "state_changed"
        else:
            verified["rollback"] = live["rollback"](checkpoint, current["identity"])
    if "record" in live:
        live["record"]("fit_verified", acceptanceStatus=verified["acceptanceStatus"], stopReason=verified["stopReason"],
                       identity=verified.get("actualIdentity"), state="finalized" if verified["nativeAcceptanceProven"] else
                       "restored" if "rollback" in verified else "reconcileRequired")
    return verified


def proxy_compare(payload):
    """Validate the implemented rigid-translation proxy against native mesh readback."""
    import numpy as np
    from .projection import normalize_mesh
    from .quality_metrics import surface_metrics
    frozen = check_plan(payload["plan"])
    candidate = payload["candidate"]
    model = frozen["model"]
    if model.get("kind") not in ("translation_points", "orthographic_translation_points", "perspective_translation_points") or not model.get("mesh"):
        return {"evaluationStatus": "insufficient_evidence", "maxError": None, "reason": "native_geometry_proxy_not_implemented_for_model"}
    if candidate.get("candidateHash") != _candidate_hash(frozen["planHash"], candidate["best"]["values"], candidate["operations"]):
        raise ValueError("proxy candidate hash mismatch")
    vertices, faces, identities = normalize_mesh(model["mesh"])
    displacement = np.zeros(3)
    for p in frozen["parameters"]:
        axis = model["parameterAxes"][p["name"]]
        displacement["xyz".index(axis)] = candidate["best"]["values"][p["name"]] - p["value"]
    predicted = {"vertices": (vertices + displacement).tolist(), "triangles": faces.tolist(), "faceObjectIds": identities}
    metrics = surface_metrics(predicted, payload["actualMesh"], int(model.get("proxySampleCount", 3000)), model.get("proxySampleSpacing"))
    allowed = frozen.get("proxyCalibration", {}).get("errorBudget")
    status = "pass" if metrics["status"] == "measured" and allowed is not None and metrics["max"] <= allowed else "fail"
    return {"evaluationStatus": status, "maxError": metrics["max"], "allowedError": allowed, "surface": metrics,
            "proxyKind": "rigid_translation_of_native_baseline_mesh"}
