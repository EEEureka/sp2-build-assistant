"""Wavefront OBJ source adapter. No Blender, worker or game is required."""
from __future__ import annotations

from pathlib import Path
import math
from .common import ProviderError, coordinate_transform, mesh_result, source_info, transform_point, triangulate, vec3


def load_obj(path, unit=None, up_axis="+Y", forward_axis="+Z", selection=None):
    source = source_info(path)
    if Path(path).suffix.lower() != ".obj":
        raise ProviderError("unsupported_mesh_format", "First-version file adapter supports OBJ. Export unsupported source formats to OBJ or Blender exchange JSON.")
    transform = coordinate_transform(unit, up_axis, forward_axis)
    selection = selection or {}
    if isinstance(selection, list):
        selection = {"objectNames": selection}
    if not isinstance(selection, dict):
        raise ProviderError("invalid_selection", "selection must be an object or list of object names.")
    object_names = set(selection.get("objectNames", []))
    group_names = set(selection.get("groupNames", []))
    face_indices = set(selection.get("faceIndices", []))
    vertices, triangles, owners, metadata, materials = [], [], [], [], []
    objects = {}
    name, groups, material = "default", [], None
    face_index = 0
    unsupported = {}
    with Path(source["path"]).open(encoding="utf-8-sig", errors="strict") as stream:
        for line_number, line in enumerate(stream, 1):
            text = line.partition("#")[0].strip()
            if not text:
                continue
            fields = text.split()
            kind, values = fields[0], fields[1:]
            try:
                if kind == "v":
                    if len(values) < 3:
                        raise ProviderError("invalid_vertex", "OBJ vertex has fewer than three coordinates.")
                    point = vec3(values[:3])
                    if len(values) == 4:
                        w = float(values[3])
                        if not math.isfinite(w) or not w:
                            raise ProviderError("invalid_vertex", "OBJ homogeneous vertex requires finite nonzero w.")
                        point = [v/w for v in point]
                    vertices.append(transform_point(transform, point))
                elif kind == "o":
                    name = " ".join(values) or "default"
                elif kind == "g":
                    groups = values
                elif kind == "usemtl":
                    material = " ".join(values) or None
                elif kind == "mtllib":
                    materials.append(" ".join(values))
                elif kind == "f":
                    owner = objects.setdefault(name, {"id": name, "name": name, "groups": set(), "sourceFaceCount": 0, "selectedFaceCount": 0, "visible": None, "visibilityEvidence": "not_recorded_by_obj"})
                    owner["groups"].update(groups)
                    owner["sourceFaceCount"] += 1
                    selected = (not object_names or name in object_names) and (not group_names or bool(set(groups) & group_names)) and (not face_indices or face_index in face_indices)
                    ids = []
                    for token in values:
                        index = int(token.split("/")[0])
                        if index == 0:
                            raise ProviderError("invalid_face_index", "OBJ indices are one-based; zero is invalid.")
                        index = index-1 if index > 0 else len(vertices)+index
                        if index < 0 or index >= len(vertices):
                            raise ProviderError("invalid_face_index", "OBJ face references an undefined vertex.")
                        ids.append(index)
                    if ids and ids[0] == ids[-1]:
                        ids.pop()
                    if selected:
                        faces = triangulate(ids, vertices)
                        owner["selectedFaceCount"] += 1
                        triangles.extend(faces)
                        owners.extend([name] * len(faces))
                        metadata.extend([{"sourceFaceIndex": face_index, "objectId": name, "groups": list(groups), "material": material}] * len(faces))
                    face_index += 1
                elif kind not in ("vt", "vn", "s", "l", "p"):
                    unsupported[kind] = unsupported.get(kind, 0) + 1
            except (ValueError, IndexError) as error:
                if isinstance(error, ProviderError):
                    error.details.setdefault("line", line_number)
                    raise
                raise ProviderError("invalid_obj", str(error), {"line": line_number}) from error
    for obj in objects.values():
        obj["groups"] = sorted(obj["groups"])
        obj["included"] = obj["selectedFaceCount"] > 0
        if not obj["included"]:
            obj["exclusionReason"] = "outside_selection"
    missing = sorted(object_names - set(objects))
    if missing:
        raise ProviderError("selection_not_found", "Some requested OBJ objects are absent.", {"objectNames": missing})
    diagnostics = {"format": "obj", "sourceFaceCount": face_index, "materialLibraries": materials, "unsupportedStatements": unsupported,
                   "selection": selection, "visibilityStatus": "unknown_obj_does_not_record_hidden_objects", "unitSource": unit, "sourceUpAxis": up_axis, "sourceForwardAxis": forward_axis}
    return mesh_result(vertices, triangles, owners, list(objects.values()), source, transform, diagnostics, metadata)


inspect_obj = load_obj
