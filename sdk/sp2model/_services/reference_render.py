"""Deterministic CPU triangle rasterization with clipping, z, source IDs and masks."""
import json
from pathlib import Path

from .projection import camera_spec, camera_points, pixels_from_camera, normalize_mesh


def _clip_z(polygon, value, keep_greater):
    if not len(polygon):
        return []
    output = []
    previous = polygon[-1]
    previous_inside = previous[2] >= value if keep_greater else previous[2] <= value
    for current in polygon:
        inside = current[2] >= value if keep_greater else current[2] <= value
        if inside != previous_inside:
            t = (value - previous[2]) / (current[2] - previous[2])
            output.append(previous + t * (current - previous))
        if inside:
            output.append(current)
        previous, previous_inside = current, inside
    return output


def render_mesh(mesh, camera):
    import numpy as np
    camera = camera_spec(camera)
    vertices, faces, source_ids = normalize_mesh(mesh)
    points = camera_points(vertices, camera)
    width, height = camera["width"], camera["height"]
    depth = np.full((height, width), np.inf, dtype=np.float32)
    ids = np.zeros((height, width), dtype=np.int32)
    mapping, encoded = [], {}
    for identity in source_ids:
        key = (type(identity).__name__, identity)
        if key not in encoded:
            encoded[key] = len(mapping) + 1
            mapping.append({"value": len(mapping) + 1, "sourceId": identity})
    skipped, clipped = 0, 0
    for face, identity in zip(faces, source_ids):
        triangle = points[face]
        if (triangle[:, 2] < camera["near"]).any() or (triangle[:, 2] > camera["far"]).any():
            clipped += 1
        polygon = _clip_z(triangle, camera["near"], True)
        polygon = _clip_z(polygon, camera["far"], False)
        if len(polygon) < 3:
            skipped += 1
            continue
        object_id = encoded[(type(identity).__name__, identity)]
        for index in range(1, len(polygon) - 1):
            tri = np.asarray([polygon[0], polygon[index], polygon[index + 1]])
            pixels = pixels_from_camera(tri, camera)
            xmin = max(0, int(np.ceil(pixels[:, 0].min() - .5)))
            xmax = min(width - 1, int(np.floor(pixels[:, 0].max() - .5)))
            ymin = max(0, int(np.ceil(pixels[:, 1].min() - .5)))
            ymax = min(height - 1, int(np.floor(pixels[:, 1].max() - .5)))
            if xmin > xmax or ymin > ymax:
                continue
            a, b, c = pixels
            denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(denominator) < 1e-12:
                continue
            # Rows are chunked to bound temporary allocations for very large triangles.
            for row in range(ymin, ymax + 1, 128):
                end = min(ymax + 1, row + 128)
                xx, yy = np.meshgrid(np.arange(xmin, xmax + 1) + .5, np.arange(row, end) + .5)
                wa = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / denominator
                wb = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / denominator
                wc = 1 - wa - wb
                inside = (wa >= -1e-10) & (wb >= -1e-10) & (wc >= -1e-10)
                if camera["projection"] == "perspective":
                    z = 1 / (wa / tri[0, 2] + wb / tri[1, 2] + wc / tri[2, 2])
                else:
                    z = wa * tri[0, 2] + wb * tri[1, 2] + wc * tri[2, 2]
                target = depth[row:end, xmin:xmax + 1]
                valid = inside & (z < target - 1e-7)
                target[valid] = z[valid]
                ids[row:end, xmin:xmax + 1][valid] = object_id
    return {"camera": camera, "depth": depth, "ids": ids, "mask": ids != 0, "idMapping": mapping,
            "triangleCount": len(faces), "clippedTriangleCount": clipped, "outsideDepthTriangleCount": skipped}


def write_render(rendered, directory):
    import numpy as np
    from PIL import Image
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    mask = rendered["mask"]
    ids = rendered["ids"]
    depth = rendered["depth"].copy()
    depth[~mask] = np.nan
    Image.fromarray((mask * 255).astype("uint8")).save(root / "mask.png")
    np.save(root / "depth.npy", depth, allow_pickle=False)
    np.save(root / "object-id.npy", ids, allow_pickle=False)
    preview = np.full((*mask.shape, 3), 245, dtype=np.uint8)
    for item in rendered["idMapping"]:
        value = item["value"]
        preview[ids == value] = [(value * 67) % 180 + 40, (value * 107) % 180 + 40, (value * 139) % 180 + 40]
    Image.fromarray(preview).save(root / "render.png")
    metadata = {key: value for key, value in rendered.items() if key not in ("depth", "ids", "mask")}
    (root / "render.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"mask": str(root / "mask.png"), "depth": str(root / "depth.npy"), "objectIds": str(root / "object-id.npy"),
            "preview": str(root / "render.png"), "metadata": str(root / "render.json")}


def render(payload):
    result = render_mesh(payload["mesh"], payload["camera"])
    report = {key: value for key, value in result.items() if key not in ("depth", "ids", "mask")}
    report["visiblePixelCount"] = int(result["mask"].sum())
    report["depthUnit"] = payload.get("units", "m")
    if payload.get("outputDirectory"):
        report["files"] = write_render(result, payload["outputDirectory"])
    if payload.get("includeBuffers", not payload.get("outputDirectory")):
        if result["mask"].size > 1048576:
            raise ValueError("inline buffers exceed one million pixels; use outputDirectory")
        report["mask"] = result["mask"].tolist()
        report["objectIds"] = result["ids"].tolist()
        report["depth"] = [[float(z) if visible else None for z, visible in zip(row, visible_row)]
                           for row, visible_row in zip(result["depth"], result["mask"])]
    return report
