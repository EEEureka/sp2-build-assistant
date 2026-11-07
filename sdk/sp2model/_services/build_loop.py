"""Evidence-driven build goals. This module journals decisions; it never edits a craft.

Every review supplies a fresh snapshot plus separate subject and impact reports.
Reports are evidence, not authority to relax the original user acceptance criteria.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import os
import math
from pathlib import Path
import uuid

from .reference_storage import ReferenceError, digest, utc_now
from .reference_binding import bind, changes, identity, part_signature, snapshot_parts, snapshot_context
from .structure_model import part_ids
from . import run_journal

KIND = "sp2build.buildLoop"
_STATUS = {"passed": "pass", "failed": "fail", "needs_review": "unknown", "missing_evidence": "unknown"}


def _ids(values, name="partIds"):
    return part_ids(values or [], name)


def scope_hash(snapshot, ids):
    parts = snapshot_parts(snapshot)
    keys = [str(i) for i in sorted(_ids(ids))]
    if any(key not in parts for key in keys):
        raise ReferenceError("part_not_found", "Evidence scope contains a missing part", partIds=list(ids))
    return digest({key: part_signature(parts[key]) for key in keys})


def _scope(goal):
    return sorted(set(goal["partIds"]) | set(goal.get("scope", {}).get("partIds", [])) |
                  {i for boundary in goal.get("boundaries", []) for i in boundary.get("partIds", [])})


def _goal(value, source, existing_ids=()):
    if not isinstance(value, dict) or not isinstance(value.get("expected"), str) or not value["expected"].strip():
        raise ReferenceError("invalid_goal", "Each goal needs a concrete expected outcome")
    goal = deepcopy(value)
    for field in ('partIds','boundaries','protectedFields'):
        if field in goal and not isinstance(goal[field],list):raise ReferenceError('invalid_goal',field+' must be an array',fieldPath='.'+field)
    for field in ('scope','verification'):
        if field in goal and not isinstance(goal[field],dict):raise ReferenceError('invalid_goal',field+' must be an object',fieldPath='.'+field)
    for field in ('partIds','impactPartIds'):
        if field in goal.get('scope',{}) and not isinstance(goal['scope'][field],list):raise ReferenceError('invalid_goal','Scope '+field+' must be an array',fieldPath='.scope.'+field)
    goal["id"] = str(goal.get("id") or uuid.uuid4())
    if goal["id"] in existing_ids:
        raise ReferenceError("duplicate_goal", "Goal IDs cannot be replaced", goalId=goal["id"])
    try:goal["partIds"] = _ids(goal.get("partIds"))
    except ReferenceError as error:error.details['fieldPath']='.partIds';raise
    goal["scope"] = deepcopy(goal.get("scope", {}))
    try:goal["scope"]["partIds"] = _ids(goal["scope"].get("partIds", goal["partIds"]))
    except ReferenceError as error:error.details['fieldPath']='.scope.partIds';raise
    goal["boundaries"] = deepcopy(goal.get("boundaries", []))
    if not isinstance(goal["boundaries"], list) or any(not isinstance(b, dict) or not b.get("id") for b in goal["boundaries"]):
        raise ReferenceError("invalid_goal", "Boundaries require explicit stable IDs")
    for boundary in goal["boundaries"]:
        boundary["partIds"] = _ids(boundary.get("partIds", []))
    if not _scope(goal):
        raise ReferenceError("invalid_goal", "Goals need a nonempty part or boundary scope")
    goal["protectedFields"] = deepcopy(goal.get("protectedFields", []))
    if not isinstance(goal["protectedFields"], list) or any(not isinstance(f, dict) or type(f.get("partId")) is not int or f['partId']<0 or
            not isinstance(f.get("path"), str) or not f["path"].startswith("/") for f in goal["protectedFields"]):
        raise ReferenceError("invalid_goal", "Protected fields need partId and JSON pointer path")
    verification = deepcopy(goal.get("verification", {}))
    verification.setdefault("requiredEvidenceKinds", ["native_mesh_measurement"])
    verification.setdefault("coverageMode", "complete")
    if not isinstance(verification['requiredEvidenceKinds'],list) or not verification["requiredEvidenceKinds"] or any(not isinstance(v,str) or not v.strip() for v in verification['requiredEvidenceKinds']) or verification["coverageMode"] not in ("complete", "finite_sampled"):
        raise ReferenceError("invalid_goal", "Verification requires evidence kinds and an explicit coverage mode")
    if verification["coverageMode"] == "finite_sampled" and (not isinstance(verification.get("limitationsAccepted"),(str,dict)) or not verification["limitationsAccepted"]):
        raise ReferenceError("invalid_goal", "Finite sampling needs an explicit accepted limitation and its source")
    goal.update(verification=verification, source=deepcopy(source), status="inspection" if value.get("task") == "inspect" else "pending")
    goal.setdefault("channel", "subject" if source["kind"] == "user" else source.get("channel", "impact"))
    goal.setdefault("task", "repair")
    goal["verificationHistory"] = []
    return goal


def _load(path):
    entries = run_journal.read(path)
    if not entries:
        raise ReferenceError("loop_not_found", "Create a build loop before reviewing it")
    if entries[0].get("loop", {}).get("kind") != KIND:
        raise ReferenceError("document_kind_mismatch", "This journal is not a build loop")
    if any(entry.get("loop", {}).get("kind") != KIND for entry in entries):
        raise ReferenceError("journal_corrupt", "Build loop history contains another record type")
    loop=deepcopy(entries[-1]["loop"])
    # Old journals accepted impact reports without retaining their dependency
    # scope. Recover that scope from the immutable round record in memory;
    # inspect must never rewrite historical evidence as a new verification.
    if "impactAcceptance" not in loop:
        accepted=next((entry for entry in reversed(entries) if entry.get("event")=="round_reviewed" and entry.get("loop",{}).get("completion",{}).get("impact") is True and isinstance(entry.get("impactReview"),dict)),None)
        if accepted:
            report=accepted["impactReview"];coverage=report.get("coverageSummary",report.get("coverage",{}))
            ids=coverage.get("partIds",coverage.get("impactPartIds",[])) if isinstance(coverage,dict) else []
            loop["impactAcceptance"]=_impact_acceptance(accepted["loop"],report,ids,accepted["loop"]["binding"])
            loop["impactRequiredPartIds"]=sorted(set(loop.get("impactRequiredPartIds",[]))|set(ids))
    return loop, entries


def _impact_acceptance(loop,report,ids,binding):
    selected=sorted(set(ids));saved=deepcopy(binding)
    saved["partIds"]=selected
    saved["parts"]={str(i):deepcopy(binding["baselineParts"][str(i)]) for i in selected}
    saved["baselineParts"]=deepcopy(saved["parts"])
    saved["partHashes"]={str(i):part_signature(saved["parts"][str(i)]) for i in selected}
    coverage=deepcopy(report.get("coverageSummary",report.get("coverage",{})))
    snapshot={"identity":deepcopy(binding["identity"]),"parts":list(deepcopy(binding["baselineParts"]).values())}
    accepted=[deepcopy(item) for item in report.get("evidence",[]) if _evidence(item,loop,snapshot)[0]]
    scopes={}
    for item in accepted:scopes.setdefault(item["kind"],set()).update(set(item["partIds"])&set(selected))
    proof=deepcopy(report.get("discovery"))
    subject={str(i) for goal in loop["goals"] if goal["source"]["kind"]=="user" for i in _scope(goal)}
    discovery_verified=bool(selected or proof) or set(binding["baselineParts"])<=subject
    return {"id":"impact-round-"+str(loop["round"]),"status":"verified","partIds":selected,"binding":saved,
            "coverage":coverage,"evidenceScopes":{kind:sorted(values) for kind,values in scopes.items() if kind and values},
            "evidence":accepted,"checkIds":[item.get("id") for item in report.get("checks",[])],
            "referenceHash":loop.get("referenceHash"),"coordinateFrame":deepcopy(loop.get("coordinateFrame")),"invalidationHistory":[],
            "discoveryBasis":_discovery_basis(binding["baselineParts"],binding["identity"],binding.get("contextState",{}),proof),
            "discoveryState":{"status":"verified" if discovery_verified else "pending","reason":"accepted_inventory_baseline" if discovery_verified else "empty_impact_discovery_unproven"}}


def _geometry_inventory(parts):
    def node(value):
        if not isinstance(value,dict):return deepcopy(value)
        if value.get("tag") in ("FuelTank.State","InputController.State"):return None
        attrs={key:deepcopy(item) for key,item in value.get("attributes",{}).items() if key not in ("drag","dragArea","mass","deadMassKg","fuel","capacity")}
        if value.get("tag")=="Part":attrs={key:item for key,item in attrs.items() if key in ("id","partType","position","rotation","scale","symmetryId","symmetryDisabled","visible","visibleInDesigner","hidden","partCollisionResponse")}
        return {"tag":value.get("tag"),"attributes":attrs,"children":[item for child in value.get("children",[]) if (item:=node(child)) is not None],"text":value.get("text")}
    fields=("id","type","position","rotationEulerDegrees","rotationQuaternion","scale","symmetryId","connectedPartIds","visible","visibleInDesigner","hidden","visibility","shape","props","stateNodes")
    result={}
    for key,part in parts.items():
        value={field:deepcopy(part[field]) for field in fields if field in part}
        if part.get("serializedState"):value["serializedState"]=node(part["serializedState"])
        result[str(key)]=digest(value)
    return result


def _discovery_basis(parts,ident,context,proof=None):
    return {"identity":deepcopy(ident),"geometryInventory":_geometry_inventory(parts),"nativeConnections":deepcopy(context.get("connections",[])),
            "topologyHash":digest(context.get("connections",[])),"boundsInventory":deepcopy((proof or {}).get("boundsInventory",{})),
            "proof":deepcopy(proof),"meaning":"Full native inventory geometry/content and topology for cheap impact rediscovery; names, palette assignments, fuel and generated mass/drag caches are excluded."}


def _discovery_proof(proof,snapshot):
    if not isinstance(proof,dict) or proof.get("identity")!=identity(snapshot):return False,"discovery_evidence_missing_or_stale"
    ids={int(key) for key in snapshot_parts(snapshot)}
    if proof.get("complete") is not True or set(proof.get("inventoryPartIds",[]))!=ids or proof.get("uncapturedInventoryPartIds"):
        return False,"discovery_inventory_incomplete"
    if proof.get("source")=="regional_geometry":return (True,None) if proof.get("geometryStamp") else (False,"native_geometry_stamp_missing")
    if proof.get("source")!="native_bounds_inventory" or not proof.get("geometryStamp"):return False,"unsupported_discovery_source"
    if proof.get("units") not in ("m","metres") or proof.get("frame")!="world":return False,"native_bounds_coordinate_system_missing"
    boxes=proof.get("boundsInventory",{})
    if not isinstance(boxes,dict) or set(boxes)!=set(str(i) for i in ids):return False,"native_bounds_inventory_incomplete"
    for box in boxes.values():
        if not isinstance(box,dict) or any(not isinstance(box.get(key),list) or len(box[key])!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in box[key]) for key in ("min","max")) or any(box["min"][i]>box["max"][i] for i in range(3)):
            return False,"invalid_native_bounds"
    return True,None


def _bounds_far(basis,proof,snapshot,changed,subject):
    valid,_=_discovery_proof(proof,snapshot)
    if not valid or proof["source"]!="native_bounds_inventory" or set(changed)&set(subject):return False
    if basis.get("topologyHash")!=digest(snapshot_context(snapshot)["connections"]):return False
    before=basis.get("boundsInventory",{});after=proof["boundsInventory"]
    if not before and basis["geometryInventory"]==_geometry_inventory(snapshot_parts(snapshot)):before=after
    radius=proof.get("neighborRadiusMetres",.05)
    if isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or radius<0:return False
    # Both old and new positions matter. Missing old bounds cannot certify that
    # a retired or moved object used to be unrelated.
    region=[box for table in (before,after) for pid in subject if (box:=table.get(str(pid))) is not None]
    if not region or any(str(pid) not in before or str(pid) not in after for pid in subject):return False
    for pid in changed:
        boxes=[table[str(pid)] for table in (before,after) if str(pid) in table]
        if not boxes or str(pid) in basis["geometryInventory"] and str(pid) not in before or str(pid) in snapshot_parts(snapshot) and str(pid) not in after:return False
        for box in boxes:
            for target in region:
                distance=math.sqrt(sum(max(0.,box['min'][i]-target['max'][i],target['min'][i]-box['max'][i])**2 for i in range(3)))
                if distance<=radius:return False
    return True


def _rediscovery_goal(loop,snapshot,changed,reason):
    acceptance=loop["impactAcceptance"];acceptance["discoveryState"]={"status":"pending","reason":reason,"changedPartIds":sorted(changed)}
    loop["completion"]["impact"]=False;loop["state"]="active";loop["nextAction"]="rediscover_impact_before_repair"
    subject=sorted({i for goal in loop["goals"] if goal["source"]["kind"]=="user" for i in _scope(goal)})
    ids=sorted(i for i in changed if str(i) in snapshot_parts(snapshot)) or [i for i in subject if str(i) in snapshot_parts(snapshot)]
    if not ids:return
    key="system:impact-rediscovery";goal=next((goal for goal in loop["goals"] if goal["id"]==key),None)
    if goal is None:
        goal=_goal({"id":key,"partIds":ids,"channel":"impact","task":"inspect","expected":"Rediscover current and previous geometric neighbors before deciding whether any repair is needed",
                    "verification":{"requiredEvidenceKinds":["impact_discovery"],"coverageMode":"complete"}},
                   {"kind":"impact_rediscovery","channel":"impact","subjectPartIds":subject,"changedPartIds":sorted(changed),"reason":reason,"repairInferred":False})
        loop["goals"].append(goal)
    else:
        if goal["source"]["kind"]!="impact_rediscovery":raise ReferenceError("reserved_goal_id","System rediscovery goal ID is already used")
        if goal["status"]!="verified":changed=set(changed)|set(goal["source"].get("changedPartIds",[]))
        goal["partIds"]=ids;goal["scope"]["partIds"]=ids;goal["status"]="inspection";goal["task"]="inspect"
        goal["source"].update(changedPartIds=sorted(changed),reason=reason)


def _impact_recheck(loop,snapshot,reason,report):
    acceptance=loop.get("impactAcceptance")
    if not acceptance:return
    acceptance["status"]="invalidated";loop["completion"]["impact"]=False
    history=acceptance.setdefault("invalidationHistory",[])
    event={"identity":identity(snapshot),"reason":reason,"changeReport":deepcopy(report)}
    if not history or history[-1]!=event:history.append(event)
    if not acceptance["partIds"]:return
    ids=sorted(i for i in acceptance["partIds"] if str(i) in snapshot_parts(snapshot))
    missing=sorted(set(acceptance["partIds"])-set(ids))
    if not ids:ids=sorted({i for goal in loop["goals"] if goal["source"]["kind"]=="user" for i in _scope(goal) if str(i) in snapshot_parts(snapshot)})
    if not ids:
        loop["unresolvedFindings"].append({"id":"impact-ownership-missing","channel":"impact","reason":"Accepted impact region has no surviving binding; explicit ownership rebinding is required","partIds":[]})
        return
    key="system:impact-acceptance-recheck";goal=next((goal for goal in loop["goals"] if goal["id"]==key),None)
    if goal is None:
        mode="finite_sampled" if acceptance.get("coverage",{}).get("status")=="finite_sampled" else "complete"
        verification={"coverageMode":mode,"requiredEvidenceKinds":sorted(acceptance.get("evidenceScopes",{})) or ["native_mesh_measurement"],"impactEvidenceScopes":deepcopy(acceptance.get("evidenceScopes",{}))}
        if mode=="finite_sampled":verification["limitationsAccepted"]={"basis":"previous_explicit_finite_impact_acceptance","acceptanceId":acceptance["id"],"userGoalVerifications":[deepcopy(g["verification"]) for g in loop["goals"] if g["source"]["kind"]=="user" and g["verification"]["coverageMode"]=="finite_sampled"]}
        goal=_goal({"id":key,"partIds":ids,"channel":"impact","task":"inspect","expected":"Recheck the previously accepted impact region and preserve the original subject evidence","verification":verification},
                   {"kind":"impact_acceptance","channel":"impact","acceptanceId":acceptance["id"],"evidenceIds":[item.get("id") for item in acceptance.get("evidence",[])]})
        loop["goals"].append(goal)
    elif goal["source"]["kind"]!="impact_acceptance":raise ReferenceError("reserved_goal_id","System impact-recheck ID is already used by another goal")
    else:
        goal["partIds"]=ids;goal["scope"]["partIds"]=ids
        goal["verification"]["impactEvidenceScopes"]=deepcopy(acceptance.get("evidenceScopes",{}))
        if goal["status"]=="verified":goal["verificationHistory"].append({"at":utc_now(),"status":"invalidated","identity":identity(snapshot),"reason":reason})
        goal["status"]="inspection";goal["task"]="inspect"
    goal["source"]["missingDependencyPartIds"]=missing
    loop["state"]="active";loop["nextAction"]="inspect_affected_impact_scope"


@contextmanager
def _lock(path):
    target = Path(str(Path(path).resolve()) + ".loop.lock")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ReferenceError("journal_busy", "Inspect the interrupted loop writer before recovery", path=str(target)) from exc
    try:
        os.close(fd)
        yield
    finally:
        target.unlink(missing_ok=True)


def _append(path, event, loop, payload, **data):
    from . import build_guidance
    loop['guidance'] = build_guidance.journal_metadata(payload, loop.get('guidance'))
    if 'executionJournals' in payload:
        paths = payload['executionJournals']
        if not isinstance(paths, list) or len(paths) > 16 or any(not isinstance(p, str) or not p.strip() for p in paths):
            raise ReferenceError('invalid_input', 'executionJournals must contain at most 16 explicit run-journal paths')
        loop['executionJournals'] = list(dict.fromkeys(str(Path(p).resolve()) for p in paths))
    record = run_journal.append(path, event, loop=loop, state=loop["state"], requestId=payload.get("requestId"),
                                inputHash=digest(payload), **data)
    return {"journalPath":str(Path(path).resolve()), "headHash":record["entryHash"], "loop":deepcopy(loop),
            "nextRoundGoals":deepcopy([g for g in loop["goals"] if g["status"] != "verified"]),
            "writesIssued":False}


def _snapshot(payload, context):
    value = payload.get("snapshot")
    if value is None and callable((context or {}).get("live")):
        from .reference_binding import unwrap
        value = unwrap(context["live"]("craft.snapshot", {"includeXml":True}))
    if value is None:
        raise ReferenceError("snapshot_required", "A current snapshot is required")
    identity(value)
    return value


def _pointer(value, path):
    current = value
    for token in path.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (KeyError, TypeError, ValueError, IndexError):
            return {"missing":True}
    return current


def _freeze_protected(goal,snapshot):
    parts=snapshot_parts(snapshot)
    goal["protectionBaseline"]=[{**deepcopy(field),"value":deepcopy(_pointer(parts.get(str(field["partId"]),{}),field["path"]))}
                                 for field in goal["protectedFields"]]


def _chronology(binding,snapshot):
    before=binding["identity"];current=identity(snapshot)
    if current["craftSessionId"]!=before["craftSessionId"]:return
    if current["revision"]<before["revision"]:
        raise ReferenceError("evidence_order_mismatch","Historical snapshots cannot move an active goal loop backwards",
                             acceptedIdentity=before,suppliedIdentity=current)
    if current["revision"]==before["revision"]:
        report=changes(binding,snapshot)
        if current.get("fingerprint")!=before.get("fingerprint") or report["changedPartIds"] or report["topologyConflicts"] or report["materialConflicts"] or report["globalConflicts"]:
            raise ReferenceError("identity_conflict","The same session/revision describes different state; reconcile before reviewing",
                                 acceptedIdentity=before,suppliedIdentity=current)


def _loop_changes(loop,snapshot,reused=()):
    report=changes(loop["binding"],snapshot,reused_ids=reused)
    if report["status"]=="rebind_required":return report
    anchored={i for goal in loop["goals"] for i in _scope(goal)}|set(loop.get("impactRequiredPartIds",[]))
    parts=snapshot_parts(snapshot);baseline=loop["binding"].get("baselineParts",{})
    typed={i for i in anchored if str(i) in parts and str(i) in baseline and parts[str(i)].get("type")!=baseline[str(i)].get("type")}
    explicit={item["partId"] if isinstance(item,dict) else item for item in reused}&anchored
    if typed or explicit:report.update(status="rebind_required",reason="anchored_numeric_id_reused",reusedPartIds=sorted(typed|explicit))
    return report


def _invalidate(loop, snapshot, reused=(), reference_state=None, discovery=None):
    _chronology(loop["binding"],snapshot)
    report = _loop_changes(loop,snapshot,reused)
    if report["status"] == "rebind_required":
        raise ReferenceError("rebind_required", "A new session requires an explicit part mapping; old numeric IDs are not identities")
    changed = set(report["changedPartIds"]) | set(report["reusedPartIds"])
    for entry in report["topologyConflicts"]:
        for connection in (entry["before"], entry["after"]):
            if connection:
                changed.update((connection["partA"], connection["partB"]))
    parts = snapshot_parts(snapshot)
    reference_changed={key:{"expected":deepcopy(loop.get(key)),"current":deepcopy(value)} for key,value in (reference_state or {}).items() if value!=loop.get(key)}
    if reference_state:
        loop["referenceState"]={"status":"changed" if reference_changed else "compatible","differences":reference_changed}
    elif loop.get("referenceState",{}).get("status")=="changed":reference_changed=deepcopy(loop["referenceState"]["differences"])
    for goal in loop["goals"]:
        ids = set(_scope(goal)) | set(goal.get("scope", {}).get("impactPartIds", []))
        material_changed = any(set(parts.get(str(i), {}).get("materialIds", [])) & set(report["materialConflicts"]) for i in ids)
        geometric_discovery_goal=goal["source"]["kind"]=="impact_rediscovery"
        if (ids & changed or material_changed or report["globalConflicts"]) and not geometric_discovery_goal and goal["status"] == "verified":
            goal["status"] = "reopened"
            goal["verificationHistory"].append({"at":utc_now(), "status":"invalidated", "identity":identity(snapshot),
                                                 "reason":"related_state_changed", "changedPartIds":sorted(ids & changed)})
        if any(str(item["sourcePartId"]) in parts for item in goal.get("retirementObligations",[])) and goal["status"]=="verified":
            goal["status"]="reopened"
            goal["verificationHistory"].append({"at":utc_now(),"status":"invalidated","identity":identity(snapshot),"reason":"retired_id_reappeared_requires_ownership_review"})
        if reference_changed and goal["status"]=="verified":
            goal["status"]="reopened"
            goal["verificationHistory"].append({"at":utc_now(),"status":"invalidated","identity":identity(snapshot),"reason":"reference_or_coordinate_frame_changed","differences":deepcopy(reference_changed)})
    acceptance=loop.get("impactAcceptance")
    if acceptance:
        delta=changes(acceptance["binding"],snapshot,acceptance["partIds"],reused)
        relevant=delta.get("status")=="rebind_required" or set(delta.get("conflicts",[])) or delta.get("topologyConflicts") or delta.get("materialConflicts") or delta.get("globalConflicts")
        if relevant or reference_changed or acceptance.get("status")!="verified":
            _impact_recheck(loop,snapshot,"reference_or_coordinate_frame_changed" if reference_changed else "accepted_impact_state_changed",{"state":delta,"reference":reference_changed})
        basis=acceptance.get("discoveryBasis")
        if basis:
            current_inventory=_geometry_inventory(parts)
            geometry_changed={int(key) for key in set(basis["geometryInventory"])|set(current_inventory) if basis["geometryInventory"].get(key)!=current_inventory.get(key)}
            current_context=snapshot_context(snapshot)
            if basis["topologyHash"]!=digest(current_context["connections"]):
                old_edges={digest(edge):edge for edge in basis["nativeConnections"]};new_edges={digest(edge):edge for edge in current_context["connections"]}
                for key in set(old_edges)^set(new_edges):geometry_changed.update((old_edges.get(key) or new_edges[key])[field] for field in ("partA","partB"))
            discovery_pending=acceptance.get("discoveryState",{}).get("status")=="pending"
            if geometry_changed or discovery_pending:
                subject={i for goal in loop["goals"] if goal["source"]["kind"]=="user" for i in _scope(goal)}
                candidates=geometry_changed or ({int(key) for key in current_inventory}-subject)
                if _bounds_far(basis,discovery,snapshot,candidates,subject):
                    acceptance["discoveryBasis"]=_discovery_basis(parts,identity(snapshot),current_context,discovery)
                    acceptance["discoveryState"]={"status":"verified","reason":"current_native_bounds_exclude_changed_external_objects","excludedPartIds":sorted(candidates),"proof":deepcopy(discovery)}
                else:_rediscovery_goal(loop,snapshot,candidates,"external_geometry_or_inventory_changed" if geometry_changed else "empty_impact_discovery_unproven")
    protected = []
    for goal in loop["goals"]:
        for field in goal.get("protectionBaseline",[]):
            key = str(field["partId"])
            before = field["value"]
            after = _pointer(parts.get(key, {}), field["path"])
            if before != after:
                protected.append({"id":"protected-"+goal["id"]+"-"+digest(field)[:12], "goalId":goal["id"],
                                  "status":"fail", "partIds":[field["partId"]], "expected":"Preserve "+field["path"],
                                  "before":before, "after":after, "field":field})
    return report, protected


def _report(payload, channel):
    report = deepcopy(payload.get(channel + "Review", {}))
    combined = payload.get("report", {})
    if not report and combined:
        report = deepcopy(combined.get(channel + "Review", {}))
        report.setdefault("checks", deepcopy(combined.get(channel + "Checks", [])))
        report.setdefault("identity", combined.get("identity"))
        report.setdefault("coverage", deepcopy(combined.get("coverage", {})))
        report.setdefault("issues", [deepcopy(f) for f in combined.get("findings", []) if f.get("channel", "subject") == channel])
    report.setdefault("checks", deepcopy(combined.get(channel + "Checks", [])))
    report.setdefault("issues", [])
    report.setdefault("evidence", [])
    if channel=="impact":
        if payload.get("impactDiscovery") is not None:report["discovery"]=deepcopy(payload["impactDiscovery"])
        elif combined.get("impactDiscovery") is not None:report.setdefault("discovery",deepcopy(combined["impactDiscovery"]))
        elif combined.get("kind")=="sp2build.regionalReview":
            coverage=combined.get("coverage",{})
            report.setdefault("discovery",{"source":"regional_geometry","identity":deepcopy(combined.get("identity")),"complete":coverage.get("impactDiscoveryComplete") is True,
                "inventoryPartIds":sorted(int(key) for key in combined.get("partHashes",{})),"geometryStamp":combined.get("geometryStamp"),
                "uncapturedInventoryPartIds":deepcopy(coverage.get("uncapturedInventoryPartIds",[])),"captureScope":deepcopy(coverage.get("captureScope")),
                "boundsInventory":deepcopy(combined.get("boundsInventory",{})),"beforeIdentity":deepcopy(combined.get("beforeIdentity")),
                "beforeComplete":combined.get("beforeComplete") is True,"beforeInventoryPartIds":deepcopy(combined.get("beforeInventoryPartIds",[])),
                "beforeGeometryInventoryHash":combined.get("beforeGeometryInventoryHash")})
    for check in report["checks"]:
        if isinstance(check.get("evidence"), dict):
            evidence = check["evidence"]
            report["evidence"].append(evidence)
            check.setdefault("evidenceIds", [evidence.get("id")])
    return report


def _evidence(evidence, loop, snapshot):
    if not isinstance(evidence, dict) or not evidence.get("id") or not evidence.get("kind"):
        return False, "evidence_identity_missing"
    if evidence.get("identity") != identity(snapshot):
        return False, "evidence_stale"
    ids = _ids(evidence.get("partIds", []))
    if not ids:
        return False, "evidence_scope_missing"
    try:
        if evidence.get("scopeHash") != scope_hash(snapshot, ids):
            return False, "evidence_scope_changed"
    except ReferenceError:
        return False, "evidence_part_missing"
    for key in ("referenceHash", "coordinateFrame"):
        if loop.get(key) is not None and evidence.get(key) != loop[key]:
            return False, key + "_mismatch"
    if evidence["kind"] == "visual_review" and (evidence.get("reviewed") is not True or not evidence.get("imagePaths")):
        return False, "images_not_reviewed"
    if evidence["kind"] == "native_mesh_measurement" and not evidence.get("geometryStamp"):
        return False, "native_geometry_stamp_missing"
    if evidence["kind"] == "native_absence":
        absent=evidence.get("absentPartIds")
        if not isinstance(absent,list) or not absent or evidence.get("checked") is not True:
            return False,"absence_check_missing"
        if any(str(i) in snapshot_parts(snapshot) for i in _ids(absent)):
            return False,"retired_part_present"
    return True, None


def _coverage(report, channel, goal):
    coverage = report.get("coverage", {})
    if isinstance(coverage, list):
        items = [item for item in coverage if item.get("goalId") == goal["id"]]
        if not items:
            return False, "goal_coverage_missing"
        if any(_STATUS.get(item.get("status"), item.get("status")) != "pass" for item in items):
            return False, "goal_coverage_incomplete"
        if any(item.get("coverageMode") == "finite_sampled" for item in items) and goal["verification"]["coverageMode"] != "finite_sampled":
            return False, "finite_samples_do_not_certify_complete_scope"
        covered = {i for item in items for i in item.get("partIds", [])}
        boundaries = {b for item in items for b in item.get("boundaryIds", [])}
    else:
        status = coverage.get("status")
        allowed = ("complete", "pass", "passed")
        if goal["verification"]["coverageMode"] == "finite_sampled":
            allowed += ("finite_sampled",)
        if status not in allowed or coverage.get("unobserved") or coverage.get("missingMeshPartIds"):
            return False, "coverage_incomplete"
        covered = set(coverage.get("partIds", coverage.get(channel + "PartIds", [])))
        boundaries = set(coverage.get("boundaryIds", []))
    if not set(_scope(goal)) <= covered:
        return False, "scope_coverage_missing"
    if not {b["id"] for b in goal["boundaries"]} <= boundaries:
        return False, "boundary_coverage_missing"
    return True, None


def _review_goal(goal, report, loop, snapshot):
    if goal["source"]["kind"]=="impact_rediscovery":
        proof=report.get("discovery");valid,reason=_discovery_proof(proof,snapshot)
        if not valid:return "unknown",reason,[]
        acceptance=loop["impactAcceptance"]
        basis=acceptance["discoveryBasis"]
        if proof["source"]=="regional_geometry" and basis["geometryInventory"]!=_geometry_inventory(snapshot_parts(snapshot)):
            bound=proof.get("beforeIdentity")==basis["identity"] or proof.get("beforeGeometryInventoryHash")==digest(basis["geometryInventory"])
            if not bound or proof.get("beforeComplete") is not True or set(proof.get("beforeInventoryPartIds",[]))!=set(int(key) for key in basis["geometryInventory"]):
                return "unknown","before_and_after_discovery_required",[]
        if proof["source"]=="native_bounds_inventory" and not _bounds_far(acceptance["discoveryBasis"],proof,snapshot,goal["source"].get("changedPartIds",[]),goal["source"]["subjectPartIds"]):
            return "unknown","bounds_candidates_need_native_geometry_discovery",[]
        acceptance["discoveryBasis"]=_discovery_basis(snapshot_parts(snapshot),identity(snapshot),snapshot_context(snapshot),proof)
        acceptance["discoveryState"]={"status":"verified","reason":"current_native_impact_discovery","proof":deepcopy(proof)}
        return "pass",None,["discovery-"+digest(proof)[:16]]
    checks = [c for c in report["checks"] if c.get("goalId") == goal["id"] or goal["id"] in c.get("goalIds", [])]
    if goal["source"]["kind"]=="impact_acceptance" and not checks:checks=report["checks"]
    reason = "goal_checks_missing"
    if loop.get("referenceState",{}).get("status")=="changed":return "unknown","reference_binding_changed",[]
    if report.get("identity") != identity(snapshot):
        return "unknown", "report_stale", []
    if not checks:
        return "unknown", reason, []
    statuses = [_STATUS.get(c.get("status"), c.get("status")) for c in checks]
    if "fail" in statuses:
        return "fail", "check_failed", []
    if any(s != "pass" for s in statuses):
        return "unknown", "check_unresolved", []
    required = set(goal["verification"].get("checkIds", []))
    if not required <= {c.get("id") for c in checks}:
        return "unknown", "required_check_missing", []
    covered, reason = _coverage(report, goal["channel"], goal)
    if not covered:
        return "unknown", reason, []
    evidence_by_id = {item.get("id"):item for item in report["evidence"]}
    used = {i for check in checks for i in check.get("evidenceIds", [])}
    if not used:
        return "unknown", "evidence_missing", []
    accepted = []
    for key in sorted(used):
        item = evidence_by_id.get(key)
        valid, reason = _evidence(item, loop, snapshot)
        if not valid:
            return "unknown", reason, []
        accepted.append(item)
    evidence_scopes=goal["verification"].get("impactEvidenceScopes") if goal["source"]["kind"]=="impact_acceptance" else None
    if evidence_scopes is not None:
        for kind,ids in evidence_scopes.items():
            covered_ids={i for e in accepted if e["kind"]==kind for i in e["partIds"]}
            if not (set(ids)&set(_scope(goal)))<=covered_ids:return "unknown","required_impact_evidence_scope_missing:"+kind,[]
        if not set(_scope(goal))<={i for e in accepted for i in e["partIds"]}:return "unknown","impact_evidence_scope_missing",[]
        if goal["source"].get("missingDependencyPartIds"):return "unknown","impact_ownership_rebind_required",[]
    else:
        for kind in goal["verification"]["requiredEvidenceKinds"]:
            covered_ids = {i for e in accepted if e["kind"] == kind for i in e["partIds"]}
            if not set(_scope(goal)) <= covered_ids:
                return "unknown", "required_evidence_kind_or_scope_missing:" + kind, []
    retired={item["sourcePartId"] for item in goal.get("retirementObligations",[])}
    if retired and not retired<={i for item in accepted if item["kind"]=="native_absence" for i in item.get("absentPartIds",[])}:
        return "unknown","retirement_absence_coverage_missing",[]
    return "pass", None, sorted(used)


def _issue_goal(loop, issue, channel, round_number):
    if not isinstance(issue, dict) or not issue.get("id"):
        raise ReferenceError("invalid_review", "Findings need stable IDs")
    if issue.get("related") is False or issue.get("relation") == "unrelated":
        loop["unrelatedFindings"].append({"round":round_number, "channel":channel, **deepcopy(issue)})
        return
    if issue.get("relation") == "full_region_coverage":
        scoped = [g for g in loop["goals"] if g["source"]["kind"] == "user" and set(_scope(g)) & set(issue.get("partIds",[]))]
        finite = {i for g in scoped if g["verification"]["coverageMode"] == "finite_sampled" for i in _scope(g)}
        if scoped and all(g["verification"]["coverageMode"] == "finite_sampled" for g in scoped) and set(issue.get("partIds",[])) <= finite:
            loop.setdefault("acceptedCoverageLimitations",[]).append({"round":round_number,"channel":channel,"finding":deepcopy(issue),
                   "basisGoalIds":[g["id"] for g in scoped],"meaning":"Full-region certification is outside the explicitly accepted finite scope; no full-region pass is claimed."})
            return
    status = _STATUS.get(issue.get("status"), issue.get("status"))
    if status == "pass" and issue.get("resolvedByGoalId"):
        resolved=next((g for g in loop["goals"] if g["id"]==issue["resolvedByGoalId"] and g["status"]=="verified"),None)
        if resolved:loop["unresolvedFindings"]=[f for f in loop["unresolvedFindings"] if not (f["id"]==issue["id"] and f["channel"]==channel)]
    if status not in ("fail", "unknown"):
        return
    goal_id = "issue:" + channel + ":" + str(issue["id"])
    existing = next((g for g in loop["goals"] if g["id"] == goal_id), None)
    if existing:
        existing["status"] = "inspection" if status == "unknown" else "reopened"
        existing["task"] = "inspect" if status == "unknown" else "repair"
        return
    if not issue.get("partIds") and not issue.get("boundaries"):
        loop["unresolvedFindings"].append({"round":round_number, "channel":channel, **deepcopy(issue)})
        return
    value = {**deepcopy(issue), "id":goal_id, "channel":channel, "task":"inspect" if status == "unknown" else "repair"}
    if not isinstance(value.get("expected"),str) or not value["expected"].strip():
        value["expected"] = str(issue.get("reason") or "Determine the cause and required action for " + str(issue["id"]))
    if not isinstance(value.get("verification"),dict):
        ids=set(issue.get("partIds",[])) | {i for b in issue.get("boundaries",[]) for i in b.get("partIds",[])}
        bases=[g for g in loop["goals"] if g["source"]["kind"]=="user" and ids <= (set(_scope(g)) | set(g["scope"].get("impactPartIds",[])))]
        if bases and all(g["verification"]["coverageMode"]=="finite_sampled" for g in bases):
            value["verification"]=deepcopy(bases[0]["verification"])
            value["verification"].pop("checkIds",None)
            value["verification"]["inheritedFromGoalIds"]=[g["id"] for g in bases]
        else:value["verification"]={"requiredEvidenceKinds":["native_mesh_measurement"]}
    loop["goals"].append(_goal(value, {"kind":"finding", "channel":channel, "round":round_number,
                                      "issueId":issue["id"], "evidenceIds":deepcopy(issue.get("evidenceIds", []))}))


def _create(path, payload, snapshot):
    if run_journal.read(path):
        raise ReferenceError("loop_exists", "Do not overwrite an existing loop history")
    if not payload.get("userObjective") or not payload.get("goals"):
        raise ReferenceError("invalid_goal", "Create requires the original user objective and nonempty goals")
    goals = []
    for index,value in enumerate(payload["goals"]):
        try:goals.append(_goal(value, {"kind":"user", "text":payload.get("source", payload["userObjective"])}, [g["id"] for g in goals]))
        except ReferenceError as error:
            error.details['jsonPath']='$.goals['+str(index)+']'+('.expected' if not isinstance(value,dict) or not isinstance(value.get('expected'),str) or not value.get('expected','').strip() else error.details.get('fieldPath',''))
            if error.details['jsonPath'].endswith('.expected'):error.details['correction']='Use expected with a concrete nonempty outcome string; expectedOutcome/outcome are not aliases.'
            raise
        _freeze_protected(goals[-1],snapshot)
    parts = snapshot_parts(snapshot)
    if any(str(i) not in parts for goal in goals for i in _scope(goal)):
        raise ReferenceError("part_not_found", "A goal refers to a missing current part")
    threshold = payload.get("stagnationRounds", 3)
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 2:
        raise ReferenceError("invalid_input", "stagnationRounds must be at least two")
    required=payload.get("completionRequirements",[])
    if not isinstance(required,list) or any(k not in ("visual","nativeSaved","userAestheticApproval") for k in required):
        raise ReferenceError("invalid_input","completionRequirements must name visual, nativeSaved or userAestheticApproval")
    loop = {"kind":KIND, "schemaVersion":1, "loopId":str(uuid.uuid4()), "createdAt":utc_now(), "state":"active",
            "userObjective":payload["userObjective"], "initialGoalIds":[g["id"] for g in goals], "goals":goals,
            "binding":bind(snapshot), "referenceHash":payload.get("referenceHash"), "coordinateFrame":payload.get("coordinateFrame"),
            "round":0, "stagnationRounds":threshold, "stagnationCount":0, "unrelatedFindings":[], "unresolvedFindings":[],
            "completionRequirements":deepcopy(payload.get("completionRequirements",[])),
            "completion":{"userGoals":False, "impact":False, "geometry":False, "visual":False,
                          "nativeSaved":False, "userAestheticApproval":False}, "limitations":["No craft writes or autonomous aesthetic repairs are performed.",
                          "Rebinding supports explicit one-to-one, merged, split and retired ownership with current scoped evidence; protected fields require explicit transfer when ownership splits or retires.",
                          "Completion certifies only explicitly scoped goals and accepted coverage; it is not whole-craft correctness."]}
    return _append(path, "loop_created", loop, payload)


def _review(path, loop, payload, snapshot):
    change_report, protected = _invalidate(loop, snapshot, payload.get("reusedPartIds", []),{key:payload[key] for key in ("referenceHash","coordinateFrame") if key in payload},payload.get("impactDiscovery"))
    reports = {channel:_report(payload, channel) for channel in ("subject", "impact")}
    round_number = loop["round"] + 1
    before_verified = {g["id"] for g in loop["goals"] if g["status"] == "verified"}
    reviewed = []
    for goal in loop["goals"]:
        # An unchanged verified goal retains its actual evidence; an absent new
        # check does not relabel old evidence as a fresh inspection.
        report = reports[goal["channel"]]
        other = reports["impact" if goal["channel"] == "subject" else "subject"]
        if not any(c.get("goalId") == goal["id"] or goal["id"] in c.get("goalIds", []) for c in report["checks"]) and any(
                c.get("goalId") == goal["id"] or goal["id"] in c.get("goalIds", []) for c in other["checks"]):
            report = other
        present = any(c.get("goalId") == goal["id"] or goal["id"] in c.get("goalIds", []) for c in report["checks"])
        if goal["status"] == "verified" and not present:
            continue
        status, reason, evidence_ids = _review_goal(goal, report, loop, snapshot)
        goal["status"] = "verified" if status == "pass" else "inspection" if status == "unknown" else "pending"
        goal["task"] = "inspect" if status == "unknown" else "repair"
        result = {"goalId":goal["id"], "round":round_number, "identity":identity(snapshot), "status":status,
                  "reason":reason, "evidenceIds":evidence_ids}
        goal["verificationHistory"].append(result)
        reviewed.append(result)
    for channel, report in reports.items():
        for issue in report["issues"]:
            _issue_goal(loop, issue, channel, round_number)
    for issue in protected:
        _issue_goal(loop, issue, "impact", round_number)
    verified = {g["id"] for g in loop["goals"] if g["status"] == "verified"}
    loop["stagnationCount"] = 0 if verified - before_verified else loop["stagnationCount"] + 1
    pending = [g for g in loop["goals"] if g["status"] != "verified"]
    impact = reports["impact"]
    impact_coverage = impact.get("coverageSummary", impact.get("coverage", {}))
    impact_ids = set(impact_coverage.get("partIds", impact_coverage.get("impactPartIds", []))) if isinstance(impact_coverage, dict) else set()
    required_impact = set(payload.get("affectedPartIds", [])) | impact_ids | set(loop.get("impactRequiredPartIds",[])) | {i for g in loop["goals"] for i in g.get("scope", {}).get("impactPartIds", [])}
    loop["impactRequiredPartIds"]=sorted(required_impact)
    finite_ids = {i for g in loop["goals"] if g["status"] == "verified" and g["verification"]["coverageMode"] == "finite_sampled" for i in _scope(g)}
    complete_coverage = isinstance(impact_coverage, dict) and impact_coverage.get("status") in ("complete", "pass", "passed") and not impact_coverage.get("unobserved")
    accepted_finite = isinstance(impact_coverage, dict) and impact_coverage.get("status") == "finite_sampled" and required_impact <= finite_ids
    impact_ok = (impact.get("identity") == identity(snapshot) and (complete_coverage or accepted_finite)
                 and not impact_coverage.get("missingMeshPartIds") and required_impact <= impact_ids
                 and all(_STATUS.get(c.get("status"), c.get("status")) == "pass" for c in impact["checks"]))
    # Even an empty impact set needs a scoped review with an explicit exclusion reason.
    if not required_impact and not impact["checks"] and not impact.get("noImpactReason"):
        impact_ok = False
    if impact_ok and required_impact:
        valid_impact = [e for e in impact["evidence"] if _evidence(e, loop, snapshot)[0]]
        impact_ok = required_impact <= {i for e in valid_impact for i in e["partIds"]}
    if loop.get("referenceState",{}).get("status")=="changed":impact_ok=False
    if impact_ok and not required_impact:
        subject_ids={i for goal in loop["goals"] if goal["source"]["kind"]=="user" for i in _scope(goal)}
        external={int(key) for key in snapshot_parts(snapshot)}-subject_ids
        proof=impact.get("discovery");proof_valid,_=_discovery_proof(proof,snapshot)
        if external and (not proof_valid or proof["source"]=="native_bounds_inventory" and not _bounds_far(_discovery_basis(snapshot_parts(snapshot),identity(snapshot),snapshot_context(snapshot)),proof,snapshot,external,subject_ids)):
            if not loop.get("impactAcceptance"):loop["impactAcceptance"]=_impact_acceptance(loop,impact,[],bind(snapshot))
            _rediscovery_goal(loop,snapshot,external,"empty_impact_discovery_unproven");impact_ok=False
    if loop.get("impactAcceptance",{}).get("discoveryState",{}).get("status")=="pending":impact_ok=False
    if impact_ok:loop["impactAcceptance"]=_impact_acceptance(loop,impact,required_impact,bind(snapshot))
    verified={g["id"] for g in loop["goals"] if g["status"]=="verified"};pending=[g for g in loop["goals"] if g["status"]!="verified"]
    loop["completion"].update(userGoals=all(g["id"] in verified for g in loop["goals"] if g["source"]["kind"] == "user"),
                              impact=impact_ok, geometry=not pending)
    # These records are deliberately independent of geometry and command success.
    for field, kind in (("visual", "visual_review"), ("nativeSaved", "native_save"), ("userAestheticApproval", "user_approval")):
        items = payload.get("completionEvidence", [])
        loop["completion"][field] = any(e.get("kind") == kind and _evidence(e, loop, snapshot)[0] and e.get("status") == "pass" for e in items)
    loop["round"] = round_number
    loop["binding"] = bind(snapshot)
    complete = not pending and impact_ok and not loop["unresolvedFindings"] and all(loop["completion"].get(k) is True for k in loop["completionRequirements"])
    loop["state"] = "complete" if complete else "reconsider_required" if loop["stagnationCount"] >= loop["stagnationRounds"] else "active"
    loop["nextAction"] = "none" if complete else "reassess_representation_and_reference" if loop["state"] == "reconsider_required" else "execute_next_round_goals"
    return _append(path, "round_reviewed", loop, payload, subjectReview=reports["subject"], impactReview=impact,
                   goalResults=reviewed, changeReport=change_report, protectedFieldChanges=protected)


def _rebind_loop(path,loop,payload,snapshot):
    """Transfer region obligations, never infer semantic ownership from an ID."""
    _chronology(loop["binding"],snapshot)
    raw=payload.get("semanticMapping",payload.get("partMapping"))
    if not isinstance(raw,dict) or not payload.get("mappingEvidence"):
        raise ReferenceError("rebind_required","Rebinding requires explicit ownership and supporting evidence")
    required={i for goal in loop["goals"] for i in _scope(goal)} | {i for goal in loop["goals"] for i in goal["scope"].get("impactPartIds",[])} | {f["partId"] for goal in loop["goals"] for f in goal["protectedFields"]} | set(loop.get("impactRequiredPartIds",[]))
    try:mapped={int(k):_ids(v if isinstance(v,list) else [v],"semanticMapping") for k,v in raw.items()}
    except (TypeError,ValueError) as exc:raise ReferenceError("invalid_binding","Mapping IDs must be nonnegative integers") from exc
    parts=snapshot_parts(snapshot)
    if not required<=set(mapped) or any(str(i) not in parts for values in mapped.values() for i in values):
        raise ReferenceError("invalid_binding","Mapping must cover every scoped source and refer to existing current targets")
    if "semanticMapping" in payload and "partMapping" in payload:
        anchors=payload["partMapping"]
        if not isinstance(anchors,dict) or any(int(old) not in mapped or target not in mapped[int(old)] for old,target in anchors.items()):
            raise ReferenceError("invalid_binding","Legacy connection anchors must belong to the explicit semantic target set")
    evidence=payload["mappingEvidence"];valid,reason=_evidence(evidence,loop,snapshot)
    if not valid or evidence.get("kind")!="part_mapping" or evidence.get("reviewed") is not True:
        raise ReferenceError("invalid_binding","Part mapping needs reviewed, current scoped evidence",reason=reason)
    ownership=evidence.get("ownershipMapping",[])
    if not isinstance(ownership,list):raise ReferenceError("invalid_binding","ownershipMapping must be an explicit list")
    support={};retirement={}
    def owner(sources,targets,strict=False):
        matches=[item for item in ownership if isinstance(item,dict) and set(item.get("sourcePartIds",[]))==set(sources)
                 and set(item.get("targetPartIds",[]))==set(targets) and item.get("reason")
                 and (item.get("structureId") or item.get("planHash"))]
        if strict:matches=[item for item in matches if item.get("structureId") and item.get("planHash") and item["planHash"]==evidence.get("planHash")]
        if len(matches)!=1:raise ReferenceError("invalid_binding","Split, merged or retired ownership needs unambiguous semantic evidence",sourcePartIds=sources,targetPartIds=targets)
        return matches[0]
    for old,targets in mapped.items():
        if len(targets)>1:owner([old],targets,True)
        if targets:continue
        item=owner([old],[],True);ids=_ids(item.get("supportPartIds"),"supportPartIds")
        if not ids or any(str(i) not in parts for i in ids) or str(old) in parts:
            raise ReferenceError("invalid_retirement","Retirement requires absent old IDs and a nonempty current region supporting the original obligation",sourcePartId=old)
        check=next((check for check in evidence.get("absenceChecks",[]) if check.get("sourcePartId")==old),None)
        if not isinstance(check,dict) or check.get("absent") is not True or check.get("identity")!=identity(snapshot) or set(check.get("supportPartIds",[]))!=set(ids) or check.get("scopeHash")!=scope_hash(snapshot,ids):
            raise ReferenceError("invalid_retirement","Retirement requires current scoped absence-check evidence",sourcePartId=old)
        support[old]=ids;retirement[old]={"sourcePartId":old,"supportPartIds":ids,"mappingEvidenceId":evidence["id"],"planHash":item["planHash"],"structureId":item["structureId"],"absenceCheck":deepcopy(check)}
    all_targets={i for values in mapped.values() for i in values}|{i for values in support.values() for i in values}
    if not all_targets<=set(evidence.get("partIds",[])):
        raise ReferenceError("invalid_binding","Mapping evidence omits current ownership/support parts")
    merges={target:sorted(old for old,values in mapped.items() if target in values) for target in all_targets}
    for target,sources in merges.items():
        if len(sources)>1:owner(sources,[target])
    transfers=payload.get("protectedFieldMapping",[])
    if not isinstance(transfers,list):raise ReferenceError("protected_mapping_required","protectedFieldMapping must be a list")
    new_fields={};frozen={}
    for goal in loop["goals"]:
        rows=[]
        for baseline in goal.get("protectionBaseline",[]):
            old,path_=baseline["partId"],baseline["path"];targets=mapped[old]
            declared=[row for row in transfers if isinstance(row,dict) and row.get("sourcePartId")==old and row.get("sourcePath")==path_]
            if len(targets)!=1 and len(declared)!=1:
                raise ReferenceError("protected_mapping_required","Split/retired protected fields require explicit target fields; pose/length protections cannot fan out automatically",sourcePartId=old,path=path_)
            if len(declared)>1:raise ReferenceError("protected_mapping_conflict","Duplicate protected-field transfer")
            fields=declared[0].get("targets") if declared else [{"partId":targets[0],"path":path_}]
            if not isinstance(fields,list) or not fields:
                raise ReferenceError("protected_mapping_required","Protected obligations cannot be retired without an explicit surviving field")
            for target in fields:
                if not isinstance(target,dict) or target.get("partId") not in set(targets or support.get(old,[])) or not isinstance(target.get("path"),str) or not target["path"].startswith("/"):
                    raise ReferenceError("protected_mapping_conflict","Transferred protection must address an owned target or declared retirement support")
                if "value" in target and target["value"]!=baseline["value"]:
                    raise ReferenceError("protected_mapping_conflict","Rebinding cannot relax or redefine a frozen protected value")
                key=(target["partId"],target["path"])
                if key in frozen and frozen[key]["value"]!=baseline["value"]:
                    raise ReferenceError("protected_mapping_conflict","Merged ownership has conflicting frozen protected values; review protections explicitly",targetPartId=key[0],path=key[1],goalIds=[frozen[key]["goalId"],goal["id"]])
                frozen[key]={"value":deepcopy(baseline["value"]),"goalId":goal["id"]}
                rows.append({**deepcopy(baseline),"partId":key[0],"path":key[1],"sourceField":{"partId":old,"path":path_}})
        new_fields[goal["id"]]=rows
    def expand(ids):return sorted({new for old in ids for new in (mapped[old] or support[old])})
    for goal in loop["goals"]:
        old_scope=set(_scope(goal))|set(goal["scope"].get("impactPartIds",[]))
        goal.setdefault("ownershipHistory",[]).append({"at":utc_now(),"partIds":deepcopy(goal["partIds"]),"scope":deepcopy(goal["scope"]),"boundaries":deepcopy(goal["boundaries"]),"protectedFields":deepcopy(goal["protectedFields"]),"protectionBaseline":deepcopy(goal.get("protectionBaseline",[])),"mappingEvidenceId":evidence["id"]})
        goal["partIds"]=expand(goal["partIds"]);goal["scope"]["partIds"]=expand(goal["scope"]["partIds"])
        goal["scope"]["impactPartIds"]=expand(goal["scope"].get("impactPartIds",[]))
        for boundary in goal["boundaries"]:boundary["partIds"]=expand(boundary["partIds"])
        for obligation in goal.get("retirementObligations",[]):obligation["supportPartIds"]=expand(obligation["supportPartIds"])
        retired=[deepcopy(retirement[old]) for old in old_scope&set(retirement)]
        if retired:
            goal.setdefault("retirementObligations",[]).extend(retired)
            goal["verification"]["requiredEvidenceKinds"]=sorted(set(goal["verification"]["requiredEvidenceKinds"])|{"native_absence"})
        goal["protectionBaseline"]=new_fields[goal["id"]]
        goal["protectedFields"]=[{k:deepcopy(v) for k,v in field.items() if k not in ("value","sourceField")} for field in goal["protectionBaseline"]]
        goal["status"]="inspection";goal["task"]="inspect"
        goal["verificationHistory"].append({"at":utc_now(),"status":"invalidated","reason":"explicit_rebind_requires_fresh_geometry","mappingEvidenceId":evidence["id"]})
    loop["impactRequiredPartIds"]=expand(loop.get("impactRequiredPartIds",[]))
    if loop.get("impactAcceptance"):
        acceptance=loop["impactAcceptance"]
        acceptance.setdefault("ownershipHistory",[]).append({"identity":deepcopy(acceptance["binding"]["identity"]),"partIds":deepcopy(acceptance["partIds"]),"mappingEvidenceId":evidence["id"]})
        acceptance["partIds"]=expand(acceptance["partIds"])
        acceptance["evidenceScopes"]={kind:expand(ids) for kind,ids in acceptance["evidenceScopes"].items()}
        acceptance["binding"]=bind(snapshot,acceptance["partIds"]);acceptance["status"]="invalidated"
        _impact_recheck(loop,snapshot,"explicit_impact_ownership_rebind_requires_fresh_evidence",{"mappingEvidenceId":evidence["id"]})
    loop["binding"]=bind(snapshot);loop["state"]="active";loop["completion"]={key:False for key in loop["completion"]}
    # JSON keys must sort identically before hashing and after journal reload.
    return _append(path,"loop_rebound",loop,payload,semanticMapping={str(old):targets for old,targets in mapped.items()},partMapping=deepcopy(payload.get("partMapping")),mappingEvidence=deepcopy(evidence),protectedFieldMapping=deepcopy(transfers))


def dispatch(action, payload=None, context=None):
    """Actions: build.loop.create, inspect, review, amend, rebind (also short names)."""
    payload = payload or {}
    action = action.rsplit(".", 1)[-1]
    path = payload.get("journalPath")
    if not path:
        raise ReferenceError("invalid_input", "Build loop actions require journalPath")
    if action in ("inspect", "status"):
        loop, entries = _load(path)
        snapshot = payload.get("snapshot")
        if snapshot:_chronology(loop["binding"],snapshot)
        report = _loop_changes(loop,snapshot,payload.get("reusedPartIds",[])) if snapshot else None
        rebind_task=None
        if snapshot and report["status"]=="rebind_required":
            previous_identity=deepcopy(loop["binding"]["identity"])
            loop["historicalState"]=loop["state"]
            loop["previousAcceptance"]={"identity":previous_identity,"completion":deepcopy(loop["completion"]),"state":loop["state"]}
            loop["state"]="rebind_required";loop["nextAction"]="inspect_current_craft_and_rebind"
            loop["currentIdentity"]=identity(snapshot);loop["completion"]={key:False for key in loop["completion"]}
            rebind_task={"id":"system:current-craft-rebind","task":"inspect","status":"inspection","channel":"impact","partIds":[],
                "scope":{"partIds":[]},"expected":"Inspect the current craft and explicitly bind original semantic goals before editing",
                "source":{"kind":"current_craft_rebind","reason":report.get("reason"),"previousBindingIdentity":previous_identity,
                          "currentIdentity":identity(snapshot),"repairInferred":False,"oldNumericIdsAreCurrentTargets":False}}
        if snapshot and report["status"] != "rebind_required":
            _invalidate(loop,snapshot,payload.get("reusedPartIds",[]),{key:payload[key] for key in ("referenceHash","coordinateFrame") if key in payload},payload.get("impactDiscovery"))
            if any(g["status"] != "verified" for g in loop["goals"]):
                loop["state"]="active"
                loop["completion"].update(userGoals=all(g["status"]=="verified" for g in loop["goals"] if g["source"]["kind"]=="user"),geometry=False)
                for field in ("visual","nativeSaved","userAestheticApproval"):loop["completion"][field]=False
        return {"journalPath":str(Path(path).resolve()), "headHash":entries[-1]["entryHash"], "loop":loop,
                "changeReport":report, "currentStateVerified":bool(snapshot and report["status"] == "compatible" and loop.get("referenceState",{}).get("status")!="changed" and loop.get("impactAcceptance",{}).get("status","verified")=="verified" and loop.get("impactAcceptance",{}).get("discoveryState",{}).get("status")!="pending"),
                "stateInterpretation":"current" if snapshot else "historical",
                "nextRoundGoals":[rebind_task] if rebind_task else [g for g in loop["goals"] if g["status"] != "verified"], "writesIssued":False}
    if action not in ("create", "review", "amend", "rebind"):
        raise ReferenceError("unknown_action", "Unknown build loop action", action=action)
    with _lock(path):
        entries = run_journal.read(path)
        if payload.get("requestId"):
            matching = [entry for entry in entries if entry.get("requestId") == payload["requestId"]]
            if matching:
                if matching[-1].get("inputHash") != digest(payload):
                    raise ReferenceError("request_changed", "A recorded request ID cannot be used with different input")
                return {"journalPath":str(Path(path).resolve()), "headHash":entries[-1]["entryHash"], "loop":deepcopy(entries[-1]["loop"]),
                        "replayed":False, "alreadyRecorded":True, "writesIssued":False}
        if "expectedHeadHash" in payload and payload["expectedHeadHash"] != (entries[-1]["entryHash"] if entries else None):
            raise ReferenceError("loop_changed", "Loop history changed since this decision was prepared")
        snapshot = _snapshot(payload, context)
        if action == "create":
            return _create(path, payload, snapshot)
        loop, entries = _load(path)
        if action == "review":
            return _review(path, loop, payload, snapshot)
        if action == "amend":
            _invalidate(loop, snapshot, payload.get("reusedPartIds", []),{key:payload[key] for key in ("referenceHash","coordinateFrame") if key in payload},payload.get("impactDiscovery"))
            if not payload.get("source") or not payload.get("goals"):
                raise ReferenceError("invalid_goal", "User amendments need source text and additional goals")
            for value in payload["goals"]:
                goal = _goal(value, {"kind":"user", "text":payload["source"], "round":loop["round"]}, [g["id"] for g in loop["goals"]])
                _freeze_protected(goal,snapshot)
                loop["goals"].append(goal)
                loop["initialGoalIds"].append(goal["id"])
            loop["state"] = "active"
            for key in ("referenceHash","coordinateFrame"):
                if key in payload:loop[key]=deepcopy(payload[key])
            if any(key in payload for key in ("referenceHash","coordinateFrame")):loop["referenceState"]={"status":"compatible","differences":{}}
            loop["completion"] = {key:False for key in loop["completion"]}
            loop["binding"] = bind(snapshot)
            return _append(path, "user_goals_added", loop, payload)
        return _rebind_loop(path,loop,payload,snapshot)
