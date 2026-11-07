"""Reference mesh schema and coordinate helpers without third-party modules."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path


class ProviderError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def source_info(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ProviderError("source_not_found", "Reference source does not exist.", {"path": str(path)})
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def vec3(value, label="vertex"):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ProviderError("invalid_geometry", f"{label} must contain three finite numbers.")
    try:
        result = [float(x) for x in value]
    except (TypeError, ValueError) as error:
        raise ProviderError("invalid_geometry", f"{label} must contain three finite numbers.") from error
    if not all(math.isfinite(x) for x in result):
        raise ProviderError("invalid_geometry", f"{label} must contain three finite numbers.")
    return result


def unit_scale(unit):
    scales = {"m": 1.0, "meter": 1.0, "metre": 1.0, "cm": .01, "mm": .001, "ft": .3048, "in": .0254}
    if unit is None:
        raise ProviderError("reference_units_required", "OBJ has no intrinsic unit. Specify unit (m, cm, mm, ft, in) or positive metersPerUnit.")
    if isinstance(unit, dict):
        unit = unit.get("metersPerUnit")
    if isinstance(unit, str):
        if unit.lower() not in scales:
            raise ProviderError("unsupported_units", f"Unsupported reference unit: {unit}")
        return scales[unit.lower()]
    if isinstance(unit, bool) or not isinstance(unit, (int, float)) or not math.isfinite(unit) or unit <= 0:
        raise ProviderError("invalid_units", "metersPerUnit must be finite and positive.")
    return float(unit)


def axis_vector(axis):
    axis = str(axis).upper()
    if len(axis) == 1:
        axis = "+" + axis
    if len(axis) != 2 or axis[0] not in "+-" or axis[1] not in "XYZ":
        raise ProviderError("invalid_axis", "Axes must be +X, -X, +Y, -Y, +Z or -Z.")
    out = [0., 0., 0.]
    out["XYZ".index(axis[1])] = 1. if axis[0] == "+" else -1.
    return out


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def coordinate_transform(unit, up, forward):
    scale = unit_scale(unit)
    up, forward = axis_vector(up), axis_vector(forward)
    if sum(a*b for a, b in zip(up, forward)) != 0:
        raise ProviderError("invalid_axis", "Up and forward must be perpendicular.")
    right = cross(up, forward)
    return [[scale * x for x in row] + [0.] for row in (right, up, forward)] + [[0., 0., 0., 1.]]


def validate_matrix(value):
    if not isinstance(value, list) or len(value) != 4 or any(not isinstance(row, (list, tuple)) or len(row) != 4 for row in value):
        raise ProviderError("invalid_transform", "matrixWorld must be a row-major 4 by 4 matrix.")
    try:
        matrix = [[float(x) for x in row] for row in value]
    except (TypeError, ValueError) as error:
        raise ProviderError("invalid_transform", "matrixWorld must contain finite numbers.") from error
    if not all(math.isfinite(x) for row in matrix for x in row) or any(abs(matrix[3][i] - (1. if i == 3 else 0.)) > 1e-10 for i in range(4)):
        raise ProviderError("invalid_transform", "matrixWorld must be a finite affine transform.")
    return matrix


def transform_point(matrix, point):
    return [sum(matrix[i][j]*point[j] for j in range(3)) + matrix[i][3] for i in range(3)]


def topology_diagnostics(vertices, triangles):
    """Boundary edges indicate missing coverage, not proof of accidentally lost faces."""
    edges, degenerate, duplicate = {}, [], []
    seen = set()
    for index, face in enumerate(triangles):
        if not isinstance(face, (list, tuple)) or len(face) != 3 or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(vertices) for i in face):
            raise ProviderError("invalid_face_index", "Triangle contains an invalid zero-based vertex index.", {"triangle": index})
        key = tuple(sorted(face))
        if key in seen:
            duplicate.append(index)
        seen.add(key)
        a, b, c = (vertices[i] for i in face)
        area_vec = cross([b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)])
        if sum(x*x for x in area_vec) < 1e-24:
            degenerate.append(index)
        for i in range(3):
            edge = tuple(sorted((face[i], face[(i+1)%3])))
            edges[edge] = edges.get(edge, 0) + 1
    boundaries = [list(edge) for edge, count in edges.items() if count == 1]
    nonmanifold = [list(edge) for edge, count in edges.items() if count > 2]
    return {"boundaryEdgeCount": len(boundaries), "boundaryEdgeSamples": boundaries[:100], "nonManifoldEdgeCount": len(nonmanifold),
            "nonManifoldEdgeSamples": nonmanifold[:100], "degenerateTriangles": degenerate[:100], "degenerateTriangleCount": len(degenerate),
            "duplicateTriangleCount": len(duplicate), "duplicateTriangleSamples": duplicate[:100],
            "coverageStatus": "open_surface_or_missing_faces" if boundaries else "no_boundary_edges_detected",
            "missingFacesConclusion": "Boundary edges can be intentional openings or split vertices; hidden/unexported geometry cannot be inferred from a mesh alone."}


def mesh_result(vertices, triangles, face_objects, objects, source, transform, diagnostics=None, face_metadata=None):
    if not triangles:
        raise ProviderError("empty_selection", "Reference selection contains no mesh faces.")
    # Compact selected geometry so excluded objects cannot contaminate bounds.
    used = sorted({i for face in triangles for i in face})
    mapping = {old: new for new, old in enumerate(used)}
    vertices = [vertices[i] for i in used]
    triangles = [[mapping[i] for i in face] for face in triangles]
    top = topology_diagnostics(vertices, triangles)
    low = [min(v[i] for v in vertices) for i in range(3)]
    high = [max(v[i] for v in vertices) for i in range(3)]
    return {"meshSchemaVersion": 1, "vertices": vertices, "triangles": triangles, "faceObjectIds": face_objects,
            "faceMetadata": face_metadata or [], "objects": objects, "source": source, "unit": "m", "upAxis": "+Y", "forwardAxis": "+Z",
            "sourceToReference": transform, "bounds": {"min": low, "max": high, "size": [high[i]-low[i] for i in range(3)]},
            "diagnostics": {**(diagnostics or {}), **top}, "vertexCount": len(vertices), "triangleCount": len(triangles)}


def triangulate(indices, vertices):
    """Ear-clip planar polygons. Refuse self-intersection instead of wrong fan geometry."""
    if len(indices) < 3 or len(set(indices)) < 3:
        raise ProviderError("invalid_polygon", "A face needs at least three distinct vertices.")
    if len(indices) == 3:
        return [indices]
    normal = [0., 0., 0.]
    for a, b in zip(indices, indices[1:] + indices[:1]):
        pa, pb = vertices[a], vertices[b]
        normal[0] += (pa[1]-pb[1])*(pa[2]+pb[2])
        normal[1] += (pa[2]-pb[2])*(pa[0]+pb[0])
        normal[2] += (pa[0]-pb[0])*(pa[1]+pb[1])
    dropped = max(range(3), key=lambda i: abs(normal[i]))
    if abs(normal[dropped]) < 1e-18:
        raise ProviderError("invalid_polygon", "Polygon has no stable area; triangulate this source explicitly.")
    axes = [i for i in range(3) if i != dropped]
    pts = {i: [vertices[i][a] for a in axes] for i in indices}
    def area(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    winding = 1 if sum(pts[a][0]*pts[b][1]-pts[b][0]*pts[a][1] for a,b in zip(indices,indices[1:]+indices[:1])) > 0 else -1
    remaining, triangles = list(indices), []
    while len(remaining) > 3:
        for j, b in enumerate(remaining):
            a, c = remaining[j-1], remaining[(j+1)%len(remaining)]
            if winding*area(pts[a],pts[b],pts[c]) <= 1e-14:
                continue
            others = [v for v in remaining if v not in (a,b,c)]
            if any(all(winding*area(pts[u],pts[v],pts[p]) >= -1e-14 for u,v in ((a,b),(b,c),(c,a))) for p in others):
                continue
            triangles.append([a,b,c])
            remaining.pop(j)
            break
        else:
            raise ProviderError("invalid_polygon", "Polygon could not be triangulated reliably; triangulate the source explicitly.")
    triangles.append(remaining)
    return triangles
