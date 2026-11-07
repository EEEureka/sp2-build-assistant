"""Finite construction checks; observation stations are not native controls.

Section fits are analytic candidates, never proof that a complete native surface
is expressible.  In particular a failed candidate is not a native-family limit.
"""
import math
from .registration import vector, norm, cross
from .reference_storage import ReferenceError


def sub(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def unit(v):
    size=norm(v)
    if size<1e-12:raise ReferenceError("degenerate_geometry","Zero-length construction edge")
    return [x/size for x in v]


def wall_check(payload):
    a,b,c,d=[vector(payload[key]) for key in ("lowerStart","lowerEnd","upperStart","upperEnd")]
    tolerance=payload.get("toleranceMetres",1e-5)
    if tolerance<0:raise ReferenceError("invalid_input","Tolerance must be nonnegative")
    edge0,edge1=sub(c,a),sub(d,b)
    y=unit(edge0);lower=sub(b,a)
    z=unit(sub(lower,[dot(lower,y)*v for v in y]));normal=unit(cross(y,z))
    plane_error=abs(dot(sub(d,a),normal))
    angle=math.degrees(math.acos(max(-1.,min(1.,dot(y,unit(edge1))))))
    perpendicular_error=norm(cross(edge1,y))
    length=abs(dot(lower,z))
    single=plane_error<=tolerance and perpendicular_error<=tolerance and dot(edge1,y)>0 and length>=.001
    reasons=[]
    if plane_error>tolerance:reasons.append("nonplanar_wall")
    if perpendicular_error>tolerance or dot(edge1,y)<=0:reasons.append("nonparallel_end_sections")
    if length<.001:reasons.append("native_minimum_length")
    bottom_dir=unit(lower);top_dir=unit(sub(d,c))
    return {"status":"expressible" if single else "split_required","singlePart":single,"planeResidualMetres":plane_error,
            "endSectionDirectionDegrees":angle,"endSectionResidualMetres":perpendicular_error,
            "topBottomDirectionDegrees":math.degrees(math.acos(max(-1.,min(1.,dot(bottom_dir,top_dir))))),
            "longitudinalLengthMetres":length,"reasons":reasons,"frame":{"right":normal,"up":y,"forward":z},
            "meaning":"Two-slice fuselage sections share parallel planes and section-up direction; all four endpoints are checked.",
            "assessmentScope":"straight_rectangular_wall_recipe", "nativeValidated":False,
            "limitations":["split_required applies only to this finite wall recipe, not every fuselage/Curved/Hole construction.",
                           "These four mid-surface corners do not validate thickness, cuts, native mesh or full boundaries."]}


def _number(value):
    return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value)


def _basis(count,t):
    return [1-t,t] if count==2 else [(1-t)**2,2*t*(1-t),t*t]


def _section_values(section,fields,label):
    if not isinstance(section,dict):raise ReferenceError("invalid_input",label+" must be an object")
    result={}
    for field in fields:
        value=section.get(field,0 if field.startswith("offset") else None)
        if not _number(value):raise ReferenceError("invalid_input","Finite section value required",field=field,section=label)
        if field in ("width","height") and not 0<=value<=1000:
            raise ReferenceError("invalid_input","Section dimensions must be 0..1000 metres",field=field,section=label)
        result[field]=float(value)
    return result


def _calibration_metadata(payload,model):
    """Keep version claims visible without treating caller metadata as evidence."""
    calibration=model.get("calibration")
    if calibration is not None and not isinstance(calibration,dict):
        raise ReferenceError("invalid_input","model.calibration must be an object")
    current={key:payload.get(key) for key in ("gameVersion","pluginVersion","shapeFamily")}
    supplied={key:calibration.get(key) for key in current} if calibration else {}
    mismatched=[key for key,value in current.items() if calibration and value and supplied.get(key)!=value]
    missing=[key for key,value in current.items() if not value or not supplied.get(key)]
    return {"current":current,"declared":supplied,"status":"version_mismatch" if mismatched else
            "version_unknown" if missing else "declared_only", "mismatchedFields":mismatched,
            "missingFields":missing,"verified":False,
            "meaning":"Version metadata is not native mesh calibration; no supplied validated/pass flag can certify this fit."}


def sections_check(payload):
    sections=payload.get("sections",[]);count=payload.get("nativeSectionCount",2)
    if isinstance(count,bool) or count not in (2,3):
        raise ReferenceError("invalid_input","Only two/three native control-section candidates are supported")
    if not isinstance(sections,list) or len(sections)<2:
        raise ReferenceError("invalid_input","At least two observation sections are required")
    tolerance=payload.get("toleranceMetres",1e-5)
    if not _number(tolerance) or tolerance<0:
        raise ReferenceError("invalid_input","Tolerance must be finite and nonnegative")
    model=payload.get("model",{})
    if not isinstance(model,dict):raise ReferenceError("invalid_input","model must be an object")
    kind=model.get("kind","linear" if count==2 else "quadratic_bezier")
    fields=["width","height"]+[key for key in ("offsetX","offsetY") if any(isinstance(s,dict) and key in s for s in sections)]
    stations=[];observations=[];unmodeled=set()
    for index,section in enumerate(sections):
        observations.append(_section_values(section,fields,"observation "+str(index)))
        station=section.get("station")
        if not _number(station):raise ReferenceError("invalid_input","Finite observation station required",index=index)
        if index and station<=stations[-1]:
            raise ReferenceError("invalid_input","Observation stations must be strictly increasing",index=index)
        stations.append(float(station))
        unmodeled.update(set(section)-set(fields)-{"station","label"})
    shape=payload.get("shape",{})
    if not isinstance(shape,dict):raise ReferenceError("invalid_input","shape must be an object")
    unmodeled.update("shape."+key for key in shape)
    versions=_calibration_metadata(payload,model)
    reasons=[]
    result={"status":"requires_calibration","singlePart":None,"splitRequired":False,
            "nativeSectionCount":count,"targetSectionCount":len(sections),"observationSectionCount":len(sections),
            "modeledFields":fields,"unmodeledFields":sorted(unmodeled),"reasons":reasons,
            "requiresNativeCalibration":True,"nativeValidated":False,"calibration":versions,
            "assessmentScope":"finite_observation_scalar_fit",
            "limitations":["Observation count is not a construction boundary or native control count.",
                           "Fit residual covers only the listed scalar fields at observed stations, not complete contours, cuts, topology, tangency or tessellation.",
                           "A failed fitted candidate does not prove all single native bodies impossible.",
                           "Curved middle values are Bezier controls, not literal dimensions at the middle observation."]}
    supported={"linear":2,"quadratic_bezier":3}
    if kind not in supported or supported[kind]!=count:
        reasons.append("interpolation_model_requires_calibration")
        return result
    first,last=stations[0],stations[-1];span=last-first
    if span<.001:
        reasons.append("native_minimum_length")
        return result
    parameters=[(station-first)/span for station in stations]
    bases=[_basis(count,t) for t in parameters]
    specified=model.get("controlSections")
    if specified is not None:
        if not isinstance(specified,list) or len(specified)!=count:
            raise ReferenceError("invalid_input","controlSections must match the declared native control count")
        controls=[_section_values(s,fields,"control "+str(i)) for i,s in enumerate(specified)]
        for i,station in ((0,first),(count-1,last)):
            if "station" in specified[i] and (not _number(specified[i]["station"]) or abs(specified[i]["station"]-station)>1e-9):
                raise ReferenceError("invalid_input","Control endpoint station must match the observation domain",index=i)
        for section in specified:
            unmodeled.update(set(section)-set(fields)-{"station","index","controlParameter","label"})
        result["unmodeledFields"]=sorted(unmodeled)
        origin="supplied_controls"
    else:
        # Endpoints remain shared-boundary anchors. Fit only the quadratic middle
        # control over every observation; do not copy the measured t=.5 value.
        controls=[observations[0].copy(),observations[-1].copy()]
        origin="endpoint_constrained_fit"
        if count==3:
            denominator=sum(b[1]*b[1] for b in bases)
            if denominator<1e-15:
                reasons.append("middle_control_underconstrained")
                return result
            middle={field:sum(b[1]*(sample[field]-b[0]*controls[0][field]-b[2]*controls[1][field])
                              for b,sample in zip(bases,observations))/denominator for field in fields}
            controls.insert(1,middle)
    residuals=[]
    for index,(basis,sample) in enumerate(zip(bases,observations)):
        predicted={field:sum(basis[j]*controls[j][field] for j in range(count)) for field in fields}
        errors={field:abs(predicted[field]-sample[field]) for field in fields}
        residuals.append({"observationIndex":index,"station":stations[index],"parameter":parameters[index],
                          "predicted":predicted,"absoluteResidualMetres":errors,"maxResidualMetres":max(errors.values())})
    maximum=max(row["maxResidualMetres"] for row in residuals)
    invalid=any(not 0<=control[field]<=1000 for control in controls for field in ("width","height"))
    fits=maximum<=tolerance and not invalid
    if invalid:reasons.append("fitted_controls_outside_dimension_domain")
    if maximum>tolerance:reasons.append("candidate_residual_exceeds_tolerance")
    if unmodeled:reasons.append("unmodeled_section_properties")
    if versions["mismatchedFields"]:reasons.append("native_calibration_version_changed")
    result.update(status="fit_candidate" if fits else "candidate_mismatch",candidateFits=fits,
                  candidate={"kind":kind,"controlOrigin":origin,"controlSections":[
                      {"index":i,"controlParameter":i/(count-1),"station":first+span*i/(count-1),**control}
                      for i,control in enumerate(controls)],"endpointAnchorsPreserved":specified is None},
                  residuals=residuals,maxResidualMetres=maximum,toleranceMetres=tolerance)
    return result


def dispatch(action,payload,context=None):
    family=payload.get("family","wall")
    if family=="wall":return wall_check(payload)
    if family in ("sections","hull","bluntClosure"):return sections_check(payload)
    raise ReferenceError("unsupported_shape_family","No declared expression model for this shape family",family=family)
