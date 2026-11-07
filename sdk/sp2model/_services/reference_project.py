"""Offline reference engineering and guarded live structure dispatch."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import uuid
from .reference_storage import ReferenceError, utc_now, read_json, write_json, file_hash, digest
from .structure_model import validate_structure, freeze_profile
from . import reference_binding
from . import structure_plan
from . import structure_runner
from . import native_shape_planner
from . import representation_checks
from . import quality_gates
from . import run_journal

KIND="sp2build.referenceProject"


def create(payload):
    coordinate=deepcopy(payload.get("coordinateSystem",{"units":"m","axes":{"right":"+x","up":"+y","forward":"+z"}}))
    value={"kind":KIND,"schemaVersion":1,"projectId":str(uuid.uuid4()),"name":payload.get("name","Reference project"),
           "createdAt":utc_now(),"updatedAt":utc_now(),"coordinateSystem":coordinate,"sources":[],"structures":[],
           "toleranceProfiles":{},"annotations":[],"cameras":[],"binding":None,"history":[]}
    validate(value,verify_sources=False)
    return value


def validate(project,verify_sources=True):
    if project.get("kind")!=KIND:raise ReferenceError("document_kind_mismatch","Expected a reference project")
    if project.get("schemaVersion")!=1:raise ReferenceError("incompatible_schema","Unsupported reference project schema",supported=[1],actual=project.get("schemaVersion"))
    if not project.get("projectId") or not project.get("name"):raise ReferenceError("invalid_document","Project id and name required")
    coordinate=project.get("coordinateSystem",{})
    if coordinate.get("units")!="m":raise ReferenceError("invalid_coordinate_system","Project coordinates use metres; source unit conversion must be explicit")
    axes=coordinate.get("axes",{})
    labels=[str(axes.get(k,"")).lower() for k in ("right","up","forward")]
    if any(v not in ("+x","-x","+y","-y","+z","-z") for v in labels) or len(set(v[-1:] for v in labels))!=3:
        raise ReferenceError("invalid_coordinate_system","Project axes must specify three distinct signed axes")
    diagnostics=[];source_ids=set()
    for source in project.get("sources",[]):
        if not source.get("id") or source["id"] in source_ids or not source.get("kind") or not source.get("path") or not source.get("sha256"):
            raise ReferenceError("invalid_document","Sources require unique id, kind, path and sha256")
        source_ids.add(source["id"])
        if verify_sources:
            try:
                checksum=file_hash(source["path"])
                if checksum!=source["sha256"]:diagnostics.append({"sourceId":source["id"],"status":"changed","expectedSha256":source["sha256"],"actualSha256":checksum})
            except ReferenceError as exc:diagnostics.append({"sourceId":source["id"],"status":"unavailable","reason":str(exc)})
    structure_ids=set()
    for structure in project.get("structures",[]):
        validate_structure(structure)
        if structure["id"] in structure_ids:raise ReferenceError("invalid_document","Structure IDs must be unique")
        structure_ids.add(structure["id"])
        missing=set(structure.get("sourceIds",[]))-source_ids
        if missing:raise ReferenceError("source_not_found","Structure refers to unknown sources",sourceIds=sorted(missing))
        profile=structure.get("toleranceProfile")
        if profile and profile not in project.get("toleranceProfiles",{}):raise ReferenceError("profile_not_found","Structure tolerance profile is missing",profileId=profile)
    for profile in project.get("toleranceProfiles",{}).values():
        if profile.get("frozen") and digest({k:v for k,v in profile.items() if k!="contentHash"})!=profile.get("contentHash"):
            raise ReferenceError("profile_changed","Frozen tolerance profile was changed",profileId=profile.get("id"))
    # Multiple primary references for a semantic structure require explicit precedence.
    groups={}
    for source in project.get("sources",[]):
        semantic=source.get("semanticId")
        if semantic and not source.get("excluded"):groups.setdefault(semantic,[]).append(source)
    for semantic,sources in groups.items():
        if len(sources)>1 and (any("priority" not in s for s in sources) or len(set(s["priority"] for s in sources))!=len(sources)):
            diagnostics.append({"semanticId":semantic,"status":"reference_conflict","sourceIds":[s["id"] for s in sources]})
    return {"valid":True,"status":"ready" if not diagnostics else "attention_required","diagnostics":diagnostics,
            "schemaVersion":1,"projectId":project["projectId"]}


def _project_path(payload):
    value=payload.get("project") or payload.get("projectPath") or payload.get("path")
    if not isinstance(value,str):raise ReferenceError("invalid_input","Project path is required")
    return value


def _snapshot(payload,context):
    value=payload.get("snapshot")
    if isinstance(value,str):value=read_json(value)
    if value is None:
        callback=(context or {}).get("live")
        if not callable(callback):raise ReferenceError("live_required","Supply a snapshot or connect to the live game")
        value=callback("craft.snapshot",{"includeXml":True})
    reference_binding.identity(value)
    return value


def _plan(payload):
    value=payload.get("plan") or payload.get("planPath")
    if isinstance(value,str):value=read_json(value,structure_plan.KIND)
    if not isinstance(value,dict):raise ReferenceError("invalid_input","Plan object or planPath required")
    return structure_plan.validate(value)


def dispatch(action,payload,context=None):
    """Return unwrapped local data. Caller supplies its normal CLI result envelope."""
    payload=deepcopy(payload or {})
    if action.startswith("reference."):action=action[len("reference."):]
    if action in ("create","project.create"):
        project=create(payload);path=_project_path(payload)
        saved=write_json(path,project,overwrite=bool(payload.get("overwrite",False)))
        return {"project":project,**saved}
    if action in ("structure.plan",):
        payload["snapshot"]=_snapshot(payload,context)
        if isinstance(payload.get("qualityProfile"),str):payload["qualityProfile"]=read_json(payload["qualityProfile"])
        plan=structure_plan.create(payload);output=payload.get("output") or payload.get("planPath")
        return {"plan":plan,**(write_json(output,plan,overwrite=False) if output else {})}
    if action=="structure.impact":return structure_plan.inspect_impact(_snapshot(payload,context),payload.get("oldPartIds",[]))
    if action in ("structure.run","structure.replace","structure.reconcile","structure.restore"):
        plan=_plan(payload);journal=payload.get("journalPath")
        if not journal:raise ReferenceError("invalid_input","Explicit journalPath is required for recoverable replacement")
        runner=structure_runner.reconcile if action.endswith("reconcile") else structure_runner.restore if action.endswith("restore") else structure_runner.run
        return runner(plan,journal,payload,context)
    if action=="structure.status":return run_journal.status(payload["journalPath"])
    if action in ("shape.plan","native.shape.plan"):return native_shape_planner.plan(payload)
    if action in ("representation.check","shape.check"):return representation_checks.dispatch(action,payload,context)
    if action=="quality.evaluate":
        profile=payload.get("profile");evidence=payload.get("evidence")
        if isinstance(profile,str):profile=read_json(profile)
        if isinstance(evidence,str):evidence=read_json(evidence)
        return quality_gates.evaluate(profile,evidence or {})
    if action=="binding.threeWay":return reference_binding.three_way(payload["base"],payload["proposed"],payload["current"])
    path=_project_path(payload);checksum=file_hash(path);project=read_json(path,KIND)
    validate(project,verify_sources=False)
    if action in ("read","inspect","project.read"):return {"project":project,"validation":validate(project),"path":str(Path(path).resolve()),"sha256":checksum}
    if action in ("validate","project.validate"):return validate(project)
    if action in ("changes","project.changes"):
        if not project.get("binding"):raise ReferenceError("binding_required","Project is not bound to a craft")
        return reference_binding.changes(project["binding"],_snapshot(payload,context),payload.get("affectedPartIds"),payload.get("reusedPartIds"))
    result={}
    if action in ("source.add","add"):
        source=deepcopy(payload.get("source",{}))
        if not source.get("id") or not source.get("path") or not source.get("kind"):raise ReferenceError("invalid_input","Source requires id, path and kind")
        if any(s["id"]==source["id"] for s in project["sources"]):raise ReferenceError("source_exists","Source ID already exists; use a new version ID")
        source["path"]=str(Path(source["path"]).resolve());source["sha256"]=file_hash(source["path"]);source["addedAt"]=utc_now()
        project["sources"].append(source);result["source"]=source
    elif action=="structure.set":
        structure=validate_structure(deepcopy(payload.get("structure",{})))
        old=next((s for s in project["structures"] if s["id"]==structure["id"]),None)
        if old and set(old.get("lockedPartIds",[]))!=set(structure.get("lockedPartIds",[])) and not payload.get("changeLocks"):
            raise ReferenceError("locked_scope","Changing locked scope requires explicit changeLocks:true")
        project["structures"]=[s for s in project["structures"] if s["id"]!=structure["id"]]+[structure];result["structure"]=structure
    elif action in ("profile.freeze","tolerance.freeze"):
        profile=freeze_profile(payload["profile"])
        if profile["id"] in project["toleranceProfiles"]:raise ReferenceError("profile_exists","Frozen profile is immutable; create a new ID")
        project["toleranceProfiles"][profile["id"]]=profile;result["profile"]=profile
    elif action in ("bind","project.bind"):
        project["binding"]=reference_binding.bind(_snapshot(payload,context),payload.get("partIds"),payload.get("anchors"),payload.get("referenceToCraft"));result["binding"]=project["binding"]
    elif action in ("rebind","project.rebind"):
        if not project.get("binding"):raise ReferenceError("binding_required","Project has no baseline binding")
        result=reference_binding.rebind(project["binding"],_snapshot(payload,context),payload.get("partMapping"),payload.get("toleranceMetres",1e-4));project["binding"]=result["binding"]
    else:raise ReferenceError("unsupported_command","Unknown reference action",action=action)
    project["updatedAt"]=utc_now();project["history"].append({"at":project["updatedAt"],"action":action,"previousDocumentHash":checksum})
    result["validation"]=validate(project)
    result.update(write_json(path,project,expected_hash=checksum));return result
