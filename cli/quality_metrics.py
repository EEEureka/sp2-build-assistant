"""Bidirectional sample residuals, silhouettes, exact triangle queries and sections."""
import math

from projection import normalize_mesh


def distance_summary(distances, source=None, destination=None):
    import numpy as np
    values = np.asarray(distances, dtype=float)
    if not len(values):
        return {"status": "missing_evidence", "count": 0, "p95": None, "max": None, "mean": None, "worst": None}
    index = int(np.argmax(values))
    return {"status": "measured", "count": len(values), "p95": float(np.percentile(values, 95)),
            "max": float(values[index]), "mean": float(values.mean()),
            "worst": {"source": None if source is None else list(map(float, source[index])),
                      "destination": None if destination is None else list(map(float, destination[index]))}}


def mask_metrics(reference, actual, valid=None):
    import numpy as np
    from scipy.ndimage import binary_erosion, distance_transform_edt
    reference, actual = np.asarray(reference, dtype=bool), np.asarray(actual, dtype=bool)
    if reference.ndim != 2 or actual.shape != reference.shape:
        raise ValueError("masks must be equally sized 2D arrays")
    valid = np.ones_like(reference) if valid is None else np.asarray(valid, dtype=bool)
    if valid.shape != reference.shape:
        raise ValueError("valid mask dimensions differ")
    # Do not invent a contour along a cropped/ignored ROI edge.
    ref_edge = (reference & ~binary_erosion(reference)) & binary_erosion(valid, border_value=1)
    act_edge = (actual & ~binary_erosion(actual)) & binary_erosion(valid, border_value=1)
    ref, act = reference & valid, actual & valid
    union = int((ref | act).sum()); intersection = int((ref & act).sum())
    report = {"unit": "px", "iou": intersection / union if union else None,
              "referenceAreaPx": int(ref.sum()), "actualAreaPx": int(act.sum()), "validAreaPx": int(valid.sum())}
    if not ref_edge.any() or not act_edge.any():
        missing = distance_summary([])
        report.update(status="missing_evidence", referenceToActual=missing.copy(), actualToReference=missing.copy(),
                      reason="empty_reference_or_actual_contour")
        return report
    da, ia = distance_transform_edt(~act_edge, return_indices=True)
    dr, ir = distance_transform_edt(~ref_edge, return_indices=True)
    ref_indices, act_indices = np.argwhere(ref_edge), np.argwhere(act_edge)
    forward = distance_summary(da[ref_edge], ref_indices[:, ::-1], ia[:, ref_edge].T[:, ::-1])
    reverse = distance_summary(dr[act_edge], act_indices[:, ::-1], ir[:, act_edge].T[:, ::-1])
    report.update(status="measured", referenceToActual=forward, actualToReference=reverse,
                  p95=max(forward["p95"], reverse["p95"]), max=max(forward["max"], reverse["max"]))
    return report


def polyline_samples(points, spacing):
    import numpy as np
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] not in (2, 3) or len(points) < 2 or not np.isfinite(points).all() or not spacing > 0:
        raise ValueError("polyline needs finite Nx2/Nx3 points and positive spacing")
    samples = []
    for a, b in zip(points[:-1], points[1:]):
        count = max(1, int(math.ceil(np.linalg.norm(b - a) / spacing)))
        if count > 100000 or len(samples) + count > 100000:
            raise ValueError("polyline sample budget exceeded")
        samples.extend(a + (b - a) * t for t in np.linspace(0, 1, count, endpoint=False))
    samples.append(points[-1])
    return np.asarray(samples)


def nearest_segments(points, segments):
    import numpy as np
    points, segments = np.asarray(points), np.asarray(segments)
    if not len(points) or not len(segments):
        return np.array([]), np.empty((0, points.shape[-1] if points.ndim else 3))
    result, witnesses = [], []
    a, edge = segments[:, 0], segments[:, 1] - segments[:, 0]
    denom = (edge * edge).sum(axis=1)
    denom = np.maximum(denom, 1e-30)
    for point in points:
        t = np.clip(((point - a) * edge).sum(axis=1) / denom, 0, 1)
        closest = a + t[:, None] * edge
        distance = ((closest - point) ** 2).sum(axis=1)
        index = int(np.argmin(distance)); result.append(math.sqrt(float(distance[index]))); witnesses.append(closest[index])
    return np.asarray(result), np.asarray(witnesses)


def line_metrics(reference, actual, spacing=1., unit="px"):
    import numpy as np
    ref = polyline_samples(reference, spacing); act = polyline_samples(actual, spacing)
    a = np.asarray(actual); r = np.asarray(reference)
    da, wa = nearest_segments(ref, np.stack((a[:-1], a[1:]), axis=1))
    dr, wr = nearest_segments(act, np.stack((r[:-1], r[1:]), axis=1))
    forward, reverse = distance_summary(da, ref, wa), distance_summary(dr, act, wr)
    return {"status": "measured", "unit": unit, "referenceToActual": forward, "actualToReference": reverse,
            "p95": max(forward["p95"], reverse["p95"]), "max": max(forward["max"], reverse["max"]), "sampleSpacing": spacing}


def _closest_triangles(point, triangles):
    """Exact point-to-triangle queries for a small BVH leaf, including degenerate faces."""
    import numpy as np
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    normal = np.cross(ab, ac); n2 = (normal * normal).sum(axis=1)
    scale = ((point - a) * normal).sum(axis=1) / np.maximum(n2, 1e-30)
    projected = point - scale[:, None] * normal
    d00, d01, d11 = (ab * ab).sum(axis=1), (ab * ac).sum(axis=1), (ac * ac).sum(axis=1)
    relative = projected - a
    d20, d21 = (relative * ab).sum(axis=1), (relative * ac).sum(axis=1)
    denominator = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / np.maximum(denominator, 1e-30)
    w = (d00 * d21 - d01 * d20) / np.maximum(denominator, 1e-30)
    inside = (n2 > 1e-24) & (v >= -1e-10) & (w >= -1e-10) & (v + w <= 1 + 1e-10)
    closest, distances = [], []
    for start, end in ((a, b), (b, c), (c, a)):
        edge = end - start
        t = np.clip(((point - start) * edge).sum(axis=1) / np.maximum((edge * edge).sum(axis=1), 1e-30), 0, 1)
        candidate = start + t[:, None] * edge
        closest.append(candidate); distances.append(((point - candidate) ** 2).sum(axis=1))
    closest.append(projected); distances.append(np.where(inside, ((point - projected) ** 2).sum(axis=1), np.inf))
    choices = np.asarray(distances); edge_index = np.argmin(choices, axis=0)
    nearest = np.asarray(closest)[edge_index, np.arange(len(triangles))]
    distances = choices[edge_index, np.arange(len(triangles))]
    index = int(np.argmin(distances))
    return float(distances[index]), nearest[index], index


class TriangleTree:
    def __init__(self, vertices, faces):
        import numpy as np
        self.np = np
        self.triangles = vertices[faces]
        if not len(faces):
            raise ValueError("cannot query empty triangle mesh")
        def build(indices):
            tri = self.triangles[indices]
            lower, upper = tri.min(axis=(0, 1)), tri.max(axis=(0, 1))
            if len(indices) <= 8:
                return lower, upper, indices, None, None
            axis = int(np.argmax(upper - lower))
            order = indices[np.argsort(tri.mean(axis=1)[:, axis], kind="stable")]
            mid = len(order) // 2
            return lower, upper, None, build(order[:mid]), build(order[mid:])
        self.root = build(np.arange(len(faces)))

    def nearest(self, points):
        np = self.np
        distances, witnesses, face_ids = [], [], []
        def bound(point, node):
            delta = np.maximum(np.maximum(node[0] - point, point - node[1]), 0)
            return float(delta @ delta)
        for point in points:
            best = [np.inf, None, None]
            def visit(node):
                if bound(point, node) > best[0] + 1e-15:
                    return
                if node[2] is not None:
                    d2, witness, index = _closest_triangles(point, self.triangles[node[2]])
                    if d2 < best[0]:
                        best[:] = d2, witness, int(node[2][index])
                else:
                    children = sorted((node[3], node[4]), key=lambda child: bound(point, child))
                    for child in children:
                        visit(child)
            visit(self.root)
            distances.append(math.sqrt(best[0])); witnesses.append(best[1]); face_ids.append(best[2])
        return np.asarray(distances), np.asarray(witnesses), face_ids


def surface_samples(vertices, faces, count=3000, spacing=None):
    import numpy as np
    if type(count) is not int or not 1 <= count <= 100000:
        raise ValueError("sampleCount must be 1..100000")
    triangles = vertices[faces]
    if not len(triangles):
        return np.empty((0, 3)), {"sampleCount": 0, "sampledFaceCount": 0, "faceCount": 0, "coverageComplete": False}
    samples, sampled = [], set()
    if spacing is not None:
        spacing = float(spacing)
        if not math.isfinite(spacing) or spacing <= 0:
            raise ValueError("sampleSpacing must be positive")
        for index, tri in enumerate(triangles):
            length = max(np.linalg.norm(tri[i] - tri[(i + 1) % 3]) for i in range(3))
            n = max(1, int(math.ceil(length / spacing)))
            needed = (n + 1) * (n + 2) // 2
            if len(samples) + needed > count:
                raise ValueError("sampleSpacing exceeds sampleCount budget; increase budget or declare coarser spacing")
            for i in range(n + 1):
                for j in range(n - i + 1):
                    samples.append(tri[0] + (tri[1] - tri[0]) * i / n + (tri[2] - tri[0]) * j / n)
            sampled.add(index)
        scheme = "barycentric_grid"
    else:
        # Every face receives a centroid before extra deterministic area-weighted samples.
        # Large meshes that exceed the budget explicitly remain incomplete.
        included = min(len(triangles), count)
        if included < len(triangles):
            selected = np.linspace(0, len(triangles) - 1, included, dtype=int)
        else:
            selected = np.arange(included)
        samples.extend(triangles[selected].mean(axis=1)); sampled.update(map(int, selected))
        remaining = count - included
        if remaining:
            areas = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) / 2
            if areas.sum() > 0:
                distribution = np.cumsum(areas / areas.sum())
                indices = np.searchsorted(distribution, (np.arange(remaining) + .5) / remaining)
                for i, face in enumerate(indices):
                    u = ((i + 1) * .6180339887498949) % 1
                    v = ((i + 1) * .4142135623730951) % 1
                    r = math.sqrt(u); tri = triangles[face]
                    samples.append((1 - r) * tri[0] + r * (1 - v) * tri[1] + r * v * tri[2]); sampled.add(int(face))
        scheme = "centroids_and_deterministic_area_samples"
    return np.asarray(samples), {"sampleCount": len(samples), "sampledFaceCount": len(sampled), "faceCount": len(faces),
                                "coverageComplete": len(sampled) == len(faces), "scheme": scheme,
                                "sampleSpacing": spacing, "continuousErrorBoundProven": False}


def surface_metrics(reference_mesh, actual_mesh, sample_count=3000, spacing=None):
    import numpy as np
    rv, rf, rid = normalize_mesh(reference_mesh); av, af, aid = normalize_mesh(actual_mesh)
    if not len(rf) or not len(af):
        return {"status": "missing_evidence", "unit": "m", "p95": None, "max": None, "reason": "empty_mesh",
                "referenceToActual": distance_summary([]), "actualToReference": distance_summary([])}
    rs, rcoverage = surface_samples(rv, rf, sample_count, spacing)
    as_, acoverage = surface_samples(av, af, sample_count, spacing)
    da, wa, aindex = TriangleTree(av, af).nearest(rs)
    dr, wr, rindex = TriangleTree(rv, rf).nearest(as_)
    forward, reverse = distance_summary(da, rs, wa), distance_summary(dr, as_, wr)
    forward["worst"]["destinationId"] = aid[aindex[int(np.argmax(da))]]
    reverse["worst"]["destinationId"] = rid[rindex[int(np.argmax(dr))]]
    return {"status": "measured" if rcoverage["coverageComplete"] and acoverage["coverageComplete"] else "incomplete_sampling",
            "unit": "m", "referenceToActual": forward, "actualToReference": reverse,
            "p95": max(forward["p95"], reverse["p95"]), "max": max(forward["max"], reverse["max"]),
            "sampling": {"reference": rcoverage, "actual": acoverage}}


def section_segments(mesh, plane, epsilon=1e-8):
    import numpy as np
    vertices, faces, _ = normalize_mesh(mesh)
    normal = np.asarray(plane["normal"], dtype=float); origin = np.asarray(plane["point"], dtype=float)
    if normal.shape != (3,) or origin.shape != (3,) or not np.isfinite(normal).all() or not np.isfinite(origin).all() or np.linalg.norm(normal) < epsilon:
        raise ValueError("section requires finite point and nonzero normal")
    normal /= np.linalg.norm(normal)
    result, coplanar = [], 0
    for triangle in vertices[faces]:
        distances = (triangle - origin) @ normal
        if (abs(distances) <= epsilon).all():
            coplanar += 1; continue
        hits = []
        for i in range(3):
            j = (i + 1) % 3
            if abs(distances[i]) <= epsilon:
                hits.append(triangle[i])
            elif distances[i] * distances[j] < -epsilon ** 2:
                t = distances[i] / (distances[i] - distances[j])
                hits.append(triangle[i] + t * (triangle[j] - triangle[i]))
        unique = []
        for point in hits:
            if not any(np.linalg.norm(point - other) <= epsilon for other in unique):
                unique.append(point)
        if len(unique) == 2:
            result.append(unique)
    return np.asarray(result).reshape((-1, 2, 3)), coplanar


def section_metrics(reference_mesh, actual_mesh, plane, spacing=.1):
    import numpy as np
    rs, rc = section_segments(reference_mesh, plane); act, ac = section_segments(actual_mesh, plane)
    if not len(rs) or not len(act):
        return {"status": "missing_evidence", "reason": "empty_section", "unit": "m", "p95": None, "max": None,
                "referenceCoplanarFaces": rc, "actualCoplanarFaces": ac}
    rpoints = np.concatenate([polyline_samples(s, spacing) for s in rs]); apoints = np.concatenate([polyline_samples(s, spacing) for s in act])
    da, wa = nearest_segments(rpoints, act); dr, wr = nearest_segments(apoints, rs)
    forward, reverse = distance_summary(da, rpoints, wa), distance_summary(dr, apoints, wr)
    return {"status": "measured" if rc == 0 and ac == 0 else "coplanar_section_incomplete", "unit": "m",
            "referenceToActual": forward, "actualToReference": reverse, "p95": max(forward["p95"], reverse["p95"]),
            "max": max(forward["max"], reverse["max"]), "sampleSpacing": spacing,
            "referenceCoplanarFaces": rc, "actualCoplanarFaces": ac}
