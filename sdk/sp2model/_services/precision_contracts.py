"""Typed precision-edit request shapes; effective property values come from discovery."""
from copy import deepcopy

def enrich(command, schema):
    p=schema["properties"]
    n={"type":"number"}
    v={"type":"array","minItems":3,"maxItems":3,"items":n}
    q={"type":"array","minItems":4,"maxItems":4,"items":n,"description":"Quaternion x,y,z,w; finite nonzero, normalized before use. q and -q are equivalent."}
    def obj(fields, required=()):
        return {"type":"object","properties":fields,"required":list(required),"additionalProperties":False}
    frame={"oneOf":[obj({"kind":{"const":"world"}},["kind"]),obj({"kind":{"const":"craft"}},["kind"]),
        obj({"kind":{"const":"part"},"partId":{"type":"integer","minimum":0}},["kind","partId"]),
        obj({"kind":{"const":"custom"},"position":v,"rotationQuaternion":q},["kind","position","rotationQuaternion"])],
        "description":"Rigid frame frozen at operation start; metres. craft uses main control Part pose; existing nonuniform Part scale does not scale the frame."}
    for key in ("position","translation","pivot","offset"):
        if key in p:p[key]=deepcopy(v)
    if "rotationQuaternion" in p:p["rotationQuaternion"]=q
    if "frame" in p:p["frame"]=frame
    for key in ("partIds","partIdsA","partIdsB"):
        if key in p:p[key].update(minItems=1,maxItems=2048,uniqueItems=True,items={"type":["integer","string"] if command.startswith("transform.") or command=="appearance.set" else "integer"})
    if "limit" in p:p["limit"].update(minimum=1,maximum=2048 if command=="appearance.get" else 1000)
    if "offset" in p and command not in ("transform.align",):p["offset"].update(minimum=0)
    if command.startswith("transform."):
        schema["oneOf"]=[{"required":["partIds"]},{"required":["groupId"]}]
        p["symmetric"]["default"]=False
    if command=="transform.apply":
        p["mode"]["enum"]=["delta","absolute"]
        schema["description"]="Rigid group change, no scaling or implicit BFS. delta: p'=pivot+Q*(p-pivot)+translation, R'=Q*R. Absolute sets the anchor's pose and preserves group offsets. Missing host/dependent pairs are rejected."
        schema["allOf"]=[{"if":{"properties":{"mode":{"const":"absolute"}}},"then":{"required":["position","rotationQuaternion"],"not":{"anyOf":[{"required":["pivot"]},{"required":["translation"]}]}},"else":{"not":{"required":["position"]}}}]
    if command=="transform.align":
        schema["dependentRequired"]={"sourcePointId":["targetPointId"],"targetPointId":["sourcePointId"]}
        p["axis"].update(enum=["opposedNormals","jointAxes"],default="opposedNormals")
        p["offset"]["description"]="Metres in the target Part's rigid local axes. Shortest axis rotation; creates no connection."
    if command=="appearance.set":
        p["mode"]["enum"]=["assign","clone","shared"]
        p["slots"].update(minItems=1,uniqueItems=True,items={"type":"integer","minimum":0})
        finish={k:{"type":"number","minimum":0,"maximum":5 if k.startswith("emission") else 1} for k in ("metallic","smoothness","emissionDay","emissionNight")}
        color=obj({"index":{"type":"integer","minimum":0,"maximum":3},"rgba":{**q,"items":{"type":"number","minimum":0,"maximum":1}},
            **{k:{"anyOf":[value,{"type":"null"}]} for k,value in finish.items()}},["index"])
        p["patch"]=obj({"name":{"type":"string"},"style":{"enum":["SolidColor","SinglePlaneTextureColorMask","TriPlaneTextureColorMask"]},
            **finish,"colors":{"type":"array","minItems":1,"maxItems":4,"items":color},"textureId":{"type":"string"},"texturePresetId":{"type":"string"},
            "textureBlend":{"type":"number","minimum":0,"maximum":1},"textureOffset":v,"textureRotation":v,"textureScale":{**v,"items":{"type":"number","minimum":.0001,"maximum":10000}},
            "textureWrapMode":{"type":"array","minItems":3,"maxItems":3,"items":{"enum":["Repeat","Clamp","Mirror","MirrorOnce"]}}})
        schema["allOf"]=[{"if":{"properties":{"mode":{"const":"shared"}}},"then":{"required":["patch"],"not":{"anyOf":[{"required":["partIds"]},{"required":["slots"]}]}},"else":{"required":["partIds","slots"]}}]
        schema["description"]="Current craft palette only; clone changes selected slots, shared explicitly changes all users of materialId. Reserved materials/slots cannot be assigned. RGBA is serialized by native RGBA8, with effective values returned."
    if command=="resources.list":
        p["category"]["enum"]=["textures","decals","propertyChoices"]
        schema["allOf"]=[{"if":{"properties":{"category":{"const":"propertyChoices"}}},"then":{"required":["partId"]}}]
    if command=="groups.resolve":
        from .visual import schema as visual_schema
        p["selector"]=deepcopy(visual_schema("visual.resolve")["properties"]["groups"]["items"]["properties"]["selector"])
    if command.startswith("geometry."):
        p['vertexAttributes']={'type':'array','minItems':1,'maxItems':2,'uniqueItems':True,'items':{'enum':['normals','tangents']},'description':'Optional actual final render attributes. Requires exportMeshes:true and source renderMesh; inverse-transpose normals, native winding preserved with parity. Budget 250000 vertices.'}
        p["exportMeshes"].update(default=False,description="Requires export:true. Save same-sample indexed triangles as meshes.json for independent local verification; does not include native textures or paint.")
        schema["allOf"]=[{"if":{"required":["exportMeshes"],"properties":{"exportMeshes":{"const":True}}},"then":{"required":["export"],"properties":{"export":{"const":True}}}}]
        schema['allOf'].append({'if':{'required':['vertexAttributes']},'then':{'required':['exportMeshes'],'properties':{'exportMeshes':{'const':True},'source':{'const':'renderMesh'}}}})
        p["plane"]=obj({"origin":v,"normal":v},["origin","normal"])
        p["region"]=obj({"min":v,"max":v},["min","max"])
        p["sampleSpacingMetres"].update(minimum=.00001,maximum=1,default=.001)
        p["source"]={"enum":["renderMesh","collider"],"default":"renderMesh","description":"Collider source supports exact readable nonconvex MeshCollider and BoxCollider; convex hulls, spheres and capsules are explicitly excluded."}
        schema["description"]="Immutable native geometry sampled at a captured frame. Unsigned distance is not penetration depth. Sections are unordered segments; seam and symmetry maxima apply to sampled points, not a continuous bound. Unavailable surfaces are reported with exclusions."
    return schema
