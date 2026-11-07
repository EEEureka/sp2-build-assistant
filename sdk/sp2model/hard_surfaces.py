"""Bounded native plane cuts and complete convex-face shading checks.

No game writes occur in this module. Cuts become ordinary scoped Hole plans;
measurements consume immutable captured attributes, never invented normals.
"""
import math
from copy import deepcopy
from .errors import ModelingError
from .geometry import vector,unit,dot,sub,add,scale,cross,look_rotation,rotate,number


def plane_cut(origin,normal,bounds_min,bounds_max,*,max_cutters=16,padding_m=.002):
    """Tile the positive half-space inside an explicit finite target AABB.

    All dimensions are metres in the plan frame. The lower local-Z face of
    every native Hole coincides with the plane; tiling is tangential only.
    """
    o=vector(origin,'plane origin');n=unit(normal,'outward plane normal')
    lo=vector(bounds_min,'bounds_min');hi=vector(bounds_max,'bounds_max')
    if any(a>=b for a,b in zip(lo,hi)):raise ModelingError('invalid_cut_bounds','Bounds must have positive size on every axis')
    if type(max_cutters) is not int or not 1<=max_cutters<=64:raise ModelingError('cut_budget','max_cutters must be 1..64')
    pad=number(padding_m,'padding_m',.0001,.1)
    up=(0,1,0) if abs(n[1])<.9 else (1,0,0)
    q=look_rotation(n,up);inv=(-q[0],-q[1],-q[2],q[3])
    corners=[(x,y,z) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
    local=[rotate(inv,sub(c,o)) for c in corners]
    a=[min(c[i] for c in local) for i in range(3)];b=[max(c[i] for c in local) for i in range(3)]
    if a[2]>=-1e-7 or b[2]<=1e-7:raise ModelingError('nonintersecting_cut','Plane must cross the declared target bounds; positive half-space is removed')
    depth=b[2]+pad
    if not .01<=depth<=10:raise ModelingError('unsupported_cut_depth','Native Hole depth must be .01..10m; partition the target explicitly',{'requiredDepthMetres':depth})
    a=[a[i]-pad for i in range(2)];b=[b[i]+pad for i in range(2)]
    counts=[max(1,math.ceil((b[i]-a[i])/(10-2*pad))) for i in range(2)]
    count=counts[0]*counts[1]
    if count>max_cutters:raise ModelingError('cut_budget','Increase explicit cutter budget or partition the target',{'requiredCutters':count,'budget':max_cutters})
    cuts=[]
    for x in range(counts[0]):
        for y in range(counts[1]):
            intervals=[]
            for i,k in enumerate((x,y)):
                step=(b[i]-a[i])/counts[i]
                intervals.append((a[i]+step*k-(pad if k else 0),a[i]+step*(k+1)+(pad if k+1<counts[i] else 0)))
            center=[sum(v)/2 for v in intervals]+[depth/2]
            size=[v[1]-v[0] for v in intervals]+[depth]
            if min(size)<.01 or max(size)>10+1e-9:raise ModelingError('unsupported_cut_size','Native cutter dimensions must be .01..10m')
            cuts.append({'position':list(add(o,rotate(q,center))),'rotationQuaternion':list(q),'sizeMetres':size})
    return {'origin':list(o),'normal':list(n),'bounds':{'min':list(lo),'max':list(hi)},'removedHalfSpace':'dot(point-origin,normal)>0',
            'cutters':cuts,'cutterCount':count,'surfaceStatus':'requires_native_measurement','paddingMetres':pad}


def append_plane_cut(plan,name,targets,origin,normal,bounds_min,bounds_max,*,max_cutters=16,padding_m=.002):
    # Public Plan lengths are in plan units; previews/evidence always use metres.
    preview=plane_cut(scale(vector(origin),plan.unit_scale),normal,scale(vector(bounds_min),plan.unit_scale),scale(vector(bounds_max),plan.unit_scale),max_cutters=max_cutters,padding_m=padding_m)
    if len(plan.operations)+len(preview['cutters'])>100:raise ModelingError('operation_budget_exceeded','Plane cut exceeds native plan operation budget')
    with plan._atomic_edit():
        parts=[]
        for i,c in enumerate(preview['cutters']):
            part=plan.hole(f'{name}/cut-{i}',targets,*[x/plan.unit_scale for x in c['sizeMetres']],position=scale(c['position'],1/plan.unit_scale),rotation_quaternion=c['rotationQuaternion'])
            part.expected['hardFaceIntent']=deepcopy({k:v for k,v in preview.items() if k!='cutters'})
            parts.append(part)
    return {'parts':parts,'preview':preview,'geometryStatus':'not_assessed','shadingStatus':'not_assessed'}


def _angle(a,b):return math.degrees(math.acos(max(-1.,min(1.,dot(a,b)))))
def _cross2(a,b):return a[0]*b[1]-a[1]*b[0]
def _sub2(a,b):return (a[0]-b[0],a[1]-b[1])
def _area(poly):return abs(sum(_cross2(a,b) for a,b in zip(poly,poly[1:]+poly[:1])))/2 if len(poly)>=3 else 0.
def _signed(poly):return sum(_cross2(a,b) for a,b in zip(poly,poly[1:]+poly[:1]))/2
def _clip(poly,clip):
    result=list(poly)
    for a,b in zip(clip,clip[1:]+clip[:1]):
        old=result;result=[]
        if not old:break
        edge=_sub2(b,a)
        for p,q in zip(old,old[1:]+old[:1]):
            dp=_cross2(edge,_sub2(p,a));dq=_cross2(edge,_sub2(q,a))
            if dp>=-1e-12:result.append(p)
            if (dp<0<dq) or (dq<0<dp):
                t=dp/(dp-dq);result.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
    return result


def _fit_plane(points):
    c=tuple(sum(p[i] for p in points)/len(points) for i in range(3))
    centered=[sub(p,c) for p in points]
    a=[[sum(p[i]*p[j] for p in centered) for j in range(3)] for i in range(3)]
    v=[[float(i==j) for j in range(3)] for i in range(3)]
    for _ in range(32):
        p,q=max(((0,1),(0,2),(1,2)),key=lambda pair:abs(a[pair[0]][pair[1]]))
        if abs(a[p][q])<1e-20:break
        theta=.5*math.atan2(2*a[p][q],a[q][q]-a[p][p]);cs=math.cos(theta);sn=math.sin(theta)
        rot=[[float(i==j) for j in range(3)] for i in range(3)];rot[p][p]=rot[q][q]=cs;rot[p][q]=sn;rot[q][p]=-sn
        a=[[sum(rot[k][i]*a[k][l]*rot[l][j] for k in range(3) for l in range(3)) for j in range(3)] for i in range(3)]
        v=[[sum(v[i][k]*rot[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    k=min(range(3),key=lambda i:a[i][i]);n=unit(tuple(v[i][k] for i in range(3)))
    return c,n,max(abs(dot(sub(p,c),n)) for p in points)


def validate_face_target(boundary,normal,tolerance_m=.001):
    tol=number(tolerance_m,'tolerance_m',1e-8,.1)
    if not isinstance(boundary,(list,tuple)) or not 3<=len(boundary)<=64:raise ModelingError('invalid_face_boundary','Supply 3..64 convex ordered vertices')
    points=[vector(p) for p in boundary];n=unit(normal);o=points[0]
    if len(set(points))!=len(points):raise ModelingError('invalid_face_boundary','Do not repeat boundary vertices')
    if max(abs(dot(sub(p,o),n)) for p in points)>tol:raise ModelingError('invalid_face_boundary','Expected boundary must lie on its declared plane')
    u=unit(sub(points[1],o));v=unit(cross(n,u));poly=[(dot(sub(p,o),u),dot(sub(p,o),v)) for p in points]
    if _signed(poly)<0:poly.reverse()
    if _area(poly)<1e-12 or any(_cross2(_sub2(b,a),_sub2(p,a))<-1e-10 for a,b in zip(poly,poly[1:]+poly[:1]) for p in poly):raise ModelingError('invalid_face_boundary','Boundary must be convex and ordered without self-intersections')
    return points,n


def inspect_planar_face(evidence,mesh_index,triangle_indices,*,boundary,normal,tolerance_m=.001,normal_tolerance_deg=.5,max_triangles=512):
    tol=number(tolerance_m,'tolerance_m',1e-8,.1);ntol=number(normal_tolerance_deg,'normal_tolerance_deg',1e-6,10)
    validate_face_target(boundary,normal,tol)
    if type(mesh_index) is not int or not 0<=mesh_index<len(evidence.meshes):raise ModelingError('invalid_face_selection','Unknown mesh index')
    if type(max_triangles) is not int or not 1<=max_triangles<=512:raise ModelingError('measurement_budget','max_triangles must be 1..512')
    mesh=evidence.meshes[mesh_index];indices=mesh['indices'];vertices=mesh['vertices']
    if not isinstance(triangle_indices,(list,tuple)) or not triangle_indices or len(triangle_indices)>max_triangles or len(set(triangle_indices))!=len(triangle_indices):raise ModelingError('invalid_face_selection','Select distinct triangles for the complete face within budget')
    if any(type(i) is not int or not 0<=i<len(indices)//3 for i in triangle_indices):raise ModelingError('invalid_face_selection','Triangle index is outside this capture')
    if not isinstance(boundary,(list,tuple)) or not 3<=len(boundary)<=64:raise ModelingError('invalid_face_boundary','Supply 3..64 convex boundary vertices, without repeating the first')
    n=unit(normal,'expected outward normal');poly=[vector(p,'boundary vertex') for p in boundary];o=poly[0]
    if max(abs(dot(sub(p,o),n)) for p in poly)>tol:raise ModelingError('invalid_face_boundary','Expected boundary must lie on the declared plane')
    u=unit(sub(poly[1],o));v=unit(cross(n,u));project=lambda p:(dot(sub(p,o),u),dot(sub(p,o),v))
    polygon=[project(p) for p in poly]
    if _signed(polygon)<0:polygon.reverse()
    if _area(polygon)<1e-12 or any(_cross2(_sub2(b,a),_sub2(c,b))<-1e-10 for a,b,c in zip(polygon,polygon[1:]+polygon[:1],polygon[2:]+polygon[:2])):raise ModelingError('invalid_face_boundary','Boundary must be nondegenerate, convex and ordered')
    attrs=mesh.get('attributes',{});normal_data=attrs.get('normals');parity=attrs.get('windingParity',1)
    used=set();gn=[];projected=[];degenerate=[];normal_errors=[]
    for i in triangle_indices:
        ids=indices[i*3:i*3+3];tri=[vector(vertices[k]) for k in ids];direction=cross(sub(tri[1],tri[0]),sub(tri[2],tri[0]))
        if dot(direction,direction)<1e-20:degenerate.append(i);continue
        used.update(ids);gn.append(scale(unit(direction),parity));p=[project(x) for x in tri]
        if _signed(p)<0:p.reverse()
        projected.append(p)
    if not used:return {'status':'unavailable','reason':'no_nondegenerate_face_triangles'}
    points=[vector(vertices[i]) for i in sorted(used)];unique=list(dict.fromkeys(points));center,fit,fit_error=_fit_plane(unique)
    distances=[abs(dot(sub(p,o),n)) for p in points]
    area=_area(polygon);perimeter=sum(math.dist(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]));area_tol=max(1e-10,tol*perimeter)
    inside=sum(_area(_clip(p,polygon)) for p in projected);outside=sum(_area(p) for p in projected)-inside
    overlap=sum(_area(_clip(a,b)) for i,a in enumerate(projected) for b in projected[i+1:])
    coverage=abs(area-inside)<=area_tol and outside<=area_tol and overlap<=max(1e-10,area*1e-7) and not degenerate
    # Pairwise comparisons are bounded above by max_triangles and deduplicated.
    geometric=list(dict.fromkeys(tuple(round(x,12) for x in g) for g in gn))
    span=lambda ns:max((_angle(a,b) for i,a in enumerate(ns) for b in ns[i:]),default=0.)
    geometric_span=span(geometric);geometric_angle=max(_angle(g,n) for g in gn)
    normals_available=attrs.get('normalsStatus')=='available' and isinstance(normal_data,list) and len(normal_data)==len(vertices)
    shading=[]
    if normals_available:
        try:shading=[unit(normal_data[i],'native shading normal') for i in sorted(used)]
        except (ValueError,TypeError,ModelingError):normals_available=False
    normals=list(dict.fromkeys(tuple(round(x,12) for x in g) for g in shading))
    if len(normals)>1536:raise ModelingError('measurement_budget','Too many unique shading normals for pairwise span')
    shading_span=span(normals) if normals_available else None
    shading_angle=max((_angle(g,n) for g in shading),default=0.) if normals_available else None
    geometry_ok=coverage and max(distances)<=tol and fit_error<=tol and geometric_span<=ntol and geometric_angle<=ntol
    shading_ok=normals_available and shading_span<=ntol and shading_angle<=ntol
    status='passed' if geometry_ok and shading_ok else 'failed' if not geometry_ok or normals_available else 'unavailable'
    return {'status':status,'identity':deepcopy(evidence.identity),'captureId':evidence.sample.get('captureId'),'geometryStamp':evidence.sample.get('geometryStamp'),
        'attributeStamp':attrs.get('attributeStamp'),'nativeEvidenceVerified':evidence._artifact_verified,'frame':evidence.frame.to_dict(),'partId':mesh['partId'],'meshIndex':mesh_index,'triangleIndices':list(triangle_indices),
        'target':{'boundary':[list(p) for p in poly],'normal':list(n),'toleranceMetres':tol,'normalToleranceDegrees':ntol},
        'geometry':{'passed':geometry_ok,'targetPlaneMaxMetres':max(distances),'bestFitPlaneMaxMetres':fit_error,'bestFitOrigin':list(center),'bestFitNormal':list(fit),'normalSpanDegrees':geometric_span,'normalToTargetMaxDegrees':geometric_angle},
        'shading':{'status':'available' if normals_available else 'unavailable','passed':bool(shading_ok),'normalSpanDegrees':shading_span,'normalToTargetMaxDegrees':shading_angle,'reason':None if normals_available else attrs.get('normalsReason','capture vertex_attributes=[normals]')},
        'coverage':{'complete':coverage,'expectedAreaM2':area,'projectedInsideAreaM2':inside,'outsideAreaM2':outside,'overlapAreaM2':overlap,'areaToleranceM2':area_tol,'degenerateTriangles':degenerate},
        'witness':{'vertexId':sorted(used)[distances.index(max(distances))],'position':list(points[distances.index(max(distances))])},
        'meaning':'Complete declared convex footprint only; native appearance still needs fixed-view review. Missing coverage/attributes never count as passed.'}


def inspect_face_region(evidence,mesh_index,*,boundary,normal,selection_angle_deg=25,selection_distance_m=.05,**tolerances):
    """Resolve a target face on a fresh mesh, then require whole-footprint coverage.

    The frozen search corridor is wider than acceptance tolerances. Geometry
    outside it is not called correct: missing footprint makes the check fail.
    """
    validate_face_target(boundary,normal,tolerances.get('tolerance_m',.001))
    if type(mesh_index) is not int or not 0<=mesh_index<len(evidence.meshes):raise ModelingError('invalid_face_selection','Unknown mesh index')
    angle=number(selection_angle_deg,'selection_angle_deg',1,80);distance=number(selection_distance_m,'selection_distance_m',.00001,1)
    if distance<tolerances.get('tolerance_m',.001):raise ModelingError('invalid_face_selection','Search corridor must include the acceptance tolerance')
    if not isinstance(boundary,(list,tuple)) or len(boundary)<3:raise ModelingError('invalid_face_boundary','A complete convex boundary is required')
    p=[vector(x) for x in boundary];n=unit(normal);o=p[0];u=unit(sub(p[1],o));v=unit(cross(n,u));project=lambda x:(dot(sub(x,o),u),dot(sub(x,o),v))
    polygon=[project(x) for x in p]
    if _signed(polygon)<0:polygon.reverse()
    mesh=evidence.meshes[mesh_index];parity=mesh.get('attributes',{}).get('windingParity',1);selected=[]
    for i in range(len(mesh['indices'])//3):
        tri=[vector(mesh['vertices'][k]) for k in mesh['indices'][3*i:3*i+3]];direction=cross(sub(tri[1],tri[0]),sub(tri[2],tri[0]))
        if dot(direction,direction)<1e-20:continue
        if _angle(scale(unit(direction),parity),n)>angle or min(abs(dot(sub(x,o),n)) for x in tri)>distance:continue
        projected=[project(x) for x in tri]
        if _signed(projected)<0:projected.reverse()
        if _area(_clip(projected,polygon))>1e-12:selected.append(i)
    if not selected:return {'status':'failed','reason':'No triangles cover the required face in the frozen search corridor','coverage':{'complete':False},'identity':deepcopy(evidence.identity)}
    result=inspect_planar_face(evidence,mesh_index,selected,boundary=boundary,normal=normal,**tolerances)
    result['selection']={'angleDegrees':angle,'distanceMetres':distance,'candidateTriangleCount':len(selected),'rule':'all projected-overlapping triangles in declared geometric normal/distance corridor'}
    return result
