"""Original-image semantic annotations, EXIF normalization and numbered previews."""
import hashlib
import math
from pathlib import Path


def transform_points(points, matrix, inverse=False):
    import numpy as np
    transform = np.asarray(matrix, dtype=float)
    values = np.asarray(points, dtype=float)
    if transform.shape != (3, 3) or values.ndim != 2 or values.shape[1] != 2 or not np.isfinite(transform).all() or not np.isfinite(values).all():
        raise ValueError("image transform must be finite 3x3 and points Nx2")
    if abs(np.linalg.det(transform)) < 1e-12:
        raise ValueError("image transform is singular")
    if inverse:
        transform = np.linalg.inv(transform)
    homogeneous = np.column_stack((values, np.ones(len(values)))) @ transform.T
    if (abs(homogeneous[:, 2]) < 1e-12).any():
        raise ValueError("image point maps to infinity")
    return (homogeneous[:, :2] / homogeneous[:, 2:]).tolist()


def normalize_image(payload):
    from PIL import Image, ImageOps
    path = Path(payload["path"]).expanduser().resolve()
    output = Path(payload["outputPath"]).expanduser().resolve()
    if path == output:
        raise ValueError("normalized image must preserve the original file")
    with Image.open(path) as original:
        width, height = original.size
        orientation = int(original.getexif().get(274, 1))
        transforms = {
            1: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            2: [[-1, 0, width - 1], [0, 1, 0], [0, 0, 1]],
            3: [[-1, 0, width - 1], [0, -1, height - 1], [0, 0, 1]],
            4: [[1, 0, 0], [0, -1, height - 1], [0, 0, 1]],
            5: [[0, 1, 0], [1, 0, 0], [0, 0, 1]],
            6: [[0, -1, height - 1], [1, 0, 0], [0, 0, 1]],
            7: [[0, -1, height - 1], [-1, 0, width - 1], [0, 0, 1]],
            8: [[0, 1, 0], [-1, 0, width - 1], [0, 0, 1]],
        }
        normalized = ImageOps.exif_transpose(original).convert("RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        normalized.save(output)
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "originalSize": [width, height], "normalizedSize": list(normalized.size),
                "exifOrientation": orientation, "originalToNormalized": transforms.get(orientation, transforms[1]),
                "normalizedPath": str(output), "coordinateConvention": "pixel centers, original unrotated file coordinates"}


def annotate(payload):
    from PIL import Image, ImageDraw
    path = Path(payload["imagePath"]).expanduser().resolve()
    output = Path(payload["outputPath"]).expanduser().resolve()
    if path == output:
        raise ValueError("annotation preview cannot overwrite the original image")
    items = payload.get("annotations", [])
    if not isinstance(items, list) or len(items) > 10000:
        raise ValueError("annotations must be an array of at most 10000 items")
    matrix = payload.get("originalToPreview", [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    with Image.open(path) as source:
        image = source.convert("RGB")
    width, height = payload.get("originalSize", image.size)
    draw = ImageDraw.Draw(image)
    identities, semantic, report = set(), set(), []
    for number, item in enumerate(items, 1):
        identity = item.get("id")
        kind = item.get("kind")
        points = item.get("points", [])
        if not isinstance(identity, str) or not identity or identity in identities:
            raise ValueError("annotation IDs must be unique nonempty strings")
        if kind not in ("point", "polyline", "region") or len(points) < {"point": 1, "polyline": 2, "region": 3}.get(kind, 1) or (kind == "point" and len(points) != 1):
            raise ValueError("invalid annotation kind/point count")
        if any(len(p) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in p) or not 0 <= p[0] < width or not 0 <= p[1] < height for p in points):
            raise ValueError("annotation coordinates must lie in original image bounds")
        visibility = item.get("visibility", "visible")
        status = item.get("status", "measured")
        if visibility not in ("visible", "occluded", "unknown", "ignored") or status not in ("measured", "inferred", "unconstrained"):
            raise ValueError("invalid annotation visibility/status")
        uncertainty = item.get("uncertaintyPx")
        if uncertainty is not None and (not isinstance(uncertainty, (int, float)) or not math.isfinite(uncertainty) or uncertainty < 0):
            raise ValueError("uncertaintyPx must be nonnegative")
        identities.add(identity)
        if item.get("semanticId"):
            if item["semanticId"] in semantic:
                raise ValueError("semanticId must be unique within one image")
            semantic.add(item["semanticId"])
        mapped = [tuple(p) for p in transform_points(points, matrix)]
        color = (255, 70, 30) if visibility == "visible" else (255, 180, 20)
        if kind == "region":
            draw.line(mapped + [mapped[0]], fill=color, width=2)
        elif kind == "polyline":
            draw.line(mapped, fill=color, width=2)
        for x, y in mapped:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=color, width=2)
        x, y = mapped[0]
        text = str(number)
        box = draw.textbbox((x + 5, y + 3), text)
        draw.rectangle(box, fill=(0, 0, 0))
        draw.text((x + 5, y + 3), text, fill=(255, 255, 255))
        report.append({**item, "number": number, "visibility": visibility, "status": status, "previewPoints": [list(p) for p in mapped]})
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return {"annotationSchemaVersion": 1, "sourceId": payload.get("sourceId"), "annotations": report,
            "originalToPreview": matrix, "previewPath": str(output), "coordinateSpace": "original_image_pixels",
            "evidence": {"measured": sum(x["status"] == "measured" for x in report),
                         "inferred": sum(x["status"] == "inferred" for x in report),
                         "unconstrained": sum(x["status"] == "unconstrained" for x in report)}}


def constraints(payload):
    """Check explicit semantic relations. Unconstrained/occluded evidence stays missing."""
    import numpy as np
    points = payload.get("points", {})
    items = payload.get("constraints", [])
    if not isinstance(points, dict) or not isinstance(items, list):
        raise ValueError("constraints requires points object and constraints array")
    results = []
    for item in items:
        keys = item.get("points", [])
        kind = item.get("kind")
        values, missing = [], []
        for key in keys:
            record = points.get(key)
            if record is None or isinstance(record, dict) and (record.get("status") == "unconstrained" or record.get("visibility") in ("occluded", "unknown", "ignored")):
                missing.append(key); continue
            value = record.get("position") if isinstance(record, dict) else record
            value = np.asarray(value, dtype=float)
            if value.ndim != 1 or len(value) not in (2, 3) or not np.isfinite(value).all():
                raise ValueError("constraint points must be finite 2D/3D positions")
            values.append(value)
        result = {"id": item.get("id"), "kind": kind, "status": "missing_evidence", "value": None, "residual": None}
        if missing:
            result["missingPoints"] = missing; results.append(result); continue
        if len({len(p) for p in values}) != 1:
            raise ValueError("constraint points must share coordinate dimension")
        expected_count = {"distance": 2, "angle": 3, "parallel": 4, "perpendicular": 4, "equalLength": 4, "symmetry": 2}.get(kind)
        if expected_count is None or len(values) != expected_count:
            raise ValueError("unsupported constraint kind or point count")
        unit = item.get("unit", payload.get("unit", "px"))
        if kind == "distance":
            value = float(np.linalg.norm(values[0] - values[1])); target = float(item["target"])
        elif kind in ("angle", "parallel", "perpendicular"):
            a, b = ((values[0] - values[1], values[2] - values[1]) if kind == "angle" else
                    (values[1] - values[0], values[3] - values[2]))
            if min(np.linalg.norm(a), np.linalg.norm(b)) < 1e-12:
                result["status"] = "degenerate"; results.append(result); continue
            angle = float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1))))
            value = min(angle, 180 - angle) if kind == "parallel" else angle
            target = float(item.get("target", 90 if kind == "perpendicular" else 0)); unit = "deg"
        elif kind == "equalLength":
            value = float(np.linalg.norm(values[1] - values[0]) - np.linalg.norm(values[3] - values[2])); target = 0.
        else:
            plane = item["plane"]
            normal = np.asarray(plane["normal"], dtype=float); origin = np.asarray(plane["point"], dtype=float)
            if normal.shape != values[0].shape or origin.shape != normal.shape or not np.isfinite(normal).all() or np.linalg.norm(normal) < 1e-12:
                raise ValueError("symmetry plane must match point dimension")
            normal /= np.linalg.norm(normal)
            reflected = values[0] - 2 * ((values[0] - origin) @ normal) * normal
            value = float(np.linalg.norm(reflected - values[1])); target = 0.
        tolerance = float(item.get("tolerance", 0.))
        if not math.isfinite(tolerance) or tolerance < 0 or not math.isfinite(target):
            raise ValueError("constraint target/tolerance must be finite and tolerance nonnegative")
        residual = abs(value - target)
        result.update(status="pass" if residual <= tolerance else "fail", value=value, residual=residual,
                      target=target, tolerance=tolerance, unit=unit)
        results.append(result)
    return {"constraints": results, "evaluationStatus": "fail" if any(x["status"] == "fail" for x in results) else
            "incomplete" if not results or any(x["status"] != "pass" for x in results) else "pass"}
