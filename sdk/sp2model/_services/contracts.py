"""Versioned output contracts. Shared definitions describe game-native units and identity.

Additive fields are allowed for bridge/CLI version skew. Required legacy fields
remain checked. Dynamic native shape/catalog schemas retain their own schema.
"""
from copy import deepcopy

S = {"type": "string"}
I = {"type": "integer"}
N = {"type": "number"}
B = {"type": "boolean"}


def obj(properties, required=None, **extra):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, **extra}


def arr(items):
    return {"type": "array", "items": items}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def described(schema, text):
    return {**schema, "description": text}


V = {"type": "array", "items": N, "minItems": 3, "maxItems": 3}
IDS = arr(I)
STRINGS = arr(S)
MAP = {"type": "object", "additionalProperties": S}
DYNAMIC = {"type": "object", "description": "Native family-specific fields. Query shape.schema or catalog.schema for the corresponding type; do not infer absent defaults."}

DEFS = {
    "Identity": obj({"craftSessionId": S, "revision": described(I, "Observed XML content version, not successful command count. Native recovery after a failed batch may advance it; use the returned identity or re-read status before any new write."), "fingerprint": S,
                     "fingerprintAlgorithm": S, "gameVersion": S, "xmlVersion": I, "stateUncertain": B}),
    "XmlNode": obj({"element": S, "attributes": MAP, "children": arr(ref("XmlNode")), "text": nullable(S)}),
    "PartSummary": obj({"id": described(I, "Reusable ID scoped to craftSessionId and revision; never a persistent part identity."),
                        "type": described(S, "Native PartTypeId. Use this for type decisions."),
                        "name": described(S, "Player-editable instance display name; neither unique nor a type identifier."),
                        "typeName": described(S, "Native part type display name, independent of instance name.")}, ["id", "type", "name"]),
    "OutputDefinition": obj({"id": S, "name": S, "defaultVariable": nullable(S), "defaultPriority": I}),
    "OutputBinding": obj({"outputId": S, "variable": nullable(S), "priority": I, "activator": nullable(S)}),
    "PartOutput": obj({"modifier": S, "definitions": arr(ref("OutputDefinition")), "bindings": arr(ref("OutputBinding"))}),
    "OutputSource": obj({"partId": I, "type": S, "typeName": S, "name": S, "modifiers": arr(ref("PartOutput"))}),
    "Setter": obj({"index": described(I, "Current zero-based index in native setter order. Re-query after add/delete/reorder."),
                   "variable": nullable(S), "function": nullable(S), "priority": I, "activator": nullable(S)}),
    "Connection": obj({"partA": I, "partB": I,
                       "attachPointsA": described(IDS, "Native endpoint A's attach-point ID set; a connection may contain multiple IDs."), "attachPointsB": IDS}),
    "AttachPoint": obj({"id": I, "localPosition": described(V, "DLL 0.4.11+: live attach-point handle position transformed into part-local metres. Earlier DLLs may report stale definition positions for dynamic powertrain points."),
                        "worldPosition": described(V, "DLL 0.4.11+: live attach-point handle world position in metres; definition fallback is explicitly identified by positionSource."),
                        "normal": described(V, "Native attach-point normal direction in part-local coordinates, dimensionless. Returned as stored, without normalization; do not assume unit length."),
                        "jointAxisLocal": described(V, "Native joint-axis direction in part-local coordinates, dimensionless; not Euler angles. Returned as stored, without normalization; do not assume unit length."),
                        "jointAxisWorld": described(V, "Native joint-axis direction transformed into world coordinates using TransformDirection (rotation only, no translation or scale). Dimensionless, not Euler angles; no normalization is applied."), "available": B,
                        "allowManualConnection": B, "allowMultiple": B, "seekType": S, "receiveType": S,
                        "seekTypes":described(STRINGS,"DLL 0.5.0+: decoded seek flags. Absent on older DLLs; use seekType there."),
                        "receiveTypes":described(STRINGS,"DLL 0.5.0+: decoded receive flags. Absent on older DLLs; use receiveType there."),
                        "excludeTypes":described(STRINGS,"DLL 0.5.0+: decoded exclusions. Absence on older DLLs means unavailable, not an empty set."),
                        "seekTypeMask":described(I,"DLL 0.5.0+: native seek bit mask; absent on older DLLs."),
                        "receiveTypeMask":described(I,"DLL 0.5.0+: native receive bit mask; absent on older DLLs."),
                        "excludeTypeMask":described(I,"DLL 0.5.0+: native exclusion bit mask; absent on older DLLs."),
                        "jointType": S, "role": {"enum": ["rotor", "housing", "moving_end", "articulated", "attachment"]},
                        "roleSource": S, "requiresPhysicsJoint": B, "bodyIslandBoundary": B,
                        "mirrorId": I, "surface": B, "connectedPartIds": IDS},
                       ["id", "localPosition", "worldPosition", "normal", "jointAxisLocal", "jointAxisWorld",
                        "available", "allowManualConnection", "allowMultiple", "seekType", "receiveType",
                        "jointType", "role", "roleSource", "requiresPhysicsJoint", "bodyIslandBoundary",
                        "mirrorId", "surface", "connectedPartIds"]),
    "Bounds": obj({"center": V, "size": V, "min": V, "max": V}),
    "Checkpoint": obj({"id": S, "name": S, "craftSessionId": S, "fingerprint": S,
                       "revision": I, "createdAt": S}, ["id", "name", "craftSessionId", "fingerprint"]),
    "Change": obj({"kind": S, "partId": nullable(I), "partIds": IDS, "deletedPartIds": IDS,
                   "createdPartIds": IDS, "affectedPartIds": IDS, "synchronizedPartIds": IDS,
                   "partA": I, "partB": I, "templateId": S, "editMode": S, "assembly": B,
                   "rootPartIds": IDS, "temporaryId": S, "wingPartId": I, "style": S,
                   "controlAttachPointId": described(I,"DLL 0.4.6+: control's selected attach point for wing.control.add."),
                   "wingAttachPointId": described(I,"DLL 0.4.6+: wing's selected surface receive point, preserving the structural root."),
                   "attachmentBasis": described(S,"DLL 0.4.6+: native_wing_surface_receive_point for wing.control.add."),
                   "groupId": I, "sourcePartId": I, "enabled": B, "symmetric": B, "checkpointId": S}, ["kind"]),
    "ReusedPartId": obj({"partId": I, "previous": ref("PartSummary"), "current": ref("PartSummary"),
                        "deletedAtOperationIndex": described(I, "Zero-based batch operation index."),
                        "createdAtOperationIndex": I, "temporaryIds": STRINGS}),
    "Validation": obj({"readBack": B, "expressionCompile": B, "geometryRefreshed": B,
                       "physicsSynchronized": B, "editorCachesRebuilt": B, "partCount": I,
                       "restorationVerified": nullable(B), "restoreEulerToleranceDegrees": N}),
    "Rollback": obj({"required": B, "restored": B, "fingerprintIdentical": B, "error": nullable(S), "attempted": B, "beforeFingerprint": S, "currentFingerprint": S,
                     "beforeRevision": I, "currentRevision": I, "revisionChanged": B, "revisionMeaning": S,
                     "restoreEulerToleranceDegrees": N, "identity": ref("Identity")}, []),
    "Error": obj({"code": S, "message": S, "operationId": S, "instancePid": I, "state": S}, ["code", "message"]),
    "Artifact": obj({"name": S, "bytes": I, "sha256": S, "mimeType": S}, ["name", "bytes", "sha256"]),
    "VisualGroup": obj({"index": described(I, "Legacy alias of groupIndex; zero-based, already usable for joins on DLL 0.3.1."),
                        "groupIndex": described(I, "DLL 0.3.2+: canonical zero-based join key for detailStatus and imageRecommendations. Equals index."), "name": S, "selector": obj({"kind": S, "partIds": IDS, "rootPartId": I,
                                  "stopConnectionKeys": STRINGS, "hops": I}, ["kind"]),
                        "partIds": IDS, "externalConnections": arr(ref("VisualConnection")),
                        "bounds": nullable(ref("Bounds")), "analysisColor": V}, ["index", "name", "selector", "partIds", "externalConnections"]),
    "VisualConnection": obj({"key": S, "partA": I, "partB": I, "attachPointsA": IDS, "attachPointsB": IDS}, ["key", "partA", "partB", "attachPointsA", "attachPointsB"]),
    "ImageRecommendation": obj({"file": S, "path": S, "reason": S, "groupIndex": I,
                                "view": S, "pixelsPerMetre": N, "meaning": S}, ["file", "reason"]),
    "GroupProjection": obj({"view": S, "widthPixels": N, "heightPixels": N, "visiblePixels": I,
                            "relativeExtent": N, "readable": B, "readability": N}),
    "DetailStatus": obj({"groupIndex": I, "status": {"enum": ["generated", "not_needed", "disabled", "budget_exceeded", "no_geometry"]},
                         "detailNeeded": B, "jointBestView": S, "jointViews": arr(ref("GroupProjection"))}, ["groupIndex", "status"]),
}
DEFS["Part"] = obj({**DEFS["PartSummary"]["properties"],
                   "position": described(V, "Unity world position in metres."),
                   "rotationEulerDegrees": described(V, "Unity world Euler angles in degrees."),
                   "rotationQuaternion": {"type": "array", "items": N, "minItems": 4, "maxItems": 4, "description": "Unity world quaternion x,y,z,w."},
                   "scale": described(V, "Local scale about the part origin, not necessarily the geometry center."),
                   "symmetryId": I, "materialIds": IDS, "connectedPartIds": IDS},
                  ["id", "type", "name", "position", "rotationEulerDegrees", "rotationQuaternion", "scale", "symmetryId", "materialIds", "connectedPartIds"])
DEFS["InputController"] = obj({
    "index": described({"type": "integer", "minimum": 0}, "Zero-based occurrence among this part's native InputController modifiers."),
    "path": {"type": "string", "pattern": r"^InputController\.State\[[0-9]+\]$"},
    "name": nullable(S), "description": nullable(S),
    "input": S, "activationGroup": S, "invert": B, "invertType": {"enum": ["Axis", "Output"]},
    "min": N, "max": N, "zeroOnDeactivate": B, "invertOnMirror": B,
    "serializedAttributes": described(STRINGS, "Attributes emitted by native GenerateStateXml for this effective configuration. Omission does not mean false or unknown; read the typed value above."),
    "valueSource": {"enum": ["live_part_modifier", "isolated_template_modifier"]},
}, description="DLL 0.4.9+: effective native input configuration, including defaults omitted from XML. No input or telemetry evaluation. name, description and invertOnMirror are context, not extra writable fields.")
DYNAMIC["properties"] = {"inputControllers": arr(ref("InputController"))}
DEFS["PartDetail"] = {"allOf": [ref("Part"), obj({"state": ref("XmlNode"), "outputs": arr(ref("PartOutput")), "attachPoints": arr(ref("AttachPoint")),
                                               "inputControllers": arr(ref("InputController"))}, ["state", "outputs", "attachPoints"])]}
DEFS["DesignerSceneIntegrity"] = obj({"status": {"enum": ["healthy", "inconsistent"]}, "currentAircraftPresent": B, "currentAircraftActive": B,
    "aircraftInstanceCount": I, "extraAircraftInstanceCount": I, "activeAircraftInstanceCount": I,
    "selectedPartBelongsToCurrentAircraft": nullable(B), "instances": arr(obj({"instanceId": I, "name": S,
        "isCurrent": B, "activeInHierarchy": B, "partCount": I})), "scope": S, "meaning": S},
    description="DLL 0.4.10+: live designer container instance audit, separate from XML identity. A 30-part snapshot does not rule out a second visible scene instance. Writes and mesh analysis reject an inconsistent scene; DLL 0.4.11 designer.capture allows diagnostic native scene screenshots.")
DEFS["Validation"]["properties"]["sceneIntegrityVerified"] = B
DEFS["Job"] = obj({"operationId": S, "state": {"enum": ["queued", "running", "succeeded", "failed", "cancelled", "result_expired"]},
                   "createdAt": S, "completedAt": S, "completionState": {"enum": ["succeeded", "failed", "cancelled"]},
                   "resultRetention": {"enum": ["available", "age_or_capacity_limit", "single_result_exceeds_capacity", "retention_failed"]},
                   "result": nullable(ref("AnyResult")), "instancePid": I}, ["operationId", "state", "createdAt", "result"])
DEFS["AnyResult"] = obj({"success": B, "schemaVersion": S,
                         "data": {"description": "Result of the submitted command. Consult that command's outputSchema.", "type": ["object", "array", "string", "number", "boolean", "null"]},
                         "error": ref("Error")}, ["success", "schemaVersion"])


def identified(fields, required=None):
    return obj({"identity": ref("Identity"), **fields}, None if required is None else ["identity", *required])


def page(item):
    return obj({"total": I, "offset": I, "limit": I, "items": arr(item)})


DEFS["AttachPoint"]["properties"].update({
    "positionSource": {"enum": ["live_attach_point_transform", "native_part_definition"], "description": "DLL 0.4.11+: source of localPosition/worldPosition; definition fallback means no matching live handle was available."},
    "definitionLocalPosition": described(V, "Native AttachPointData.Position for comparison. Dynamic handles may move independently; do not treat this as the live mount position.")})

MUTATION = identified({"operationId": S, "actualChanges": arr(ref("Change")),
                       "temporaryIds": {"type": "object", "additionalProperties": I},
                       "reusedPartIds": arr(ref("ReusedPartId")), "invalidatedTemporaryIds": STRINGS,
                       "beforeCheckpointId": described(nullable(S), "Null when the 64-checkpoint capacity is reached."),
                       "validation": ref("Validation"), "rollbackResult": ref("Rollback"), "selectedPartId": nullable(I)},
                      ["operationId", "actualChanges", "temporaryIds", "beforeCheckpointId", "validation", "rollbackResult", "selectedPartId"])
MUTATION["properties"]["identity"] = described(ref("Identity"), "Identity sampled at completion, not a lock on future state. Native save/AutoRecenter or player edits may subsequently advance revision. Read fresh state on revision_conflict and compare geometry at one revision; history.nativeSteps lists observed native steps without identifying who triggered them.")
MUTATION["properties"]["validation"] = described(ref("Validation"), "Checks at completion. Native geometry was settled then; this does not prevent a later save/recenter or player edit. Native connection callbacks may change shape or pose within the successful batch; read back actual values rather than assuming the submitted values are the final shape.")
OUTPUTS = {
    "scope.capture": identified({"scopeId":S,"ownerId":S,"capturedRevision":I,"writePartIds":IDS,"guardPartIds":IDS,"boundaryPartIds":IDS,"relations":arr({"type":"object"}),"partFingerprints":{"type":"object"},"sharedStateFingerprint":S}),
    "scope.get": identified({"scopeId":S,"valid":B,"writePartIds":IDS,"guardPartIds":IDS,"conflict":{"type":"object"}},["scopeId","valid","writePartIds","guardPartIds"]),
    "scope.release": identified({"scopeId":S,"released":B}),
    "scoped.batch.apply": identified({"operationId":S,"scopeId":S,"ownerId":S,"completed":B,"completedOperationCount":I,"operationCount":I,"chunks":arr({"type":"object"}),"rollbackPolicy":S,"frameDiagnostics":{"type":"object"},"verificationLevel":S}),
    "designer.capture": identified({"captureId": S, "backend": {"const": "native_designer_camera"}, "nativeMaterials": B, "includesUi": B, "includesGizmos": {"type":["boolean","null"]}, "gizmoPolicy": S,
        "cameraRestored": B, "sceneIntegrity": ref("DesignerSceneIntegrity"),
        "views": arr(obj({"name": S, "view": S, "file": S, "width": I, "height": I,
            "camera": obj({"positionWorld": V, "targetWorld": V, "forwardWorld": V, "upWorld": V,
                "rotationQuaternion": {"type": "array", "items": N, "minItems": 4, "maxItems": 4},
                "projection": {"enum": ["perspective", "orthographic"]}, "fieldOfViewDegrees": N, "orthographicSize": N, "aspect": N,
                "nearClipMetres": N, "farClipMetres": N, "worldToCameraRows": arr(arr(N)), "projectionRows": arr(arr(N))}),
            "autoDistance": B, "autoOrthographicSize": B})),
        "artifactBase": S, "files": arr(ref("Artifact")), "recommendedImages": described(STRINGS, "Every requested native screenshot, as absolute local paths after CLI download."),
        "warnings": STRINGS, "retention": S, "outputDirectory": S, "manifestPath": S},
        ["captureId", "backend", "nativeMaterials", "includesUi", "includesGizmos", "cameraRestored", "sceneIntegrity", "views", "artifactBase", "files", "recommendedImages", "warnings", "retention"]),
    "parts.get": identified({"part": ref("PartDetail")}),
    "parts.list": identified({"listing": page(ref("Part"))}),
    "connections.points": identified({"points": arr(ref("AttachPoint"))}),
    "connections.list": identified({"connections": nullable(ref("XmlNode"))}),
    "craft.snapshot": identified({"name": S, "partCount": I, "selectedPartId": nullable(I), "parts": arr(ref("Part")),
                                   "connections": nullable(ref("XmlNode")), "variables": nullable(ref("XmlNode")),
                                   "coordinateSystem": S, "xml": S,
                                   "xmlMetadataCaveat": described(S, "DLL 0.4.4+, with includeXml: native Aircraft size/boundsMin/boundsOffset are save-time metadata, not live geometry bounds. Use parts.geometry or a same-revision visual capture.")},
                                  ["name", "partCount", "selectedPartId", "parts", "connections", "variables", "coordinateSystem"]),
    "parts.assembly": identified({"assembly": obj({"rootPartId": I, "symmetric": B, "rootPartIds": IDS,
                       "memberPartIds": IDS, "childPartIds": IDS, "parts": arr(ref("Part")),
                       "externalConnections": arr(obj({"partA": I, "partB": I})), "membershipSource": S, "meaning": S})}),
    "designer.raycast": identified({"hits": arr(obj({"partId": I, "part": ref("PartSummary"), "distance": described(N, "Metres from ray origin."),
                       "point": described(V, "Unity world metres."), "normal": described(V, "Unity world unit normal.")}, ["partId", "distance", "point", "normal"])),
                       "query": obj({"origin": V, "direction": V, "distanceMetres": N, "mode": {"const": "all_collider_hits"},
                                     "order": {"const": "distance_ascending"}, "deduplicatedByPart": B, "truncated": B,
                                     "coordinateSystem": S, "filters": S, "meaning": S})}, ["hits"]),
    "designer.selection": identified({"selectedPartId": nullable(I), "part": nullable(ref("PartDetail")), "shape": nullable(DYNAMIC), "meaning": S}),
    "spatial.query": identified({"deltaWorld": V, "positionBInA": V, "distanceMetres": N}),
    "outputs.list": identified({"parts": arr(obj({"partId": I, "modifiers": arr(ref("PartOutput"))}))}),
    "variables.list": identified({"setters": nullable(ref("XmlNode")), "sources": arr(obj({"partId": I, "outputs": arr(ref("PartOutput"))}))}),
    "shape.get": identified({"partId": I, "shape": DYNAMIC}),
    "shape.schema": identified({"schema": {"type": "object", "description": "Native typed-edit schema for the requested family."}}),
    "funky.validate": identified({"valid": B, "compiledOnly": B, "evaluated": B}),
    "batch.preview": identified({"validated": S, "operationCount": I, "warnings": STRINGS}),
    "batch.apply": MUTATION, "craft.undo": MUTATION, "craft.rollback": MUTATION,
    "craft.checkpoint.create": ref("Checkpoint"),
    "craft.checkpoint.list": identified({"checkpoints": arr(ref("Checkpoint"))}),
    "craft.checkpoint.get": identified({"checkpoint": ref("Checkpoint")}),
    "craft.history": identified({"operations": arr(obj({"operationId": S, "command": S, "revision": I, "beforeFingerprint": S, "fingerprint": S})),
                                  "nativeSteps": arr(obj({"index": I, "Description": S, "time": S, "hash": S})), "canUndo": B, "canRedo": B}),
    "visual.resolve": identified({"groups": arr(ref("VisualGroup")), "partIds": IDS, "connections": arr(ref("VisualConnection")), "meaning": S}),
    "visual.pick": obj({"captureId": S, "view": S, "x": I, "y": I, "partId": nullable(I), "capturedIdentity": ref("Identity"), "meaning": S}),
    "visual.capture": identified({"captureId": S, "geometryStamp": S, "complete": B, "staleAtDelivery": B,
                      "artifactBase": S, "files": arr(ref("Artifact")), "recommendedImages": described(STRINGS, "Absolute local PNG paths after CLI download; overview plus useful isolated details."),
                      "imageRecommendations": arr(ref("ImageRecommendation")), "detailStatus": arr(ref("DetailStatus")),
                      "scalePolicy": S, "comparisonGuidance": S,
                      "exclusions": arr(obj({"partId": I, "renderer": S, "reason": S, "type": S, "count": I}, ["partId", "reason"])),
                      "warnings": STRINGS, "retention": S, "outputDirectory": S, "manifestPath": S},
                     ["captureId", "geometryStamp", "complete", "staleAtDelivery", "artifactBase", "files", "recommendedImages", "exclusions", "warnings", "retention"]),
    "operation.status": ref("Job"), "operation.cancel": ref("Job"),
    "version": obj({"version": S, "python": S}), "skill.path": obj({"path": S}),
}

# Effective property discovery is separate from the raw XML tree. Values are
# typed by each field descriptor; null plus valueAvailable=false is intentional.
DEFS["EffectiveProperty"] = obj({
    "propertyId": S, "family": S, "type": S, "nativeType": nullable(S), "nativeMember": S,
    "label": nullable(S), "description": nullable(S), "unit": S, "frame": S,
    "source": S, "valueSource": S, "value": {"description":"Typed effective native value, or exact serialized string for xml: fields."},
    "valueAvailable": B, "valueError": S, "defaultValue": {},
    "editability": {"enum":["editable","readOnly","conditional","unsupported","unknown"]},
    "writeOperation": nullable(S), "condition": nullable(S), "verification": S,
    "currentCondition": obj({"satisfied":nullable(B),"reason":nullable(S),"errorCode":nullable(S),"source":S,"meaning":S},
        ["satisfied","reason","errorCode","source","meaning"]),
    "limits": obj({"min":nullable(N),"max":nullable(N),"source":S}),
    "enumValues": nullable(STRINGS), "refresh": STRINGS, "path": S, "attribute": S,
}, ["propertyId","family","type","source","value","valueAvailable","valueSource","editability","writeOperation","unit","frame"])
for _command in ("properties.describe", "properties.get"):
    OUTPUTS[_command] = obj({"identity":nullable(ref("Identity")),"gameVersion":S,"registryVersion":S,
        "parts":arr(obj({"partType":S,"partId":nullable(I),"templatePartId":nullable(I),"total":I,"offset":I,
            "specializedEditors":arr({"oneOf":[
                obj({"family":{"enum":["fuselage","wing","controlSurface"]},"readCommand":{"const":"shape.get"},"writeOperation":{"const":"shape.update"},"schemaCommand":{"const":"shape.schema"},"schemaArgs":obj({"family":S}),"configuration":DYNAMIC,"meaning":S}),
                obj({"family":{"const":"inputControllers"},"readCommand":{"const":"parts.get"},"writeOperation":{"const":"part.update"},"contract":ref("InputControllerEditing")})]}),
            "fields":arr(ref("EffectiveProperty")),"textRendering":nullable(obj({"status":{"enum":["glyphs_available","missing_glyphs","unavailable"]},"font":S,"fontAsset":S,"missingCodePoints":STRINGS,"missingCharacters":STRINGS,"meaning":S,"reason":S},["status"])),"coverage":obj({"discovered":I,"byEditability":{"type":"object","additionalProperties":I},"denominator":S})},["partType","partId","templatePartId","total","offset","fields","coverage"])),
        "valueMeaning":S,"developmentStatus":S})

DEFS.update({
    "Center": obj({"status": {"enum": ["valid", "partial", "unavailable"]}, "quality": S, "method": S,
                   "positionWorldMeters": nullable(V), "positionFrameMeters": nullable(V), "nativeWeightTotal": nullable(N), "weightMeaning": S,
                   "contributorCount": I, "sourceCount": I, "excludedCount": I, "coverage": S, "nativeParity": S, "reasonCodes": STRINGS, "massKg": nullable(N)},
                  ["status", "quality", "method", "positionWorldMeters", "positionFrameMeters", "nativeWeightTotal", "weightMeaning", "contributorCount", "sourceCount", "excludedCount", "coverage", "nativeParity", "reasonCodes"]),
    "CenterRelation": obj({"deltaFrameMeters": described(V, "Named target minus origin in report frame, metres; not force arm or static margin."),
                           "distanceMeters": N, "status": S, "axisRelation": STRINGS, "meaning": S}),
    "CenterWarning": obj({"code": S, "severity": S, "message": S, "relatedPartIds": IDS}),
    "CenterBasis": obj({"mode": S, "loadCondition": S, "liftProjectionAxisWorld": V, "scopePolicy": S,
                        "aircraftOrientationWorld": nullable({"type": "array", "items": N, "minItems": 4, "maxItems": 4}), "massConversion": S, "gameVersion": S}),
    "CenterFrame": obj({"kind": {"enum": ["world", "part"]}, "partId": nullable(I), "referenceToken": nullable(S), "referencePart": ref("PartSummary"),
                        "orientationWorld": {"type": "array", "items": N, "minItems": 4, "maxItems": 4}, "frameToWorldRows": arr(arr(N)), "axisLabels": STRINGS, "orientationBasis": S, "meaning": S},
                       ["kind", "partId", "referenceToken", "orientationWorld", "frameToWorldRows", "axisLabels", "orientationBasis", "meaning"]),
    "CenterContributor": obj({"part": ref("PartSummary"), "metric": {"enum": ["mass", "lift", "thrust"]}, "sourceId": S,
                              "connectedToMainCockpit": B, "activeInHierarchy": B, "included": B, "reasonCodes": STRINGS,
                              "positionWorldMeters": nullable(V), "positionFrameMeters": nullable(V), "nativeWeight": nullable(N), "weightMeaning": S,
                              "nativeWeightFraction": nullable(N), "normalizationBasis": S, "massKg": nullable(N), "massFraction": nullable(N),
                              "offsetFromComMeters": nullable(V), "massMomentAboutComKgM": nullable(V), "projectedAreaSquareMeters": nullable(N), "liftScale": nullable(N),
                              "propulsionType": S, "directionStatus": S, "directionWorld": nullable(V)},
                             ["part", "metric", "sourceId", "connectedToMainCockpit", "activeInHierarchy", "included", "reasonCodes", "positionWorldMeters", "positionFrameMeters", "nativeWeight", "nativeWeightFraction", "normalizationBasis"]),
    "CenterDifference": obj({"beforeMeters": nullable(V), "afterMeters": nullable(V), "deltaMeters": nullable(V), "beforeDistanceMeters": nullable(N), "afterDistanceMeters": nullable(N), "distanceChangeMeters": nullable(N)}, ["beforeMeters", "afterMeters", "deltaMeters"]),
    "CenterComparison": obj({"status": {"enum": ["comparable", "not_comparable"]}, "reasonCodes": STRINGS, "baselineIdentity": ref("Identity"), "currentIdentity": ref("Identity"),
                             "scopeMembershipChanged": B, "meaning": S, "qualityNotice": S,
                             "centerChanges": nullable(obj({k: ref("CenterDifference") for k in ("com", "col", "cot")})),
                             "relativeChanges": nullable(obj({k: ref("CenterDifference") for k in ("colFromCom", "cotFromCom", "cotFromCol")}))}),
    "CentersVisual": deepcopy(OUTPUTS["visual.capture"]),
})
DEFS["CentersReport"] = identified({
    "analysisId": S, "calculationVersion": S, "capturedAt": S, "capturedFrame": I, "geometryStamp": S, "staleAtDelivery": B,
    "basis": ref("CenterBasis"), "frame": ref("CenterFrame"),
    "scope": obj({"assemblyPartCount": I, "connectedPartCount": I, "disconnectedPartCount": I, "connectedPartIds": IDS, "meaning": S}),
    "focus": obj({"status": S, "partIds": nullable(IDS), "meaning": S}),
    "centers": obj({k: ref("Center") for k in ("com", "col", "cot")}),
    "relations": obj({k: nullable(ref("CenterRelation")) for k in ("colFromCom", "cotFromCom", "cotFromCol")}),
    "positionRelationToleranceMeters": N,
    "assessment": obj({"longitudinalStaticStability": obj({"status": {"const": "not_assessed"}, "reasonCodes": STRINGS, "staticMargin": {"type": "null"}}),
                       "trim": obj({"status": {"const": "not_assessed"}, "reasonCodes": STRINGS}),
                       "thrustMoment": obj({"status": {"const": "not_assessed"}, "reasonCodes": STRINGS, "momentNm": {"type": "null"}})}),
    "contributors": obj({"requested": described(B,"True only for detail=contributors. False means rows were not requested, not that there are no contributing sources."), "metric": S,
                         "total": described(I,"Count matching metric/focus before paging, available even in summary mode. Nonzero total with requested=false and returned=0 is expected."),
                         "offset": I, "limit": I, "returned": I, "truncated": B, "nextOffset": nullable(I), "sort": S,
                         "items": described(arr(ref("CenterContributor")),"Per-source rows only when detail=contributors. Invoke sp2model craft centers --detail contributors; --metric alone does not request rows.")}),
    "warnings": arr(ref("CenterWarning")), "visual": nullable(ref("CentersVisual")), "comparison": nullable(ref("CenterComparison"))})
OUTPUTS["craft.centers"] = ref("CentersReport")
OUTPUTS["visual.capture"]["properties"]["centersReport"] = ref("CentersReport")

STRUCTURED_OUTPUTS = {
    "connections.list": identified({"view": {"const": "structured"}, "connections": arr(ref("Connection")), "count": I, "meaning": S}),
    "outputs.list": identified({"view": {"const": "structured"}, "sources": arr(ref("OutputSource")), "sourceCount": I, "meaning": S}),
    "variables.list": identified({"view": {"const": "structured"}, "setters": arr(ref("Setter")), "setterCount": I,
                                   "sources": arr(ref("OutputSource")), "sourceCount": I, "meaning": S}),
}
for _command, _structured in STRUCTURED_OUTPUTS.items():
    _legacy = OUTPUTS[_command]
    _legacy["properties"]["view"] = {"const": "legacy"}
    OUTPUTS[_command] = {"oneOf": [_legacy, _structured],
                         "description": "Default legacy retains XML/legacy field names. --view structured selects typed rows and canonical sources[].modifiers; data.view identifies the mode. Older bridges may omit view on legacy results."}

JSON_VALUE = {"type": ["object", "array", "string", "number", "boolean", "null"]}
JSON_SCHEMA = {"type": ["object", "boolean"], "description": "JSON Schema document; fields depend on the selected command or native family."}
DEFS["InputControllerEditing"] = obj({"element": S, "source": S, "operation": S, "pathPattern": S,
    "minimumPluginVersion": S, "expressionValidation": S,
    "attributes": arr(obj({"name": S, "type": S, "description": S})),
    "commonInputIds": STRINGS, "inputAllowsExpression": B, "invertTypes": STRINGS})
DEFS["CatalogEntry"] = obj({"id": S, "name": S, "description": nullable(S), "category": S,
                            "subcategory": S, "creatable": B, "source": S, "partTypes": STRINGS})
DEFS["CatalogTemplate"] = obj({"id": S, "name": S, "description": nullable(S), "coverage": S, "limitations": STRINGS,
    "parts": arr(obj({"partType": S, "templatePartId": I, "defaultState": ref("XmlNode"), "outputs": arr(ref("PartOutput")),
                      "metadata": arr(obj({"element": S, "childElements": STRINGS, "attributes": arr(obj({
                          "name": S, "type": S, "label": nullable(S), "description": nullable(S),
                          "defaultValue": JSON_VALUE, "min": JSON_VALUE, "max": JSON_VALUE, "enumValues": JSON_VALUE,
                          "optional": B, "readOnly": B}))}))}))})
DEFS["CommandDescriptor"] = obj({"name": S, "entityKind": {"const": "command"}, "invocation": S,
                                 "operationKind": nullable(S), "mutates": B, "schemaQuery": S})
DEFS["CatalogTemplate"]["properties"]["parts"]["items"]["properties"]["toolEditableExtensions"] = arr(ref("InputControllerEditing"))
DEFS["CatalogTemplate"]["properties"]["parts"]["items"]["properties"]["inputControllers"] = arr(ref("InputController"))
DEFS["OperationDescriptor"] = obj({"name": S, "entityKind": {"const": "operation"}, "cliCommands": STRINGS, "schemaQuery": S, "usage": S})
status = obj({"pluginVersion": S, "buildId": S, "gameVersion": S, "designerReady": B, "identity": nullable(ref("Identity")),
              "target": S, "commands": described(STRINGS, "Advertised game-bridge command identifiers, including batch.apply/undo/rollback. This is not the full CLI command list: local commands, operation lifecycle routes, and shortcut aliases such as parts.add are discovered with sp2model commands list. Shortcut writes are translated to batch.apply; omissions here do not mean those CLI commands are unavailable."), "fuselageCrossSectionAttributes": STRINGS, "fuselageStateAttributes": STRINGS,
              "visualInspection": obj({"backend": S, "nativeMaterials": B, "coordinateFrames": STRINGS, "maxGroups": I, "maxParts": I,
                                        "maxTriangles": I, "maxVertices": I, "maxPixels": I, "selectors": STRINGS, "artifactRetentionMinutes": I,
                                        "detailModes": STRINGS, "defaultDetails": S},
                                       ["backend", "nativeMaterials", "coordinateFrames", "maxGroups", "maxParts", "maxTriangles", "maxVertices", "maxPixels", "selectors", "artifactRetentionMinutes"]),
              "geometryRefresh": S, "assemblyDeletion": obj({"supportedRoots": STRINGS, "preview": S, "defaultCascade": B, "recursiveGraphTraversal": B}),
              "partReferencePolicy": S, "limitations": STRINGS},
             ["pluginVersion", "buildId", "gameVersion", "designerReady", "identity", "target", "commands", "limitations"])
funky = obj({"gameVersion": S, "source": S, "trigUnit": S, "evaluated": B,
             "entries": arr(obj({"name": S, "kind": S, "value": JSON_VALUE, "returns": S,
                                 "parameters": arr(obj({"name": S, "type": S})), "description": S}, ["name", "kind"]))})
status["properties"]["inputControllerEditing"] = ref("InputControllerEditing")
status["properties"]["sceneIntegrity"] = nullable(ref("DesignerSceneIntegrity"))
status["properties"]["designerMode"] = {"enum":["standalone","flight","inactive"]}
status["properties"]["acceptanceNative"] = obj({"available": B, "reason": S, "command": S,
    "fixturePrefix": S, "actions": STRINGS, "evidence": S, "desktopInput": B}, ["available"])
status["properties"]["runtimeRetention"] = obj({
    "operationResults": nullable(obj({"retainedResults": I, "compressedBytes": I, "uncompressedJsonBytes": I,
        "budgetBytes": I, "maximumAgeSeconds": N, "expiredByAge": I, "expiredByCapacity": I, "oversizedResults": I, "meaning": S})),
    "managedBytes": I, "checkpointCount": I, "operationHistoryCount": I, "rotationSnapshotCount": I,
    "nativeMeshLifetime": obj({"installed": B, "auditedGameModule": S, "conversions": I, "releases": I, "scope": S}),
    "expressionLifetime": obj({"installed": B, "auditedExpressionModule": S, "scope": S,
        "templates": obj({"count": I, "limit": I, "hits": I, "compiles": I, "fallbacks": I, "evictions": I, "meaning": S})}),
    "nativeUndo": nullable(obj({"count": described(I, "Retained states, including the current state."),
        "maximum": described(I, "Native MaxUndoSteps: undo transition limit, not the retained-state limit."),
        "maximumRetainedStates": described(I, "DLL 0.5.0-dev16+: maximum + 1, because the current state is retained too."),
        "meaning": S, "xmlBytes": I}, ["count", "maximum", "xmlBytes"])),
    "unityMemory": obj({"allocatedBytes": I, "reservedBytes": I, "unusedReservedBytes": I, "monoUsedBytes": I, "monoHeapBytes": I,
        "graphicsDriverAllocatedBytes": described(I, "Unity-reported graphics driver allocation; may be unavailable/zero and overlaps other diagnostics.")},
        ["allocatedBytes", "reservedBytes", "unusedReservedBytes", "monoUsedBytes", "monoHeapBytes"]),
    "meaning": S}, ["operationResults", "managedBytes", "checkpointCount", "operationHistoryCount", "rotationSnapshotCount", "meaning"])
OUTPUTS.update({
    "capabilities": status, "designer.status": status,
    "parts.geometry": identified({"geometry": obj({"partId": I, "coordinateSystem": S,
                           "renderBounds": described({"oneOf": [ref("Bounds"), {"type": "null"}]}, "Whole active owned entity surface world AABB, union of native renderer bounds; already includes hierarchy transforms, may conservatively enclose actual vertices."),
                           "renderBoundsMeaning": S, "renderBoundsMembers": arr(I), "rendererExclusions": arr(obj({})),
                           "geometryStamp": S, "geometryStampKind": S, "colliderMeaning": S,
                           "renderers": arr(obj({"name": S, "bounds": ref("Bounds")})),
                           "colliders": arr(obj({"name": S, "type": S, "layer": I, "bounds": ref("Bounds")})),
                           "editorColliders": arr(obj({"bounds": ref("Bounds"), "includeInBounds": B}))},
                           ["partId", "coordinateSystem", "renderers", "colliders", "editorColliders"])}),
    "symmetry.get": identified({"configuration": obj({"mode": S, "mirrorPlaneNormal": V,
                        "mirrorPlaneDistance": described(N, "Plane coefficient in dot(normal, worldPosition) + distance = 0; it is not the plane's X coordinate."),
                        "radialAxis": V, "radialOrigin": V, "disabledForNewParts": B,
                        "basis": described(S,"DLL 0.4.4+: effective frame from current main-control pose and aircraft mirror offset; read-only derivation."),
                        "originPartId": I, "aircraftMirrorPlaneOffset": N, "planeEquation": S, "nativeCacheStale": B,
                        "nativeCachedFrame": obj({"mirrorPlaneNormal":V,"mirrorPlaneDistance":N,"radialAxis":V,"radialOrigin":V}), "meaning": S},
                        ["mode","mirrorPlaneNormal","mirrorPlaneDistance","radialAxis","radialOrigin","disabledForNewParts"]),
                        "groups": arr(obj({"id": I, "parts": arr(obj({"id": I, "enabled": B, "type": S}))})),
                        "part": nullable(ref("Part")), "propagation": S}),
    "catalog.categories": obj({"gameVersion": S, "categories": arr(obj({"id": S, "name": S, "count": I}))}),
    "catalog.subcategories": obj({"category": S, "subcategories": arr(obj({"id": S, "name": S, "count": I}))}),
    "catalog.list": obj({"gameVersion": S, "listing": page(ref("CatalogEntry"))}),
    "catalog.search": obj({"gameVersion": S, "listing": page(ref("CatalogEntry"))}),
    "catalog.get": ref("CatalogEntry"),
    "catalog.schema": obj({"gameVersion": S, "dataSource": S, "templates": arr(ref("CatalogTemplate"))}),
    "catalog.export": obj({"gameVersion": S, "generatedAt": S, "entries": arr(ref("CatalogEntry")),
                           "schemas": arr({"anyOf": [ref("CatalogTemplate"), obj({"id": S, "error": ref("AnyResult")})]})}),
    "funky.list": funky, "funky.describe": funky,
    "instances.list": obj({"instances": arr(obj({"baseUrl": S, "pid": I, "instanceId": S, "pluginVersion": S, "protocolVersion": S}))}),
    "commands.list": obj({"commands": STRINGS, "operationKinds": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": {"type": ["string", "array"]}}},
                          "commandDetails": arr(ref("CommandDescriptor")), "operationDetails": arr(ref("OperationDescriptor"))}),
    "commands.schema": obj({"command": S, "entityKind": {"enum": ["command", "operation"]}, "contractVersion": S,
                            "operationKind": nullable(S), "inputSchema": JSON_SCHEMA, "outputSchema": nullable(JSON_SCHEMA),
                            "outputSchemaCoverage": S, "requestId": S, "compatibility": S,
                            "asyncOutputSchema": JSON_SCHEMA, "savedOutputSchema": JSON_SCHEMA, "outputModes": MAP,
                            "resultSchema": JSON_SCHEMA, "cliCommands": STRINGS, "schemaQuery": S, "usage": S, "legacyQuery": B},
                           ["command", "entityKind", "contractVersion", "inputSchema"]),
})
for name in ("knowledge.catalog", "knowledge.funky", "knowledge.complex"):
    OUTPUTS[name] = obj({"dataSource": S, "knowledge": {**JSON_VALUE, "description": "Versioned offline knowledge dataset, not current aircraft state or a writable-field allowlist."}})


def with_defs(document):
    """Return only reachable shared definitions, keeping schema queries small."""
    needed = {}
    def visit(node):
        if isinstance(node, dict):
            link = node.get("$ref", "")
            if link.startswith("#/$defs/"):
                key = link.removeprefix("#/$defs/")
                if key not in needed:
                    needed[key] = deepcopy(DEFS[key])
                    visit(needed[key])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(document)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **document, "$defs": needed}


def envelope(data):
    return with_defs({
            **obj({"success": B, "schemaVersion": S, "data": data, "error": ref("Error"),
                   "operationId": S, "instancePid": I, "rollbackResult": ref("Rollback"), "identity": ref("Identity")}, ["success", "schemaVersion"]),
            "oneOf": [{"properties": {"success": {"const": True}}, "required": ["data"]},
                      {"properties": {"success": {"const": False}}, "required": ["error"]}]})


Q = {"type":"array", "items":N, "minItems":4, "maxItems":4}
DEFS["Pose"] = obj({"position":V,"rotationQuaternion":Q})
DEFS["NativeDisplayState"] = obj({"isDisconnected":B,"isHidden":B,"isHighlighted":B,"overrideMaterialPresent":B,"customMaterialPresent":B,"meaning":S})
OUTPUTS["designer.capture"]["properties"]["nativeDisplayOverrides"] = arr({"allOf":[ref("NativeDisplayState"),obj({"partId":I})]})
DEFS["FieldDiff"] = obj({"totalChanges":I,"truncated":B,"comparison":S,"changes":arr(obj({"path":S,"before":nullable(S),"after":nullable(S)}))})
DEFS["Material"] = obj({"id":I,"name":nullable(S),"reserved":B,"style":S,"metallic":N,"smoothness":N,"emissionDay":N,"emissionNight":N,
    "colors":arr(obj({"index":I,"rgba":Q,"metallic":nullable(N),"smoothness":nullable(N),"emissionDay":nullable(N),"emissionNight":nullable(N)})),
    "textureId":nullable(S),"texturePresetId":nullable(S),"textureBlend":N,"textureOffset":V,"textureRotation":V,"textureScale":V,"textureWrapMode":STRINGS})
DEFS["RigidGroup"] = obj({"partIds":IDS,"nativeDependencies":arr(obj({"partId":I,"hostPartId":I,"bothIncluded":B,"kind":S})),
    "externalConnections":arr(obj({"partA":I,"partB":I})),"targetReferences":arr(obj({"partId":I,"targeting":ref("XmlNode")})),"meaning":S})
OUTPUTS.update({
    "craft.diff":identified({"checkpointId":S,"diff":ref("FieldDiff")}),
    "appearance.get":identified({"themeName":S,"globalCustomThemeFingerprint":S,"palette":arr(ref("Material")),"editablePaletteCapacity":I,"totalParts":I,"offset":I,
        "parts":arr(obj({"partId":I,"designerDisplayState":ref("NativeDisplayState"),"slots":arr(obj({"slot":I,"materialId":I,"assignable":B}))},["partId","slots"])),"capturedFrame":I,"scope":S},["themeName","globalCustomThemeFingerprint","palette","editablePaletteCapacity","totalParts","offset","parts","scope"]),
    "resources.list":identified({"category":S,"total":I,"offset":I,"items":arr(obj({"id":S,"name":nullable(S),"category":nullable(S),"paintStyle":S,"available":B,"aspectRatio":N,
        "presets":arr(obj({"id":S,"name":nullable(S)})),"propertyId":S,"values":STRINGS,"condition":nullable(S)},[]))}),
    "groups.resolve": {"allOf":[ref("RigidGroup"),identified({"groupId":S,"lifetime":S})]},
    "decal.pose.get":identified({"partId":I,"partPose":ref("Pose"),"projectorPose":ref("Pose"),"projectorPositionInPart":V,"projectorRotationInPart":Q,"projectorLocalBox":obj({"min":V,"max":V}),"projectorToWorldRows":arr(arr(N)),"meaning":S},["partId","partPose","projectorPose","projectorPositionInPart","projectorRotationInPart","meaning"]),
})
_distance = obj({"distanceMetres":N,"pointA":V,"pointB":V,"partA":I,"partB":I,"triangleA":I,"triangleB":I,"normalA":V,"normalB":V,"signedDistance":{"type":"null"},"penetrationDepth":{"type":"null"},"meaning":S})
_section = obj({"segmentCount":I,"totalLengthMetres":N,"coplanarTrianglesExcluded":I,"degenerateTrianglesExcluded":I,"truncated":B,
    "segments":arr(obj({"a":V,"b":V,"normal":V,"partId":I})),"interpretation":S})
_seam = obj({"sampledMaxMetres":N,"rmsMetres":N,"sampleCount":I,"sampleSpacingMetres":N,"maxUnorientedNormalAngleDegrees":N,"continuousUpperBound":{"type":"null"},"meaning":S,
    "witnesses":arr(obj({"direction":S,"point":V,"nearest":V,"distanceMetres":N,"normalAngleDegrees":N,"partId":I,"otherPartId":I})),"sectionA":_section,"sectionB":_section})
_symmetry = obj({"sampledMaxMetres":N,"rmsMetres":N,"sampleCount":I,"sampleSpacingMetres":N,"maxUnorientedNormalAngleDegrees":{"type":["number","null"]},"normalSampleCount":I,"ambiguousNormalSampleCount":I,"normalPolicy":S,"continuousUpperBound":{"type":"null"},"meaning":S,
    "worstSamples":arr(obj({"direction":S,"sourcePoint":V,"reflectedPoint":V,"nearestPoint":V,"distanceMetres":N,"unorientedNormalAngleDegrees":{"type":["number","null"]},"normalStatus":S,"sourcePartId":I,"targetPartId":I}))})
for _cmd,_measurement in (("geometry.measure",_distance),("geometry.section",_section),("geometry.seam",_seam),("geometry.symmetry",_symmetry)):
    OUTPUTS[_cmd]=identified({"sampleId":S,"capturedFrame":I,"staleAtDelivery":B,"source":S,"frame":obj({"kind":S,"partId":I,"position":V,"rotationQuaternion":Q},["kind"]),"frameToWorldRows":arr(arr(N)),"units":S,
        "geometryStamp":S,"triangleCount":I,"vertexCount":I,"complete":B,"exclusions":arr(obj({"partId":I,"reason":S,"renderer":S,"type":S,"count":I},["partId","reason"])),
        "sources":arr(obj({"partId":I,"renderer":S,"capturedTriangles":I,"excludedNonfiniteTriangles":I},["partId","capturedTriangles"])),"measurement":{"oneOf":[_measurement,obj({"status":{"const":"unavailable"},"reason":S})]},"accuracy":S,"cachePolicy":S})
DEFS["Change"]["properties"].update({"effectiveMaterial":ref("Material"),"effectivePoses":arr(obj({"partId":I,"pose":ref("Pose")})),"affectedPartIds":IDS,
    "effectiveChanges":arr(obj({"propertyId":S,"requested":{},"effective":{},"normalizationReason":nullable(S)}))})
MUTATION["properties"].update({"stageTimings":{"type":"object","additionalProperties":N},"rebuildCount":I,"effectiveChanges":ref("FieldDiff")})
DEFS["Rollback"]["properties"].update({"fingerprintIdentical":nullable(B),"currentFingerprint":nullable(S),"readBack":B})
_retained_cache = arr(obj({"partId":I,"modifierIndex":I,"field":S,"checkpointValue":S,"regeneratedValue":S,"meaning":S}))
DEFS["Validation"]["properties"]["retainedNativeCaches"] = _retained_cache
DEFS["Rollback"]["properties"]["retainedNativeCaches"] = _retained_cache

def output_schema(command):
    if command=='craft.status':return envelope(obj({'name':nullable(S),'identity':nullable(ref('Identity')),'partCount':I,'connectionCount':I,'designerReady':B,'pluginVersion':S,'sdkVersion':S,'buildId':S,'detail':{'const':'summary'}}))
    if command=='parts.query':return envelope(identified({'name':S,'items':arr(obj({'id':I},['id'])),'total':I,'returned':I,'offset':I,'limit':I,'hasMore':B,'truncationReason':nullable(S),'allowedFields':STRINGS}))
    if command=='native.state':return envelope(identified({'partId':I,'state':ref('XmlNode'),'metadata':arr(DYNAMIC),'source':S,'unknownAttributePolicy':S,'attributeOperations':STRINGS,'emptyValuePolicy':S,'nodeOperations':DYNAMIC,'structuralOperations':DYNAMIC}))
    if command=='mechanical.get':return envelope(identified({'partId':I,'family':{'const':'driveShaft'},'endpoints':arr(ref('AttachPoint')),'endpointDistanceMetres':N,'radiusMultiplier':N,'bootA':B,'bootB':B,'source':S,'limits':DYNAMIC}))
    if command=='wing.stations':return envelope(identified({'partId':I,'spanMetres':N,'stations':arr(DYNAMIC),'source':S,'meaning':S,'flipped':B}))
    if command=='airfoils.describe':return envelope(obj({'source':S},['source']))
    if command=='model.dependencies':return envelope(identified({'selectedPartIds':IDS,'connections':arr(DYNAMIC),'nativeGroups':DYNAMIC,'symmetryCandidates':IDS,'requiredWritableCandidates':IDS,'completeness':S,'unknownDynamicCallbacks':B,'writableExpanded':{'const':False},'meaning':S}))
    if command=='logic.dependencies':return envelope(identified({'variable':nullable(S),'declarations':arr(DYNAMIC),'references':arr(DYNAMIC),'parseFailures':arr(DYNAMIC),'duplicateProviders':arr(DYNAMIC),'possibleCycles':arr(STRINGS),'source':S,'unknownExpressionFields':B,'coverage':S,'migration':S}))
    if command=='craft.checkpoint.prune':return envelope(identified({'deletedIds':STRINGS,'capacity':DYNAMIC}))
    if command == "designer.control":
        from .designer_control import output_data_schema
        return envelope(output_data_schema())
    if command == "designer.crafts":
        return envelope(obj({"total":I,"offset":I,"items":arr(obj({"craftId":S,"name":nullable(S),"subdirectory":S})),"scope":S}))
    if command == "acceptance.native":
        from acceptance_contracts import output_data_schema
        return envelope(output_data_schema())
    if command in ("operation.wait", "operation.result"):
        return with_defs({**ref("AnyResult"), "description": "Completed result of the originally submitted command. Its exact data schema is that command's outputSchema, not a Job wrapper."})
    return envelope(deepcopy(OUTPUTS[command])) if command in OUTPUTS else None


def auxiliary_schemas():
    return {"asyncOutputSchema": envelope(ref("Job")),
            "savedOutputSchema": envelope(obj({"path": S, "sha256": S, "resultSuccess": B})),
            "outputModes": {"outputSchema": "Completed command result, also the content written to --output.",
                            "asyncOutputSchema": "--async acknowledgement; query operation result for completion.",
                            "savedOutputSchema": "stdout receipt when --output is supplied."}}
