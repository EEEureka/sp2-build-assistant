"""Fixed cameras and indexed mesh normalization. Numeric imports stay in the worker."""
import hashlib
import json
import math


def camera_spec(camera):
    import numpy as np
    if not isinstance(camera, dict):
        raise ValueError("camera must be an object")
    width, height = camera.get("width"), camera.get("height")
    if type(width) is not int or type(height) is not int or not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > 8388608:
        raise ValueError("camera dimensions must be 1..4096 and <= 8388608 pixels")
    kind = camera.get("projection")
    if kind not in ("orthographic", "perspective"):
        raise ValueError("projection must be orthographic or perspective")
    matrix = np.asarray(camera.get("worldToCamera", np.eye(4)), dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8):
        raise ValueError("worldToCamera must be a finite affine 4x4 matrix")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-5):
        raise ValueError("worldToCamera rotation must be right handed and rigid")
    near, far = float(camera.get("near", .01)), float(camera.get("far", 100000))
    if not math.isfinite(near) or not math.isfinite(far) or not 0 < near < far:
        raise ValueError("camera requires 0 < near < far")
    params = dict(camera.get("intrinsics" if kind == "perspective" else "orthographic", {}))
    xkey, ykey = ("fx", "fy") if kind == "perspective" else ("scaleX", "scaleY")
    if xkey not in params:
        raise ValueError("camera requires " + xkey)
    params[ykey] = params.get(ykey, params[xkey])
    params["cx"], params["cy"] = params.get("cx", width / 2), params.get("cy", height / 2)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in params.values()) or params[xkey] <= 0 or params[ykey] <= 0:
        raise ValueError("camera intrinsics must be finite with positive scale/focal length")
    spec = {"projection": kind, "width": width, "height": height, "near": near, "far": far,
            "worldToCamera": matrix.tolist(), "intrinsics" if kind == "perspective" else "orthographic": params,
            "convention": "+x right, +y up, +z forward; pixels x right/y down"}
    spec["cameraHash"] = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return spec


def camera_points(points, camera):
    import numpy as np
    values = np.asarray(points, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError("points must be finite Nx3")
    matrix = np.asarray(camera["worldToCamera"])
    return values @ matrix[:3, :3].T + matrix[:3, 3]


def pixels_from_camera(points, camera):
    import numpy as np
    points = np.asarray(points, dtype=float)
    params = camera["intrinsics"] if camera["projection"] == "perspective" else camera["orthographic"]
    if camera["projection"] == "perspective":
        with np.errstate(divide="ignore", invalid="ignore"):
            u = params["fx"] * points[:, 0] / points[:, 2] + params["cx"]
            v = -params["fy"] * points[:, 1] / points[:, 2] + params["cy"]
    else:
        u = params["scaleX"] * points[:, 0] + params["cx"]
        v = -params["scaleY"] * points[:, 1] + params["cy"]
    return np.column_stack((u, v))


def project_points(points, camera):
    import numpy as np
    camera = camera_spec(camera)
    transformed = camera_points(points, camera)
    pixels = pixels_from_camera(transformed, camera)
    visible = ((transformed[:, 2] >= camera["near"]) & (transformed[:, 2] <= camera["far"]) &
               (pixels[:, 0] >= 0) & (pixels[:, 0] < camera["width"]) &
               (pixels[:, 1] >= 0) & (pixels[:, 1] < camera["height"]))
    return {"camera": camera, "points": [{"pixel": p.tolist() if np.isfinite(p).all() else None,
             "depth": float(z), "visible": bool(v)} for p, z, v in zip(pixels, transformed[:, 2], visible)]}


def pixel_ray(pixel, camera, plane=None, depth=None):
    import numpy as np
    camera = camera_spec(camera)
    point = np.asarray(pixel, dtype=float)
    if point.shape != (2,) or not np.isfinite(point).all():
        raise ValueError("pixel must be finite [x,y]")
    params = camera["intrinsics"] if camera["projection"] == "perspective" else camera["orthographic"]
    perspective = camera["projection"] == "perspective"
    x = (point[0] - params["cx"]) / params["fx" if perspective else "scaleX"]
    y = -(point[1] - params["cy"]) / params["fy" if perspective else "scaleY"]
    local_origin = np.zeros(3) if perspective else np.array([x, y, 0.])
    local_direction = np.array([x, y, 1.]) if perspective else np.array([0., 0., 1.])
    matrix = np.asarray(camera["worldToCamera"])
    origin = matrix[:3, :3].T @ (local_origin - matrix[:3, 3])
    direction = matrix[:3, :3].T @ local_direction
    direction /= np.linalg.norm(direction)
    result = {"origin": origin.tolist(), "direction": direction.tolist(), "point": None, "status": "ray_only"}
    if depth is not None:
        depth = float(depth)
        if not camera["near"] <= depth <= camera["far"]:
            raise ValueError("depth must lie inside camera near/far")
        local_point = np.array([x * depth, y * depth, depth]) if perspective else np.array([x, y, depth])
        result.update(point=(matrix[:3, :3].T @ (local_point - matrix[:3, 3])).tolist(), status="depth_constrained")
    elif plane is not None:
        normal = np.asarray(plane["normal"], dtype=float)
        anchor = np.asarray(plane["point"], dtype=float)
        if normal.shape != (3,) or anchor.shape != (3,) or not np.isfinite(normal).all() or not np.isfinite(anchor).all() or np.linalg.norm(normal) < 1e-12:
            raise ValueError("plane requires finite point and nonzero normal")
        denominator = float(normal @ direction)
        if abs(denominator) < 1e-10:
            result["status"] = "parallel_to_plane"
        else:
            distance = float(normal @ (anchor - origin)) / denominator
            hit = origin + direction * distance
            z = float(camera_points([hit], camera)[0, 2])
            if camera["near"] <= z <= camera["far"]:
                result.update(point=hit.tolist(), status="plane_constrained")
            else:
                result["status"] = "plane_outside_frustum"
    return result


def normalize_mesh(mesh):
    """Accept OBJ provider meshes and the native indexed_triangles_v1 artifact."""
    import numpy as np
    if isinstance(mesh, str):
        from pathlib import Path
        mesh = json.loads(Path(mesh).read_text(encoding="utf-8-sig"))
    if not isinstance(mesh, dict):
        raise ValueError("mesh must be an object or JSON artifact path")
    vertices, triangles, identifiers = [], [], []
    chunks = mesh.get("meshes", [mesh])
    for chunk in chunks:
        verts = chunk.get("vertices", [])
        indices = chunk.get("triangles", chunk.get("indices", []))
        indices = np.asarray(indices)
        if indices.size == 0:
            continue
        if indices.dtype.kind not in "iu" or indices.size % 3:
            raise ValueError("mesh triangle indices must be integer triples")
        indices = indices.reshape((-1, 3))
        offset = len(vertices)
        if indices.min() < 0 or indices.max() >= len(verts):
            raise ValueError("mesh indices out of range")
        vertices.extend(verts)
        triangles.extend((indices + offset).tolist())
        ids = chunk.get("faceObjectIds", chunk.get("facePartIds"))
        if ids is None:
            ids = [chunk.get("partId", chunk.get("objectId", 1))] * len(indices)
        if len(ids) != len(indices) or any(not isinstance(i, (str, int)) or isinstance(i, bool) for i in ids):
            raise ValueError("faceObjectIds must contain one string/integer per triangle")
        identifiers.extend(ids)
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=int)
    if vertices.size == 0:
        vertices = np.empty((0, 3)); triangles = np.empty((0, 3), dtype=int)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("mesh vertices must be finite Nx3")
    if len(vertices) > 1000000 or len(triangles) > 1000000:
        raise ValueError("mesh exceeds one million vertices/triangles")
    return vertices, triangles, identifiers
