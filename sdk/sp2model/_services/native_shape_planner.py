"""Finite native recipes. Precision use requires explicit native-origin calibration."""
import math
from .reference_storage import ReferenceError, read_json, file_hash
from .registration import vector, norm, cross, rotation_matrix, transform_point
from .representation_checks import wall_check, sections_check, sub, dot, unit


def _quaternion(x,y,z):
    # Rotation matrix has the three world basis directions as columns.
    m=[[x[i],y[i],z[i]] for i in range(3)];trace=sum(m[i][i] for i in range(3))
    if trace>0:
        s=2*math.sqrt(trace+1);return [(m[2][1]-m[1][2])/s,(m[0][2]-m[2][0])/s,(m[1][0]-m[0][1])/s,.25*s]
    i=max(range(3),key=lambda j:m[j][j]);j=(i+1)%3;k=(i+2)%3
    s=2*math.sqrt(max(0.,1+m[i][i]-m[j][j]-m[k][k]));q=[0.,0.,0.,0.]
    q[i]=.25*s;q[j]=(m[j][i]+m[i][j])/s;q[k]=(m[k][i]+m[i][k])/s;q[3]=(m[k][j]-m[j][k])/s
    return q


def _recipe(start,end,up,height0,height1,thickness,label):
    y=unit(up);offset=sub(end,start);z=unit(sub(offset,[dot(offset,y)*v for v in y]));x=unit(cross(y,z))
    # Gram-Schmidt fixes handedness and preserves the chosen section-up direction.
    z=unit(cross(x,y))
    local=[dot(offset,axis) for axis in (x,y,z)]
    return {"id":label,"family":"fuselage","position":[(a+b)*.5 for a,b in zip(start,end)],"rotationQuaternion":_quaternion(x,y,z),
            "sectionOrigin":"midpoint","sectionCenters":[start,end],"patch":{"offset":local,"autoResize":False,"hollow":False,"glass":False,"sections":[
                {"index":0,"width":thickness,"height":height0,"smoothing":False,"syncAdjacent":False,"trapezium":0,
                 "cornerRadius":{k:0 for k in ("topLeft","topRight","bottomRight","bottomLeft")},"edgeCurvature":{k:0 for k in ("top","right","bottom","left")},"cutting":{k:None for k in ("top","right","bottom","left")}},
                {"index":1,"width":thickness,"height":height1,"smoothing":False,"syncAdjacent":False,"trapezium":0,
                 "cornerRadius":{k:0 for k in ("topLeft","topRight","bottomRight","bottomLeft")},"edgeCurvature":{k:0 for k in ("top","right","bottom","left")},"cutting":{k:None for k in ("top","right","bottom","left")}}]},
            "frame":{"right":x,"up":y,"forward":z}}


def _triangle(a,b,c,thickness,label):
    # The longest edge becomes the nondegenerate end section; the opposite point is a zero-height section.
    candidates=[(a,b,c),(b,c,a),(c,a,b)];base0,base1,apex=max(candidates,key=lambda t:norm(sub(t[1],t[0])))
    center=[(x+y)*.5 for x,y in zip(base0,base1)]
    recipe=_recipe(center,apex,sub(base1,base0),norm(sub(base1,base0)),0.,thickness,label)
    recipe["targetTriangle"]=[a,b,c]
    return recipe


def _number(value):
    return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value)


def _within_bound(value,limits):
    # Gram-Schmidt and quaternion normalization can leave sub-nanometre components
    # around an exact zero. This is numerical slack, not an expanded fitting budget.
    slack=max(1e-9,64*max(math.ulp(float(v)) for v in (value,*limits)))
    return limits[0]-slack<=value<=limits[1]+slack


def _parameters(recipe):
    return {"width":[s["width"] for s in recipe["patch"]["sections"]],"height":[s["height"] for s in recipe["patch"]["sections"]],
            "offsetX":[recipe["patch"]["offset"][0]],"offsetY":[recipe["patch"]["offset"][1]],"length":[abs(recipe["patch"]["offset"][2])]}


def _corners(sample):
    position=vector(sample.get("position"));rotation=rotation_matrix(sample.get("rotationQuaternion"));patch=sample.get("patch",{})
    offset=vector(patch.get("offset"));sections=patch.get("sections",[])
    if len(sections)!=2 or abs(offset[2])<.001:raise ReferenceError("calibration_invalid","Calibration samples require two sections and native length >=0.001m")
    points=[]
    for index,section in enumerate(sections):
        if any(not _number(section.get(k)) or not 0<=section[k]<=1000 for k in ("width","height")):
            raise ReferenceError("calibration_invalid","Calibration section dimensions must be finite and nonnegative")
        if section.get("trapezium",0)!=0 or any(any(v not in (0,None) for v in section.get(field,{}).values()) for field in ("cornerRadius","edgeCurvature","cutting")):
            raise ReferenceError("calibration_invalid","This calibration model covers straight rectangular section boundaries")
        for xsign in (-1,1):
            for ysign in (-1,1):
                local=[value*(-.5 if index==0 else .5) for value in offset]
                local[0]+=xsign*section["width"]*.5;local[1]+=ysign*section["height"]*.5
                points.append([position[i]+sum(rotation[i][j]*local[j] for j in range(3)) for i in range(3)])
    return points


def _calibration(evidence,payload):
    validation=evidence.get("validation",{});bounds=evidence.get("parameterDomain",{})
    budget=payload.get("proxyErrorBudgetMetres",.001);claimed=validation.get("maxBoundaryErrorMetres")
    if (evidence.get("templateId")!=payload.get("templateId") or not payload.get("gameVersion") or evidence.get("gameVersion")!=payload["gameVersion"]
        or evidence.get("sectionOrigin")!="midpoint" or evidence.get("sectionCount")!=2 or not _number(budget) or budget<0
        or not _number(claimed) or not 0<=claimed<=budget
        or not validation.get("nativeMeshPath") or not validation.get("nativeMeshSha256")
        or file_hash(validation["nativeMeshPath"])!=validation["nativeMeshSha256"]):
        raise ReferenceError("calibration_invalid","Native calibration identity, geometry evidence or error budget is invalid")
    mesh=read_json(validation["nativeMeshPath"]);ident=mesh.get("identity",{})
    if (mesh.get("format")!="indexed_triangles_v1" or mesh.get("units")!="metres" or mesh.get("source")!="renderMesh"
        or not mesh.get("geometryStamp") or mesh.get("exclusions") or ident.get("stateUncertain")
        or ident.get("gameVersion")!=payload["gameVersion"] or not ident.get("craftSessionId")
        or isinstance(ident.get("revision"),bool) or not isinstance(ident.get("revision"),int)):
        raise ReferenceError("calibration_invalid","Calibration requires complete native renderMesh evidence with a known game identity")
    frame=mesh.get("frameToWorldRows")
    if not isinstance(frame,list) or len(frame)!=4 or any(len(vector(row,4))!=4 for row in frame) or frame[3]!=[0,0,0,1]:
        raise ReferenceError("calibration_invalid","Native mesh coordinate frame must be an affine 4x4 matrix")
    samples=validation.get("samples",[]);count=validation.get("sampleCount")
    if isinstance(count,bool) or not isinstance(count,int) or count<1 or not isinstance(samples,list) or count!=len(samples):
        raise ReferenceError("calibration_invalid","sampleCount must equal the nonempty native sample list")
    observed={key:[] for key in ("width","height","offsetX","offsetY","length")};computed=0.
    for sample in samples:
        number=sample.get("partId")
        if isinstance(number,bool) or not isinstance(number,int) or number<0:raise ReferenceError("calibration_invalid","Sample partId must be a native integer ID")
        points=[]
        for entry in mesh.get("meshes",[]):
            if entry.get("partId")!=number:continue
            vertices=entry.get("vertices",[]);indices=entry.get("indices",[])
            if not indices or len(indices)%3 or any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(vertices) for i in indices):
                raise ReferenceError("calibration_invalid","Native sample has invalid or empty triangle topology",partId=number)
            points.extend(transform_point({"matrix":frame},vertices[i]) for i in set(indices))
        if not points:raise ReferenceError("calibration_invalid","Native calibration sample is absent from the mesh",partId=number)
        computed=max(computed,max(min(math.dist(corner,p) for p in points) for corner in _corners(sample)))
        for key,values in _parameters(sample).items():observed[key].extend(values)
    if computed>budget or computed>claimed+1e-9:
        raise ReferenceError("calibration_invalid","Actual native corner residual exceeds the declared calibration error",computedBoundaryErrorMetres=computed,declaredBoundaryErrorMetres=claimed)
    for key,values in observed.items():
        limit=bounds.get(key)
        if (not isinstance(limit,list) or len(limit)!=2 or any(not _number(v) for v in limit) or limit[0]>limit[1]
            or limit[0]<min(values)-1e-9 or limit[1]>max(values)+1e-9):
            raise ReferenceError("calibration_invalid","Parameter domain exceeds the measured sample envelope",parameter=key,observedRange=[min(values),max(values)],verifiedDomain=limit)
    return bounds


def _operations(recipes,payload):
    template=payload.get("templateId");domain=payload.get("nativeDomain")
    if not template or not domain:return [],False
    evidence_path=domain.get("evidencePath")
    if not evidence_path or not domain.get("evidenceSha256") or file_hash(evidence_path)!=domain["evidenceSha256"]:
        raise ReferenceError("calibration_invalid","Native calibration evidence is missing or its hash changed")
    evidence=read_json(evidence_path,"sp2build.nativeShapeCalibration")
    bounds=_calibration(evidence,payload)
    for recipe in recipes:
        _corners(recipe)
        parameters=_parameters(recipe)
        for key,values in parameters.items():
            limit=bounds.get(key)
            if not isinstance(limit,list) or len(limit)!=2 or any(not _within_bound(v,limit) for v in values):
                raise ReferenceError("proxy_invalid","Recipe is outside the verified native parameter domain",parameter=key,values=values,verifiedDomain=limit)
    operations=[]
    for recipe in recipes:
        name=payload.get("temporaryPrefix","shape")+"-"+recipe["id"]
        operations.extend([{"kind":"part.add","templateId":template,"temporaryId":name,"position":recipe["position"]},
                           {"kind":"shape.update","partId":name,"patch":recipe["patch"]},
                           {"kind":"transform.apply","partIds":[name],"mode":"absolute","position":recipe["position"],
                            "rotationQuaternion":recipe["rotationQuaternion"],"anchorPartId":name,"symmetric":False}])
    return operations,True


def plan(payload):
    family=payload.get("family","wall");recipes=[]
    if family=="wall":
        check=wall_check(payload);a,b,c,d=[vector(payload[key]) for key in ("lowerStart","lowerEnd","upperStart","upperEnd")]
        thickness=payload.get("thickness",.1)
        if not isinstance(thickness,(int,float)) or not math.isfinite(thickness) or not .001<=thickness<=1000:raise ReferenceError("invalid_input","Thickness must be 0.001..1000 metres")
        if check["singlePart"]:
            start=[(u+v)*.5 for u,v in zip(a,c)];end=[(u+v)*.5 for u,v in zip(b,d)]
            recipes=[_recipe(start,end,sub(c,a),norm(sub(c,a)),norm(sub(d,b)),thickness,"wall")]
        else:
            diagonal=payload.get("splitDiagonal","lowerStart_upperEnd")
            if diagonal=="lowerStart_upperEnd":recipes=[_triangle(a,b,d,thickness,"triangle-0"),_triangle(a,d,c,thickness,"triangle-1")]
            elif diagonal=="upperStart_lowerEnd":recipes=[_triangle(a,b,c,thickness,"triangle-0"),_triangle(b,d,c,thickness,"triangle-1")]
            else:raise ReferenceError("invalid_input","Unknown quadrilateral splitDiagonal")
        part_budget=payload.get("partBudget",2)
        if len(recipes)>part_budget:return {"status":"representation_limited","check":check,"requiredPartCount":len(recipes),"partBudget":part_budget,"recipes":[]}
        operations,calibrated=_operations(recipes,payload)
        return {"status":"planned" if calibrated else "native_calibration_required","check":check,"recipes":recipes,"operations":operations,
                "partCount":len(recipes),"nativeValidated":False,"requiresNativeCalibration":not calibrated,
                "geometricMeaning":"Planar mid-surfaces match the four target vertices. Thickness, native mesh, corners and final seams require readback.",
                "splitDiagonal":payload.get("splitDiagonal","lowerStart_upperEnd") if len(recipes)>1 else None,
                "limitations":["Nonplanar quadrilaterals use the declared diagonal; it must agree with the source triangulation.","Calibration is an empirical rectangular-boundary parameter envelope, not a continuous native mesh guarantee.","Zero-height tip validity and template slice origin require native evidence."]}
    if family in ("sections","hull","bluntClosure"):
        check=sections_check(payload)
        result={"status":"native_calibration_required","check":check,"recipes":[],"operations":[],
                "partCount":0,"nativeValidated":False,"requiresNativeCalibration":True,"splitRequired":False,
                "limitations":["Observation stations are verification samples, not instructions to create one segment per interval.",
                               "Only a straight rectangular two-control candidate can use the existing native calibration recipe.",
                               "Curved, hollow sections, corner/edge controls and Hole need their own native calibration and complete contour review."]}
        if not check.get("candidateFits"):
            result["reason"]="single_candidate_not_established"
            return result
        if check["candidate"]["kind"]!="linear" or check["unmodeledFields"]:
            result["reason"]="native_recipe_requires_calibration"
            return result
        budget=payload.get("partBudget",1)
        if isinstance(budget,bool) or not isinstance(budget,int) or budget<0:
            raise ReferenceError("invalid_input","partBudget must be a nonnegative integer")
        if budget<1:
            return {**result,"status":"representation_limited","requiredPartCount":1,"partBudget":budget}
        a,b=check["candidate"]["controlSections"]
        recipes=[{"id":"continuous-section","family":"fuselage",
                  "position":[(a.get("offsetX",0)+b.get("offsetX",0))*.5,
                              (a.get("offsetY",0)+b.get("offsetY",0))*.5,(a["station"]+b["station"])*.5],
                  "rotationQuaternion":[0,0,0,1],"sectionOrigin":"midpoint",
                  "patch":{"autoResize":False,"offset":[b.get("offsetX",0)-a.get("offsetX",0),
                      b.get("offsetY",0)-a.get("offsetY",0),b["station"]-a["station"]],
                      "sections":[{"index":i,"width":s["width"],"height":s["height"],
                          "smoothing":False,"syncAdjacent":False,"trapezium":0,
                          "cornerRadius":{k:0 for k in ("topLeft","topRight","bottomRight","bottomLeft")},
                          "edgeCurvature":{k:0 for k in ("top","right","bottom","left")},
                          "cutting":{k:None for k in ("top","right","bottom","left")}}
                          for i,s in enumerate((a,b))],"hollow":False,"glass":False}}]
        # The newly narrowed section recipe cannot inherit an unversioned
        # calibration from another plugin build. Wall recipes retain their
        # historical contract; fresh section evidence records both versions.
        domain=payload.get("nativeDomain")
        if domain and domain.get("evidencePath"):
            evidence=read_json(domain["evidencePath"],"sp2build.nativeShapeCalibration")
            if not payload.get("pluginVersion") or evidence.get("pluginVersion")!=payload["pluginVersion"]:
                return {**result,"recipes":recipes,"partCount":1,"reason":"native_calibration_plugin_version_unknown_or_changed"}
        operations,calibrated=_operations(recipes,payload)
        return {**result,"status":"planned" if calibrated else "native_calibration_required", "recipes":recipes,
                "operations":operations,"partCount":1,"requiresNativeCalibration":not calibrated}
    raise ReferenceError("unsupported_shape_family","No finite construction recipe for this family",family=family)


def dispatch(action,payload,context=None):return plan(payload)
