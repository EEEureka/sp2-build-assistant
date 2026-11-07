"""Independent checks on captured native triangles, never the plan's proxy mesh."""
from __future__ import annotations
import hashlib
import json
import math
from .errors import ModelingError
from .geometry import add, sub, dot, cross, scale, magnitude, rotate, rotation_distance_degrees


def _same(a,b):
    return all(a.get(k)==b.get(k) for k in ("craftSessionId","revision","fingerprint"))


def _local(point,part):
    x,y,z,w=part["rotationQuaternion"]
    return rotate((-x,-y,-z,w),sub(point,part["position"]))


def section_bounds(triangles,axis,offset,tolerance=1e-8):
    """Finite mesh/plane intersections, excluding wholly coplanar triangles."""
    normal={"x":0,"y":1,"z":2}[axis]
    uv={"x":(2,1),"y":(0,2),"z":(0,1)}[axis]
    points=[]
    for triangle in triangles:
        values=[p[normal]-offset for p in triangle]
        if all(abs(v)<=tolerance for v in values):
            continue
        for i in range(3):
            a,b=triangle[i],triangle[(i+1)%3]
            da,db=values[i],values[(i+1)%3]
            if abs(da)<=tolerance:
                points.append(a)
            if da*db<0:
                points.append(add(a,scale(sub(b,a),da/(da-db))))
    if not points:
        return None
    return tuple(max(p[j] for p in points)-min(p[j] for p in points) for j in uv)


def _ray_hit(point,direction,triangle):
    a,b,c=triangle
    e1,e2=sub(b,a),sub(c,a)
    h=cross(direction,e2)
    det=dot(e1,h)
    if abs(det)<1e-12:
        return None
    s=sub(point,a)
    u=dot(s,h)/det
    if u < -1e-9 or u > 1+1e-9:
        return None
    q=cross(s,e1)
    v=dot(direction,q)/det
    if v < -1e-9 or u+v>1+1e-9:
        return None
    t=dot(e2,q)/det
    return t if t>=-1e-9 else None


def point_inside(triangles,point,tolerance=1e-5):
    """Three finite rays with duplicate-face hit consolidation; ambiguity is explicit."""
    parity=[]
    for direction in ((1,.317,.217),(.193,1,.419),(.271,.137,1)):
        values=sorted(t for tri in triangles if (t:=_ray_hit(point,direction,tri)) is not None)
        if values and values[0]<tolerance:
            return None
        unique=[]
        for t in values:
            if not unique or abs(t-unique[-1])>tolerance:
                unique.append(t)
        parity.append(len(unique)%2==1)
    return parity[0] if len(set(parity))==1 else None


def mesh_topology(triangles,tolerance=1e-5):
    edges={}
    degenerate=0
    for triangle in triangles:
        keys=[tuple(round(value/tolerance) for value in p) for p in triangle]
        if len(set(keys))<3 or magnitude(cross(sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0])))<=1e-12:
            degenerate+=1
            continue
        for i in range(3):
            edge=tuple(sorted((keys[i],keys[(i+1)%3])))
            edges[edge]=edges.get(edge,0)+1
    return {"closed":bool(edges) and all(count==2 for count in edges.values()),
            "weldToleranceMetres":tolerance,"triangleCount":len(triangles),"degenerateTriangleCount":degenerate,
            "weldedEdgeCount":len(edges),"nonTwoIncidentEdgeCount":sum(count!=2 for count in edges.values()),
            "scope":"Finite native triangle edge incidence after coordinate welding; not a proof of an ideal continuous solid."}


def closed_mesh(triangles,tolerance=1e-5):
    return mesh_topology(triangles,tolerance)["closed"]


def cap_endpoints(points):
    """Actual local-Z end-cap bounds centers for certified straight fuselages."""
    if not points:return None
    ends=[]
    for z in (min(p[2] for p in points),max(p[2] for p in points)):
        cap=[p for p in points if abs(p[2]-z)<=1e-5]
        ends.append(tuple((min(p[i] for p in cap)+max(p[i] for p in cap))/2 for i in (0,1))+(z,))
    return ends


def native_mesh_data(session,ids,identity,*,vertex_attributes=None):
    session._fresh(identity)
    extra={}
    if vertex_attributes is not None:
        if not isinstance(vertex_attributes,(list,tuple)) or not vertex_attributes or any(x not in ('normals','tangents') for x in vertex_attributes) or len(set(vertex_attributes))!=len(vertex_attributes):
            raise ModelingError('invalid_vertex_attributes','Use unique normals and/or tangents')
        extra['vertexAttributes']=list(vertex_attributes)
    sample=session.client.call("geometry.section",{"craftSessionId":identity["craftSessionId"],"expectedRevision":identity["revision"],
        "partIds":sorted(set(ids)),"frame":{"kind":"world"},"plane":{"origin":[0,0,0],"normal":[0,0,1]},"export":True,"exportMeshes":True,**extra})
    raw=session.client.artifact(sample["captureId"],"meshes.json")
    digest=next(x["sha256"] for x in sample["files"] if x["name"]=="meshes.json")
    if hashlib.sha256(raw).hexdigest().lower()!=digest.lower():
        raise ModelingError("artifact_mismatch","Native mesh artifact hash differs from its receipt.")
    data=json.loads(raw)
    if sample["staleAtDelivery"] or not _same(sample["identity"],identity) or not _same(data["identity"],identity):
        raise ModelingError("stale_evidence","Native geometry sample no longer matches the requested state.")
    return sample,data


def native_meshes(session,ids,identity):
    sample,data=native_mesh_data(session,ids,identity)
    triangles={id:[] for id in ids}
    vertices={id:[] for id in ids}
    for mesh in data["meshes"]:
        points=mesh["vertices"]
        vertices[mesh["partId"]].extend(points)
        indices=mesh["indices"]
        for i in range(0,len(indices),3):
            triangles[mesh["partId"]].append(tuple(points[indices[i+j]] for j in range(3)))
    return sample,vertices,triangles


def verify_receipt(session,receipt):
    report = verify_targets(session, receipt.identity, receipt.plan["expectations"], receipt.result.get("temporaryIds",{}))
    report["verificationSource"] = "execution_receipt"
    return report


def verify_plan(session,plan):
    from .plan import Plan
    if not isinstance(plan,Plan) or plan.session is not session:
        raise ModelingError("invalid_check_plan","Use a current expectation-only plan from this Session.")
    document=plan.to_dict()
    if document["operations"] or document["objects"]:
        raise ModelingError("check_requires_read_only_plan","check cannot execute or ignore pending mutations. Apply them explicitly, or create a separate expectation-only plan.")
    if not _same(document["baselineIdentity"],session.identity):
        raise ModelingError("revision_conflict","Check baseline changed. Inspect and declare new targets explicitly.")
    session._fresh(document["baselineIdentity"])
    report=verify_targets(session,document["baselineIdentity"],document["expectations"],{})
    report["verificationSource"]="read_only_plan"
    return report


def verify_targets(session,identity,targets,mapping):
    def ref(value):
        return mapping.get(value) if isinstance(value,str) else value
    ids={ref(t["part"]) for t in targets}
    ids.update(ref(p) for target in targets for p in target.get("connectedTo",[]))
    if None in ids:
        raise ModelingError("missing_binding","An expectation refers to a retired or missing temporary object.")
    if not ids:
        return {"status":"not_assessed","checks":[],"reason":"No declared targets."}
    sample,vertices,triangles=native_meshes(session,ids,identity)
    parts={}
    for id in ids:
        detail=session.client.call("parts.get",{"id":id})
        if not _same(detail["identity"],identity):
            raise ModelingError("stale_evidence","Native state changed during target verification.")
        parts[id]=detail["part"]
    checks=[]
    solid_evidence={}
    def check(id,name,requested,actual,error,tolerance):
        checks.append({"partId":id,"target":name,"requested":requested,"actual":actual,"error":error,"tolerance":tolerance,
                       "status":"passed" if error<=tolerance else "failed"})
    for target in targets:
        id=ref(target["part"])
        part=parts[id]
        tolerance=target.get("toleranceMetres",.002)
        local_points=[_local(p,part) for p in vertices[id]]
        local_triangles=[tuple(_local(p,part) for p in tri) for tri in triangles[id]]
        excluded_ids={row.get("partId") for row in sample["exclusions"]}
        complete=id not in excluded_ids and bool(local_points) and bool(local_triangles)
        dimensions=[max(p[i] for p in local_points)-min(p[i] for p in local_points) for i in range(3)] if local_points else None
        for key,axis in (("lengthMetres",2),("spanMetres",0)):
            if key in target:
                if complete:
                    check(id,key,target[key],dimensions[axis],abs(dimensions[axis]-target[key]),tolerance)
                else:
                    checks.append({"partId":id,"target":key,"status":"incomplete","reason":"Missing or excluded native surfaces."})
        if "dimensionsMetres" in target:
            if complete:
                error=max(abs(a-b) for a,b in zip(dimensions,target["dimensionsMetres"]))
                check(id,"dimensionsMetres",target["dimensionsMetres"],dimensions,error,tolerance)
            else:
                checks.append({"partId":id,"target":"dimensionsMetres","status":"incomplete"})
        if "positionWorldMetres" in target:
            error=magnitude(sub(part["position"],target["positionWorldMetres"]))
            check(id,"positionWorldMetres",target["positionWorldMetres"],part["position"],error,tolerance)
        if "endpointsWorldMetres" in target:
            endpoints=cap_endpoints(local_points) if complete and part["type"] in ("JFuselage-1","JFuselage-Cone-1","JFuselage-2") else None
            if endpoints is None:
                checks.append({"partId":id,"target":"endpointsWorldMetres","status":"incomplete","reason":"Complete certified straight-fuselage end-cap evidence required."})
            else:
                actual=[add(part["position"],rotate(part["rotationQuaternion"],point)) for point in endpoints]
                error=max(magnitude(sub(wanted,point)) for wanted,point in zip(target["endpointsWorldMetres"],actual))
                check(id,"endpointsWorldMetres",target["endpointsWorldMetres"],actual,error,tolerance)
        if "rotationQuaternion" in target:
            error=rotation_distance_degrees(part["rotationQuaternion"],target["rotationQuaternion"])
            check(id,"rotationDegrees",target["rotationQuaternion"],part["rotationQuaternion"],error,target.get("toleranceDegrees",.01))
        for section in target.get("sections",[]):
            actual=section_bounds(local_triangles,section["axis"],section["offsetMetres"]) if complete else None
            if actual is None:
                checks.append({"partId":id,"target":"section","status":"incomplete","section":section,"reason":"No noncoplanar native intersection."})
            else:
                wanted=(section["widthMetres"],section["heightMetres"])
                check(id,"section",section,list(actual),max(abs(a-b) for a,b in zip(actual,wanted)),section.get("toleranceMetres",tolerance))
        for connected in target.get("connectedTo",[]):
            destination=ref(connected)
            actual=destination in part["connectedPartIds"] and id in parts[destination]["connectedPartIds"]
            check(id,"nativeConnection",destination,actual,0 if actual else 1,0)
        for probe in target.get("probes",[]):
            if id not in solid_evidence:solid_evidence[id]=mesh_topology(triangles[id])
            actual=point_inside(triangles[id],probe["pointWorldMetres"],probe.get("toleranceMetres",1e-5)) if complete and solid_evidence[id]["closed"] else None
            if actual is None:
                checks.append({"partId":id,"target":"solidProbe","status":"incomplete","probe":probe,"reason":"Missing surfaces, boundary or inconsistent mesh ray parity."})
            else:
                check(id,"solidProbe",probe["inside"],actual,0 if actual==probe["inside"] else 1,0)
    status="not_assessed" if not checks else "failed" if any(c["status"]=="failed" for c in checks) else "incomplete" if any(c["status"]=="incomplete" for c in checks) else "passed"
    return {"status":status,"identity":identity,"checks":checks,"sampleId":sample["sampleId"],"geometryStamp":sample["geometryStamp"],"solidMeshEvidence":solid_evidence,
            "exclusions":sample["exclusions"],"visualStatus":"not_assessed","scope":"Explicit native triangle extents, finite plane sections, rigid poses, topology and finite solid probes. No ideal-surface or aesthetic claim."}
