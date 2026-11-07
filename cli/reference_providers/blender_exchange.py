"""Read a Blender-produced exchange file; importing/reading never connects to Blender.

schemaVersion=1; units/upAxis/forwardAxis are mandatory source declarations.
Each MESH object contains local vertices, triangle indices or polygon faces,
row-major matrixWorld and explicit visible/hidden/excluded values.
"""
from __future__ import annotations

import json
from pathlib import Path
from .common import ProviderError, coordinate_transform, mesh_result, source_info, transform_point, triangulate, validate_matrix, vec3


IDENTITY = [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


def load_exchange(path, selection=None):
    source = source_info(path)
    try:
        data = json.loads(Path(source["path"]).read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as error:
        raise ProviderError("invalid_exchange", "Blender exchange must be UTF-8 JSON.") from error
    if data.get("schemaVersion") != 1:
        raise ProviderError("unsupported_exchange_schema", "Expected Blender exchange schemaVersion 1.")
    if not all(key in data for key in ("units", "upAxis", "forwardAxis", "objects")):
        raise ProviderError("invalid_exchange", "Exchange must declare units, upAxis, forwardAxis and objects.")
    transform = coordinate_transform(data["units"], data["upAxis"], data["forwardAxis"])
    selection = selection or {}
    if isinstance(selection, list):
        selection = {"objectNames": selection}
    requested = set(selection.get("objectIds", []))
    names = set(selection.get("objectNames", []))
    include_hidden = bool(selection.get("includeHidden", False))
    include_excluded = bool(selection.get("includeExcluded", False))
    vertices, triangles, owners, objects = [], [], [], []
    recorded, unknown_visibility, missing_geometry = set(), [], []
    for raw in data["objects"]:
        obj_id = str(raw.get("id") or raw.get("name") or "")
        if not obj_id or obj_id in recorded:
            raise ProviderError("invalid_exchange", "Exchange object IDs must be present and unique.")
        recorded.add(obj_id)
        obj = {key: raw.get(key) for key in ("name", "type", "visible", "hidden", "excluded", "collections", "materialSlots", "modifiersApplied")}
        obj["id"] = obj_id
        if any(key not in raw for key in ("visible", "hidden", "excluded")):
            unknown_visibility.append(obj_id)
        matrix = validate_matrix(raw.get("matrixWorld", IDENTITY))
        obj["matrixWorld"] = matrix
        obj["transformEvidence"] = "exported_matrix" if "matrixWorld" in raw else "assumed_identity_not_exported"
        selection_match = (not requested or obj_id in requested) and (not names or raw.get("name") in names)
        excluded = raw.get("excluded") is True
        hidden = raw.get("hidden") is True or (raw.get("visible") is False and not excluded)
        included = selection_match and (include_hidden or not hidden) and (include_excluded or not excluded) and raw.get("type", "MESH") == "MESH"
        obj["included"] = included
        if not included:
            obj["exclusionReason"] = "outside_selection" if not selection_match else "hidden_or_excluded" if (hidden and not include_hidden) or (excluded and not include_excluded) else "non_mesh_object"
            objects.append(obj)
            continue
        if "vertices" not in raw or not ("triangles" in raw or "faces" in raw):
            missing_geometry.append(obj_id)
            obj.update(included=False, exclusionReason="geometry_not_exported")
            objects.append(obj)
            continue
        local = [vec3(v) for v in raw["vertices"]]
        transformed = [transform_point(transform, transform_point(matrix, v)) for v in local]
        offset = len(vertices)
        source_faces = raw.get("triangles", raw.get("faces"))
        baked = []
        for face_index, face in enumerate(source_faces):
            if not isinstance(face, list) or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(local) for i in face):
                raise ProviderError("invalid_face_index", "Exchange face references invalid local vertex.", {"objectId": obj_id, "faceIndex": face_index})
            baked.extend(triangulate(face, transformed))
        det = (matrix[0][0]*(matrix[1][1]*matrix[2][2]-matrix[1][2]*matrix[2][1]) - matrix[0][1]*(matrix[1][0]*matrix[2][2]-matrix[1][2]*matrix[2][0]) + matrix[0][2]*(matrix[1][0]*matrix[2][1]-matrix[1][1]*matrix[2][0]))
        if abs(det) < 1e-12:
            raise ProviderError("singular_object_transform", "Selected object has a singular matrixWorld.", {"objectId": obj_id})
        if det < 0:
            baked = [[a,c,b] for a,b,c in baked]
        vertices.extend(transformed)
        triangles.extend([[i+offset for i in face] for face in baked])
        owners.extend([obj_id]*len(baked))
        obj.update(sourceFaceCount=len(source_faces), triangleCount=len(baked), determinant=det)
        objects.append(obj)
    absent = requested - recorded
    missing_names = names - {raw.get("name") for raw in data["objects"]}
    if absent or missing_names:
        raise ProviderError("selection_not_found", "Some requested exchange objects are absent.", {"objectIds": sorted(absent), "objectNames": sorted(missing_names)})
    diagnostics = {"format": "blender_exchange", "blenderVersion": data.get("blenderVersion"), "exportScope": data.get("exportScope", "unspecified"),
                   "visibilityUnknownObjects": unknown_visibility, "geometryNotExportedObjects": missing_geometry,
                   "excludedObjectCount": sum(not o["included"] for o in objects), "selection": selection,
                   "sourceUpAxis": data["upAxis"], "sourceForwardAxis": data["forwardAxis"], "unitSource": data["units"],
                   "completenessStatus": "incomplete_geometry" if missing_geometry else "visibility_unknown" if unknown_visibility else "recorded_scope_only",
                   "completenessCaveat": "Only exported objects are known. Visibility, selection and export scope do not prove the original asset has no additional hidden geometry."}
    return mesh_result(vertices, triangles, owners, objects, source, transform, diagnostics)
