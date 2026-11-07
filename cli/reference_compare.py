"""Fixed-camera, regional image and 3D comparisons with explicit missing evidence."""
from pathlib import Path

from projection import camera_spec, normalize_mesh, project_points
from reference_render import render_mesh
from quality_metrics import mask_metrics, line_metrics, surface_metrics, section_metrics


def _mask(value, shape):
    import numpy as np
    if isinstance(value, str):
        from PIL import Image
        with Image.open(value) as image:
            values = np.asarray(image.convert("L")) > 0
    else:
        values = np.asarray(value, dtype=bool)
    if values.shape != shape:
        raise ValueError("image mask dimensions must exactly match the frozen camera")
    return values


def select_mesh(mesh, identities=None):
    import numpy as np
    vertices, faces, ids = normalize_mesh(mesh)
    if identities is not None:
        wanted = {(type(i).__name__, i) for i in identities}
        chosen = [index for index, value in enumerate(ids) if (type(value).__name__, value) in wanted]
        faces = faces[chosen]
        ids = [ids[index] for index in chosen]
    return {"vertices": vertices.tolist(), "triangles": faces.tolist(), "faceObjectIds": ids}


def _semantic_metrics(features, camera):
    import numpy as np
    rows = []
    for feature in features:
        row = {"semanticId": feature.get("semanticId"), "status": "missing_evidence", "unit": "px", "residual": None}
        if feature.get("visibility", "visible") != "visible" or feature.get("status", "measured") == "unconstrained":
            row["reason"] = "unobservable_feature"; rows.append(row); continue
        reference = feature.get("referencePoints")
        actual = feature.get("actualPoints")
        if feature.get("actualWorldPoints") is not None:
            if camera is None:
                row["reason"] = "camera_missing"; rows.append(row); continue
            projected = project_points(feature["actualWorldPoints"], camera)["points"]
            if not all(p["visible"] for p in projected):
                row["reason"] = "feature_clipped_or_outside_image"; rows.append(row); continue
            actual = [p["pixel"] for p in projected]
        if reference is None or actual is None:
            row["reason"] = "correspondence_missing"; rows.append(row); continue
        if feature.get("kind", "point") == "point":
            r, a = np.asarray(reference, dtype=float), np.asarray(actual, dtype=float)
            if r.shape == (1, 2):
                r, a = r[0], a[0]
            if r.shape != (2,) or a.shape != (2,) or not np.isfinite(r).all() or not np.isfinite(a).all():
                raise ValueError("semantic point must contain corresponding finite 2D coordinates")
            row.update(status="measured", residual=float(np.linalg.norm(r - a)), referencePoint=r.tolist(), actualPoint=a.tolist())
        else:
            row.update(line_metrics(reference, actual, feature.get("sampleSpacingPx", 1.)), kind="polyline")
        rows.append(row)
    return rows


def _assess(metrics, tolerance):
    """No tolerance or no evidence can never become a zero-error pass."""
    if not metrics or any(item.get("status") not in ("measured", "pass") for item in metrics.values() if isinstance(item, dict)):
        return "insufficient_evidence", []
    if not tolerance:
        return "tolerance_not_configured", []
    checks = []
    for name, rules in tolerance.items():
        measured = metrics.get(name)
        if not isinstance(measured, dict):
            checks.append({"metric": name, "status": "missing_evidence"}); continue
        for key, target in rules.items():
            value = measured.get(key)
            if value is None:
                status = "missing_evidence"
            else:
                minimum = key.lower().endswith("min") or key == "iou"
                status = "pass" if (value >= target if minimum else value <= target) else "fail"
            checks.append({"metric": name + "." + key, "value": value, "target": target, "status": status})
    if not checks or any(c["status"] == "missing_evidence" for c in checks):
        return "insufficient_evidence", checks
    return ("pass" if all(c["status"] == "pass" for c in checks) else "needs_revision"), checks


def compare(payload):
    import numpy as np
    actual = payload["actualMesh"]
    reference = payload.get("referenceMesh")
    camera = camera_spec(payload["camera"]) if payload.get("camera") else None
    expected_hash = payload.get("expectedCameraHash")
    if expected_hash and (not camera or expected_hash != camera["cameraHash"]):
        return {"evaluationStatus": "camera_changed", "regions": [], "reason": "frozen_camera_hash_mismatch"}
    frozen = bool(payload.get("cameraFrozen", False))
    regions = payload.get("regions", [{"id": "all", "referenceIds": None, "actualIds": None}])
    if not isinstance(regions, list) or len(regions) > 1000:
        raise ValueError("regions must be an array of at most 1000 items")
    reports, overlays = [], []
    for region in regions:
        if region.get("excluded"):
            reports.append({"id": region["id"], "evaluationStatus": "excluded", "reason": region.get("reason", "explicitly_excluded"), "metrics": {}})
            continue
        amesh = select_mesh(actual, region.get("actualIds"))
        rmesh = select_mesh(reference, region.get("referenceIds")) if reference is not None else None
        metrics = {}
        if rmesh is not None and payload.get("compareSurface", True):
            metrics["surface"] = surface_metrics(rmesh, amesh, int(payload.get("sampleCount", 3000)), payload.get("sampleSpacing"))
        for section in region.get("sections", payload.get("sections", [])):
            if rmesh is None:
                metrics["section." + section["id"]] = {"status": "missing_evidence", "max": None, "p95": None, "reason": "reference_mesh_missing"}
            else:
                metrics["section." + section["id"]] = section_metrics(rmesh, amesh, section["plane"], section.get("sampleSpacing", .1))
        if camera is not None:
            act_render = render_mesh(amesh, camera)
            shape = act_render["mask"].shape
            ref_value = region.get("referenceMask", payload.get("referenceMask"))
            ref_mask = _mask(ref_value, shape) if ref_value is not None else (render_mesh(rmesh, camera)["mask"] if rmesh is not None else None)
            if ref_mask is None:
                metrics["silhouette"] = {"status": "missing_evidence", "p95": None, "max": None, "iou": None, "reason": "reference_mask_missing"}
            else:
                valid = np.ones(shape, dtype=bool)
                ignore = region.get("ignoreMask", payload.get("ignoreMask"))
                if ignore is not None:
                    valid &= ~_mask(ignore, shape)
                if region.get("regionMask") is not None:
                    valid &= _mask(region["regionMask"], shape)
                metrics["silhouette"] = mask_metrics(ref_mask, act_render["mask"], valid)
                overlays.append((region["id"], ref_mask, act_render["mask"], valid))
        features = _semantic_metrics(region.get("features", payload.get("features", [])), camera)
        for index, feature in enumerate(features):
            metrics["feature." + str(feature.get("semanticId", index))] = feature
        status, checks = _assess(metrics, region.get("tolerances", payload.get("tolerances", {})))
        if camera is not None and not frozen and status == "pass":
            status = "insufficient_evidence"
        reports.append({"id": region["id"], "evaluationStatus": status, "metrics": metrics, "checks": checks})
    active = [row for row in reports if row["evaluationStatus"] != "excluded"]
    status = "pass" if active and all(r["evaluationStatus"] == "pass" for r in active) else (
        "needs_revision" if any(r["evaluationStatus"] == "needs_revision" for r in active) else "insufficient_evidence")
    result = {"schemaVersion": 1, "evaluationStatus": status, "regions": reports, "camera": camera,
              "cameraFrozen": frozen, "referenceVersion": payload.get("referenceVersion"),
              "actualIdentity": payload.get("actualIdentity"), "geometryStamp": payload.get("geometryStamp"),
              "evidenceScope": "discrete_samples_and_declared_views", "unobserved": payload.get("unobserved", []),
              "nativeAcceptanceProven": False}
    if payload.get("outputDirectory"):
        from PIL import Image
        directory = Path(payload["outputDirectory"]).expanduser().resolve(); directory.mkdir(parents=True, exist_ok=True)
        files = []
        for index, (identity, ref, act, valid) in enumerate(overlays):
            pixels = np.full((*ref.shape, 3), 245, dtype=np.uint8)
            pixels[ref & valid] = [230, 60, 60]; pixels[act & valid] = [40, 100, 235]
            pixels[ref & act & valid] = [85, 175, 100]; pixels[~valid] = [180, 180, 180]
            path = directory / ("overlay-" + str(index + 1) + ".png")
            Image.fromarray(pixels).save(path); files.append({"regionId": identity, "path": str(path)})
        result["overlays"] = files
    return result
