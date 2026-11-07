"""Guarded, journalled replacement. Live access is injected, never desktop automation."""
from __future__ import annotations
from copy import deepcopy
import uuid
from reference_storage import ReferenceError, digest
from reference_binding import unwrap, identity, bind, changes, snapshot_parts, snapshot_context, canonical_connection_key
from structure_plan import validate, compile_operations, inspect_impact, _removed
from quality_gates import evaluate
import run_journal


def _live(context):
    callback=(context or {}).get("live")
    if not callable(callback):raise ReferenceError("live_required","This action needs an injected live sp2build transport")
    return callback


def _state(entries):
    for entry in reversed(entries):
        if "runtime" in entry:return deepcopy(entry["runtime"])
    return None


def _record(path,event,runtime,**data):
    return run_journal.append(path,event,runtime=deepcopy(runtime),state=runtime["state"],**data)


def _loop_review(plan,payload,snapshot,context,runtime=None):
    if not plan.get("loopJournalPath"):return None
    import build_loop
    review=deepcopy(payload.get("loopReview"));rebound=None
    if runtime and runtime["state"]=="finalized" and plan.get("oldPartIds"):
        state=build_loop.dispatch("inspect",{"journalPath":plan["loopJournalPath"]})["loop"]
        required={i for goal in state["goals"] for i in build_loop._scope(goal)} | {i for goal in state["goals"] for i in goal["scope"].get("impactPartIds",[])} | {f["partId"] for goal in state["goals"] for f in goal["protectedFields"]} | set(state.get("impactRequiredPartIds",[]))
        if required&set(plan["oldPartIds"]):
            resolve=lambda item:runtime["temporaryIds"][item] if isinstance(item,str) else item
            semantics=plan.get("semanticMapping",{key:[name] for key,name in plan["partMapping"].items()})
            mapping={old:[resolve(name) for name in semantics[str(old)]] if str(old) in semantics else [old] for old in required}
            ownership=[];supports={}
            for row in plan.get("ownershipMapping",[]):
                item=deepcopy(row);item["targetPartIds"]=[resolve(name) for name in item["targetPartIds"]]
                if "supportPartIds" in item:item["supportPartIds"]=[resolve(name) for name in item["supportPartIds"]]
                item["planHash"]=plan["contentHash"];ownership.append(item)
                if not item["targetPartIds"]:
                    for old in item["sourcePartIds"]:supports[old]=item["supportPartIds"]
            targets=sorted({i for values in mapping.values() for i in values}|{i for values in supports.values() for i in values})
            for target in targets:
                sources=sorted(old for old,values in mapping.items() if target in values)
                if sources and not any(set(row["sourcePartIds"])==set(sources) and row["targetPartIds"]==[target] for row in ownership):
                    ownership.append({"sourcePartIds":sources,"targetPartIds":[target],"planHash":plan["contentHash"],
                                      "structureId":plan.get("structureId"),"reason":"Explicit ownership mapping in immutable finalized structure plan"})
            absence=[{"sourcePartId":old,"absent":str(old) not in snapshot_parts(snapshot),"identity":identity(snapshot),"supportPartIds":ids,"scopeHash":build_loop.scope_hash(snapshot,ids)} for old,ids in supports.items() if old in mapping and not mapping[old]]
            evidence={"id":"mapping-"+plan["planId"],"kind":"part_mapping","reviewed":True,"identity":identity(snapshot),
                      "partIds":targets,"scopeHash":build_loop.scope_hash(snapshot,targets),"referenceHash":state.get("referenceHash"),
                      "coordinateFrame":state.get("coordinateFrame"),"ownershipMapping":ownership,"planHash":plan["contentHash"],"absenceChecks":absence}
            protected=deepcopy(plan.get("protectedFieldMapping",[]))
            for row in protected:
                for target in row["targets"]:target["partId"]=resolve(target["partId"])
            rebound=build_loop.dispatch("rebind",{"journalPath":plan["loopJournalPath"],"snapshot":snapshot,"semanticMapping":mapping,
                         "protectedFieldMapping":protected,"mappingEvidence":evidence,"requestId":"structure-map-"+plan["planId"]+"-"+digest(identity(snapshot))},context)
    if not review:return rebound
    # Re-entering an already successful native plan may add new review evidence,
    # but identical review submissions are decisions with the same identity.
    review.setdefault("requestId","structure-"+plan["planId"]+"-"+digest({"identity":identity(snapshot),"review":review}))
    return build_loop.dispatch("review",{**review,"journalPath":plan["loopJournalPath"],"snapshot":snapshot},context)


def _snapshot(live):
    value=unwrap(live("craft.snapshot",{"includeXml":True}))
    identity(value)
    return value


def _guard(runtime,snapshot):
    report=changes(runtime["binding"],snapshot,runtime["guardPartIds"])
    if report["status"]!="compatible":
        raise ReferenceError("state_changed","Protected structure changed; reconcile before further writes",changeReport=report)
    return report


def _replacement_readback(plan,runtime,before,current,parameters,receipt):
    """Reject undeclared callbacks before a fresh binding can absorb them."""
    previous=before["baselineParts"];actual=snapshot_parts(current)
    all_ids=set(int(key) for key in previous)|set(int(key) for key in actual)
    delta=changes(before,current,sorted(all_ids))
    refs={**runtime.get("temporaryIds",{}),**receipt.get("temporaryIds",{})}
    resolve=lambda value:refs.get(value,value) if isinstance(value,str) else value
    created=set(receipt.get("temporaryIds",{}).values())|{i for row in receipt.get("actualChanges",[]) if row.get("kind")=="part.add" for i in row.get("partIds",[])}|{i for row in receipt.get("actualChanges",[]) for i in row.get("createdPartIds",[])}
    deleted=set();editable=set(plan.get("expectedChanges",{}).get("allowedChangedPartIds",[]));pairs=set();variable_edit=False
    for operation in parameters.get("operations",[]):
        kind=operation.get("kind")
        ids={resolve(operation[field]) for field in ("partId","wingPartId","sourcePartId","anchorPartId") if operation.get(field) is not None}|{resolve(i) for i in operation.get("partIds",[])}
        ids={i for i in ids if isinstance(i,int) and not isinstance(i,bool)}
        if kind=="part.delete":deleted.update(ids)
        elif kind in ("connection.connect","connection.disconnect"):
            pairs.add(tuple(sorted((resolve(operation["partA"]),resolve(operation["partB"])))))
        else:editable.update(ids)
        if kind=="symmetry.unlink":
            groups={previous.get(str(i),{}).get("symmetryId",0) for i in ids}-{0}
            editable.update(int(key) for key,value in previous.items() if value.get("symmetryId",0) in groups)
        if kind.startswith("variable."):variable_edit=True
    editable.update(created)
    added={int(key) for key in set(actual)-set(previous)};removed={int(key) for key in set(previous)-set(actual)}
    unexpected=[]
    for key in set(previous)&set(actual):
        left=deepcopy(previous[key]);right=deepcopy(actual[key]);left.pop("connectedPartIds",None);right.pop("connectedPartIds",None)
        if left!=right and int(key) not in editable:unexpected.append(int(key))
    topology=[]
    for row in delta["topologyConflicts"]:
        for edge in (row["before"],row["after"]):
            if not edge:continue
            endpoints={edge["partA"],edge["partB"]}
            if tuple(sorted(endpoints)) in pairs or endpoints&deleted or endpoints<=created:continue
            topology.append(row);break
    globals_=[value for value in delta["globalConflicts"] if value!="variables" or not variable_edit]
    if unexpected or created&{int(key) for key in previous} or added-created or removed-deleted or topology or globals_ or delta["materialConflicts"] or delta["unrelatedMaterialChanges"]:
        raise ReferenceError("unexpected_readback_changes","Replacement changed undeclared parts, topology or shared state; preserve current state and reconcile without replay",
                             partIds=sorted(unexpected),unexpectedAddedPartIds=sorted(added-created),unexpectedDeletedPartIds=sorted(removed-deleted),changeReport=delta)
    return delta


def _mutate(live,path,runtime,command,parameters,stage,plan=None):
    snapshot=_snapshot(live);report=_guard(runtime,snapshot);ident=identity(snapshot)
    if stage=="restore":_restore_external_guard(runtime,snapshot)
    request_id=str(uuid.uuid4())
    payload={**parameters,"craftSessionId":ident["craftSessionId"],"expectedRevision":ident["revision"],"requestId":request_id}
    runtime["state"]="applying";runtime["pendingStage"]=stage
    _record(path,"write_prepared",runtime,command=command,requestId=request_id,payload=payload,identity=ident,preservedUnrelatedPartIds=report["unrelated"],
            beforeBinding=bind(snapshot))
    try:
        raw=live(command,payload)
        receipt=unwrap(raw)
    except Exception as exc:
        details=getattr(exc,"details",{})
        details=deepcopy(details) if isinstance(details,dict) else {}
        failure={"code":getattr(exc,"code","transport_failed"),"message":str(exc),"details":details}
        operation_id=details.get("operationId");job=None;query_error=None
        if operation_id:
            try:
                job=unwrap(live("operation.status",{"id":operation_id}))
                if not isinstance(job,dict) or job.get("operationId",operation_id)!=operation_id:
                    raise ReferenceError("operation_mismatch","Status returned another operation")
            except Exception as query_exc:
                job=None;query_error={"code":getattr(query_exc,"code","status_failed"),"message":str(query_exc)}
        terminal_failed=job is not None and job.get("state") in ("failed","cancelled")
        rejected=not operation_id and details.get("writeDisposition")=="rejected_before_acceptance"
        if terminal_failed or rejected:
            runtime["state"]="failed";runtime["pendingStage"]=None;runtime["failure"]=failure
            _record(path,"write_failed" if terminal_failed else "write_rejected",runtime,
                    requestId=request_id,operationId=operation_id,error=failure,operation=job,
                    nextAction="new_plan_required")
            raise ReferenceError("new_plan_required","Write failed. Preserve candidates and create a new reviewed plan before further execution",
                                 requestId=request_id,operationId=operation_id,error=failure,operation=job) from exc
        # A timeout may refer to a completed success, but still requires normal
        # reconciliation to validate its receipt. No pending mutation is retried.
        runtime["state"]="reconcileRequired"
        _record(path,"write_unknown",runtime,requestId=request_id,operationId=operation_id,error=failure,operation=job,statusQueryError=query_error,reason=str(exc))
        raise ReferenceError("result_unknown","Write outcome is unknown. Query the original operation; do not replay the plan",requestId=request_id,operationId=operation_id,error=failure) from exc
    try:
        if command=="craft.checkpoint.create":
            current=_snapshot(live)
            receipt_id=identity(current)
            if any(receipt.get(key)!=receipt_id.get(key) for key in ("craftSessionId","revision","fingerprint")):
                raise ReferenceError("state_changed","Checkpoint metadata differs from current craft")
        else:receipt_id=identity(receipt)
        if receipt_id["craftSessionId"]!=ident["craftSessionId"]:raise ReferenceError("session_changed","Write returned another session")
        operation_id=receipt.get("operationId") or (raw.get("operationId") if isinstance(raw,dict) else None)
        reused=receipt.get("reusedPartIds",[])
        old_ids=set(runtime["oldPartIds"])
        if any(item.get("partId") in old_ids for item in reused):
            raise ReferenceError("id_reused","Old part ID was reused during replacement; refuse deletion by stale identity",reusedPartIds=reused)
        current=_snapshot(live)
        if identity(current)!=receipt_id:
            # A user edit after the receipt has no reliable attribution. Keep the receipt and stop.
            raise ReferenceError("state_changed","State changed after write receipt; explicit reconciliation is required")
        actual_parts=snapshot_parts(current)
        if any(actual_parts.get(key)!=value for key,value in runtime.get("lockedParts",{}).items()):
            raise ReferenceError("locked_scope_changed","Native callbacks changed a locked part; inspect before further writes")
        if runtime.get("mode")=="reshape":
            prewrite=bind(snapshot)
            delta=changes(prewrite,current,list(int(k) for k in prewrite["baselineParts"]))
            unexpected=set(delta["changedPartIds"])-set(runtime["permittedChangedPartIds"])
            if set(actual_parts)!=set(runtime["binding"]["baselineParts"]) or unexpected or delta["globalConflicts"] or delta["materialConflicts"] or delta["topologyConflicts"]:
                raise ReferenceError("unexpected_readback_changes","In-place edit changed undeclared parts, assembly or shared state; reconcile without replay",
                                     partIds=sorted(unexpected),changeReport=delta)
        elif stage!="restore":_replacement_readback(plan or {},runtime,bind(snapshot),current,parameters,receipt)
        runtime["lastReceipt"]=receipt
        runtime["temporaryIds"].update(receipt.get("temporaryIds",{}))
        created={i for change in receipt.get("actualChanges",[]) for i in (change.get("partIds",[]) if change.get("kind")=="part.add" else change.get("createdPartIds",[]))}
        runtime["newPartIds"]=sorted(set(runtime.get("newPartIds",[]))|created|set(runtime["temporaryIds"].values()))
        runtime["guardPartIds"]=sorted(set(runtime["guardPartIds"])|set(runtime["newPartIds"]))
        live_ids=set(int(key) for key in snapshot_parts(current))
        runtime["guardPartIds"]=[i for i in runtime["guardPartIds"] if i in live_ids]
        runtime["binding"]=bind(current,runtime["guardPartIds"])
        runtime["pendingStage"]=None
        runtime["completedStages"].append(stage)
        _record(path,"write_completed",runtime,requestId=request_id,operationId=operation_id,receipt=receipt)
        return receipt
    except Exception as exc:
        runtime["state"]="reconcileRequired"
        _record(path,"write_unknown",runtime,requestId=request_id,operationId=receipt.get("operationId"),receipt=receipt,reason=str(exc))
        if isinstance(exc,ReferenceError):raise
        raise ReferenceError("reconcile_required","Write completed but readback could not be validated",reason=str(exc)) from exc


def _quality(plan,runtime,snapshot,payload,context,phase):
    if plan.get("protectedTransferBaseline"):
        import build_loop
        current=snapshot_parts(snapshot);mismatches=[]
        for field in plan["protectedTransferBaseline"]:
            target=runtime["temporaryIds"].get(field["partId"],field["partId"])
            actual=build_loop._pointer(current.get(str(target),{}),field["path"])
            if actual!=field["value"]:mismatches.append({**deepcopy(field),"currentPartId":target,"actual":deepcopy(actual)})
        if mismatches:return {"status":"fail","reason":"protected_transfer_mismatch","fields":mismatches}
    callback=(context or {}).get("validateGeometry" if phase=="geometry" else "validateFinal")
    evidence=callback(plan,runtime["temporaryIds"],snapshot) if callable(callback) else payload.get("geometryEvidence" if phase=="geometry" else "finalEvidence")
    if not evidence:return {"status":"unknown","reason":"fresh_"+phase+"_evidence_required"}
    if evidence.get("identity")!=identity(snapshot):return {"status":"unknown","reason":"evidence_stale"}
    support={runtime["temporaryIds"][i] if isinstance(i,str) else i for row in plan.get("ownershipMapping",[]) for i in row.get("supportPartIds",[])}
    live_ids={int(key) for key in snapshot_parts(snapshot)}
    surviving_guard=(set(runtime["guardPartIds"])-set(plan["oldPartIds"]))&live_ids
    exclusions=evidence.get("coverageExclusions",[])
    if not isinstance(exclusions,list):return {"status":"unknown","reason":"invalid_coverage_exclusions"}
    excluded=set()
    for item in exclusions:
        if not isinstance(item,dict) or not item.get("reason") or item.get("basis")!="unchanged_locked_fields" or item.get("partId") not in plan["lockedPartIds"]:
            return {"status":"unknown","reason":"unsupported_coverage_exclusion"}
        key=str(item["partId"])
        if snapshot_parts(snapshot).get(key)!=runtime["lockedParts"].get(key):return {"status":"fail","reason":"excluded_locked_part_changed"}
        excluded.add(item["partId"])
    required=set(runtime.get("newPartIds",runtime["temporaryIds"].values()))|support|(surviving_guard-excluded)
    if not required<=set(evidence.get("partIds",[])):
        return {"status":"unknown","reason":"candidate_or_boundary_coverage_missing","missingPartIds":sorted(required-set(evidence.get("partIds",[])))}
    profile=plan.get("qualityProfile")
    if not profile:return {"status":"unknown","reason":"frozen_quality_profile_required"}
    result=evaluate(profile,evidence)
    if phase=="final":
        remaining=set(plan["oldPartIds"]) & set(int(key) for key in snapshot_parts(snapshot))
        if remaining:return {"status":"fail","reason":"old_parts_remain","partIds":sorted(remaining)}
        topology=_dependency_state(plan,runtime,snapshot,final=True)
        if topology["status"]!="pass":return {"status":"fail","reason":"dependency_readback_failed","dependencyReport":topology}
        material=_material_state(plan,runtime,snapshot)
        if material["status"]!="pass":return {"status":material["status"],"reason":"material_intent_mismatch" if material["status"]=="fail" else "material_evidence_required","materialReport":material}
        required=("oldPartsAbsent","dependenciesValid","materialsValid","symmetryValid","noDuplicateOwnedSurfaces","lockedPartsPreserved")
        missing=[key for key in required if evidence.get("checks",{}).get(key) is not True]
        if missing:result.update(status="unknown",reason="finalization_checks_missing",missingChecks=missing)
    return result


def _dependency_state(plan,runtime,snapshot,final=False):
    parts=snapshot_parts(snapshot);current=snapshot_context(snapshot);missing=[]
    old=[i for i in plan["oldPartIds"] if str(i) in parts]
    if old:
        live_impact=inspect_impact(snapshot,old)
        if live_impact["nestedReferences"]:missing.append({"kind":"old_nested_references","references":live_impact["nestedReferences"]})
        for group in live_impact["symmetryGroups"]:missing.append({"kind":"old_symmetry_still_linked","group":group})
    impact=plan.get("impact",{});mapping={int(old):runtime["temporaryIds"][temp] for old,temp in plan["partMapping"].items()}
    planned=compile_operations(plan,"migration",runtime["temporaryIds"])
    for category,allow_name in (("externalConnections","removeExternalConnections"),("internalConnections","removeInternalConnections")):
        removed=_removed(plan.get("expectedChanges",{}),allow_name)
        for old_connection in impact.get(category,[]):
            a=mapping.get(old_connection["partA"],old_connection["partA"]);b=mapping.get(old_connection["partB"],old_connection["partB"])
            if a==b or old_connection["key"] in removed:continue
            required=[op for op in planned if op.get("kind")=="connection.connect" and (op.get("partA"),op.get("partB")) in ((a,b),(b,a))]
            if not required:missing.append({"kind":"missing_connection_intent","oldConnection":old_connection});continue
            for operation in required:
                found=any((connection["partA"]==operation["partA"] and connection["partB"]==operation["partB"]
                           and operation["attachPointA"] in connection["attachPointsA"] and operation["attachPointB"] in connection["attachPointsB"])
                          or (connection["partB"]==operation["partA"] and connection["partA"]==operation["partB"]
                              and operation["attachPointA"] in connection["attachPointsB"] and operation["attachPointB"] in connection["attachPointsA"]) for connection in current["connections"])
                if not found:missing.append({"kind":"new_connection_not_read_back","operation":operation})
    if final:
        all_operations=planned+compile_operations(plan,"finalize",runtime["temporaryIds"])
        for operation in all_operations:
            if operation.get("kind")!="symmetry.link":continue
            ids=operation["partIds"];groups=[parts.get(str(i),{}).get("symmetryId",0) for i in ids]
            if not groups or not groups[0] or len(set(groups))!=1:missing.append({"kind":"new_symmetry_not_read_back","partIds":ids})
    return {"status":"fail" if missing else "pass","issues":missing}


def _material_state(plan,runtime,snapshot):
    parts=snapshot_parts(snapshot);intent=plan["materialIntent"];issues=[];checked=[];missing=[];comparisons=[]
    if not isinstance(intent,dict):return {"status":"unknown","reason":"material_intent_missing","checkedTemporaryIds":[],"issues":[]}
    targets=intent.get("byTemporaryId")
    if targets is None:targets={name:intent for name in runtime["temporaryIds"]}
    if not isinstance(targets,dict):return {"status":"fail","reason":"invalid_material_rules","checkedTemporaryIds":[],"issues":[]}
    for name in set(targets)-set(runtime["temporaryIds"]):issues.append({"temporaryId":name,"reason":"unknown_material_target"})
    semantics=plan.get("semanticMapping",{old:[name] for old,name in plan["partMapping"].items()})
    baseline=runtime["checkpointBaseline"]["baselineParts"]
    for name,target_id in runtime["temporaryIds"].items():
        if name not in targets:missing.append({"temporaryId":name,"reason":"material_rule_missing"});continue
        rule=targets[name]
        if isinstance(rule,int) and not isinstance(rule,bool):rule={"materialId":rule}
        if not isinstance(rule,dict):issues.append({"temporaryId":name,"reason":"invalid_material_rule"});continue
        part=parts.get(str(target_id));actual=part.get("materialIds") if part else None
        if not isinstance(actual,list) or not actual:missing.append({"temporaryId":name,"reason":"native_material_slots_unavailable"});continue
        expected=deepcopy(rule.get("materialIds"));sources=[]
        if "referencePartId" in rule:
            reference=baseline.get(str(rule["referencePartId"]));expected=deepcopy(reference.get("materialIds")) if reference else None;sources=[rule["referencePartId"]]
        if rule.get("preserve") is True:
            sources=sorted(int(old) for old,values in semantics.items() if name in values)
            values=[baseline.get(str(old),{}).get("materialIds") for old in sources]
            if not sources or any(not isinstance(value,list) or not value for value in values):
                missing.append({"temporaryId":name,"reason":"preserve_source_material_unavailable","sourcePartIds":sources});continue
            if any(value!=values[0] for value in values[1:]):
                missing.append({"temporaryId":name,"reason":"merged_material_sources_ambiguous","sourcePartIds":sources});continue
            if expected is not None and expected!=values[0]:
                issues.append({"temporaryId":name,"reason":"preserve_intent_conflict","claimed":expected,"sourceMaterials":values[0],"sourcePartIds":sources});continue
            expected=deepcopy(values[0])
        if expected is not None:
            if not isinstance(expected,list) or len(expected)!=len(actual):issues.append({"temporaryId":name,"reason":"material_slot_count_mismatch","actual":actual,"expected":expected});continue
        if "materialId" in rule:
            material=rule["materialId"];slots=rule.get("slots",list(range(len(actual))))
            if isinstance(material,bool) or not isinstance(material,int) or not isinstance(slots,list) or not slots or any(isinstance(slot,bool) or not isinstance(slot,int) or slot<0 or slot>=len(actual) for slot in slots):
                issues.append({"temporaryId":name,"reason":"invalid_material_slot_rule"});continue
            if expected is None:
                if set(slots)!=set(range(len(actual))):missing.append({"temporaryId":name,"reason":"uncovered_material_slots","slots":sorted(set(range(len(actual)))-set(slots))});continue
                expected=[material]*len(actual)
            else:
                if rule.get("preserve") is True and any(expected[slot]!=material for slot in slots):
                    issues.append({"temporaryId":name,"reason":"preserve_intent_conflict","sourceMaterials":expected,"claimedMaterialId":material});continue
                for slot in slots:expected[slot]=material
        if expected is None:missing.append({"temporaryId":name,"reason":"material_expectation_missing"});continue
        checked.append(name);comparisons.append({"temporaryId":name,"partId":target_id,"actual":actual,"expected":expected,"sourcePartIds":sources})
        if actual!=expected:issues.append({"temporaryId":name,"actual":actual,"expected":expected})
    return {"status":"fail" if issues else "unknown" if missing or set(checked)!=set(runtime["temporaryIds"]) else "pass",
            "checkedTemporaryIds":sorted(checked),"missing":missing,"issues":issues,"comparisons":comparisons,"meaning":"Every candidate material slot is checked against explicit intent or actual frozen source materials; geometry boolean claims do not substitute for this readback."}


def _batches(plan,path,runtime,live,stage,operations):
    """Stable chunks resume individually. Only typed top-level targets cross batch boundaries."""
    size=plan.get("batchSize",80)
    if isinstance(size,bool) or not isinstance(size,int) or not 1<=size<=100:
        raise ReferenceError("invalid_plan","Native batch size must be 1..100 operations")
    for index in range(0,len(operations),size):
        marker=stage+"."+str(index//size).zfill(3)
        if marker in runtime["completedStages"]:continue
        chunk=deepcopy(operations[index:index+size])
        if stage=="create":
            # A temp target created in an earlier chunk must become the actual receipt ID.
            # A target created in this same chunk remains a native batch-local reference.
            local_names={op["temporaryId"] for op in chunk if op.get("kind")=="part.add"}
            available={key:value for key,value in runtime["temporaryIds"].items() if key not in local_names}
            partial={**plan,"createOperations":chunk,"referencePaths":[],"partMapping":{}}
            chunk=compile_operations(partial,"create",available)
        _mutate(live,path,runtime,"batch.apply",{"operations":chunk},marker,plan)
    runtime["completedStages"].append(stage)
    _record(path,"stage_completed",runtime,stage=stage,batchCount=(len(operations)+size-1)//size)


def run(plan,journal_path,payload=None,context=None):
    validate(plan);payload=payload or {};live=_live(context)
    if plan.get("mode")=="reshape":return _run_reshape(plan,journal_path,payload,context,live)
    journal=run_journal.status(journal_path);entries=journal["entries"]
    if entries and entries[0].get("planHash")!=plan["contentHash"]:
        raise ReferenceError("plan_changed","Journal belongs to a different immutable plan")
    if journal["pendingWrites"]:
        raise ReferenceError("result_unknown","Journal has an unresolved write. Use structure reconcile before continuing",pendingWrites=journal["pendingWrites"])
    runtime=_state(entries)
    if runtime and runtime["state"]=="finalized":
        loop_result=None
        if plan.get("loopJournalPath"):
            current=_snapshot(live);_guard(runtime,current);loop_result=_loop_review(plan,payload,current,context,runtime)
        return {"state":"finalized","runtime":runtime,"journalPath":str(journal_path),"loopReview":loop_result,"saved":False}
    if runtime and runtime["state"]=="reconcileRequired":raise ReferenceError("reconcile_required","Inspect and reconcile recorded state before continuing")
    if runtime and runtime["state"] in ("failed","restored"):
        raise ReferenceError("new_plan_required","Terminal interrupted plans require a new reviewed plan before another execution",state=runtime["state"])
    if runtime is None:
        current=_snapshot(live)
        report=changes(plan["binding"],current,plan["guardPartIds"])
        if report["status"]!="compatible":raise ReferenceError("state_changed","Plan baseline changed",changeReport=report)
        runtime={"state":"preflighted","planId":plan["planId"],"oldPartIds":plan["oldPartIds"],"guardPartIds":plan["guardPartIds"],
                 "binding":bind(current,plan["guardPartIds"]),"temporaryIds":{},"completedStages":[],"pendingStage":None,"checkpoint":None}
        runtime["checkpointBaseline"]={"identity":identity(current),"baselineParts":snapshot_parts(current),"contextState":snapshot_context(current)}
        runtime["lockedParts"]={str(i):snapshot_parts(current)[str(i)] for i in plan["lockedPartIds"]}
        runtime["restoreOwnedPartIds"]=_restore_owned_ids(plan)
        _record(journal_path,"plan_started",runtime,planHash=plan["contentHash"])
    if "checkpoint" not in runtime["completedStages"]:
        checkpoint=_mutate(live,journal_path,runtime,"craft.checkpoint.create",{"name":"reference-"+plan["planId"]},"checkpoint",plan)
        runtime["checkpoint"]={"id":checkpoint.get("id"),"craftSessionId":runtime["binding"]["identity"]["craftSessionId"]}
        _record(journal_path,"checkpoint_recorded",runtime)
    if "create" not in runtime["completedStages"]:
        _batches(plan,journal_path,runtime,live,"create",plan["createOperations"])
        required={operation["temporaryId"] for operation in plan["createOperations"] if operation.get("kind")=="part.add"}
        if not required<=set(runtime["temporaryIds"]):
            runtime["state"]="reconcileRequired";_record(journal_path,"mapping_incomplete",runtime)
            raise ReferenceError("mapping_incomplete","Creation receipt did not provide all real IDs; old parts have not been deleted")
    if "migration" not in runtime["completedStages"]:
        operations=compile_operations(plan,"migration",runtime["temporaryIds"])
        _batches(plan,journal_path,runtime,live,"migration",operations)
    if "geometry" not in runtime["completedStages"]:
        snapshot=_snapshot(live);_guard(runtime,snapshot)
        dependencies=_dependency_state(plan,runtime,snapshot)
        if dependencies["status"]!="pass":
            _record(journal_path,"dependency_validation_failed",runtime,dependencyReport=dependencies)
            raise ReferenceError("dependency_migration_incomplete","Readback still contains old references or missing new connections; old parts retained",dependencyReport=dependencies)
        material=_material_state(plan,runtime,snapshot)
        if material["status"]=="fail":
            _record(journal_path,"material_validation_failed",runtime,materialReport=material)
            raise ReferenceError("material_intent_mismatch","New parts do not match material intent; old parts retained",materialReport=material)
        if material["status"]!="pass":
            runtime["state"]="applying";_record(journal_path,"material_evidence_pending",runtime,materialReport=material)
            return {"state":"applying","stopReason":"material_evidence_required","materialReport":material,"runtime":runtime,"journalPath":str(journal_path)}
        quality=_quality(plan,runtime,snapshot,payload,context,"geometry")
        if quality["status"]!="pass":
            runtime["state"]="applying";_record(journal_path,"geometry_pending",runtime,quality=quality)
            return {"state":"applying","stopReason":"geometry_evidence_required" if quality["status"]=="unknown" else "geometry_failed","quality":quality,"runtime":runtime,"journalPath":str(journal_path)}
        runtime["state"]="geometryValidated";runtime["completedStages"].append("geometry");_record(journal_path,"geometry_validated",runtime,quality=quality)
    if "delete" not in runtime["completedStages"]:
        _batches(plan,journal_path,runtime,live,"delete",[{"kind":"part.delete","partId":i,"symmetric":False,"assembly":False} for i in plan["oldPartIds"]])
    if "finalize" not in runtime["completedStages"]:
        operations=compile_operations(plan,"finalize",runtime["temporaryIds"])
        _batches(plan,journal_path,runtime,live,"finalize",operations)
    snapshot=_snapshot(live);_guard(runtime,snapshot)
    quality=_quality(plan,runtime,snapshot,payload,context,"final")
    runtime["state"]="finalized" if quality["status"]=="pass" else "geometryValidated"
    _record(journal_path,"finalization_checked",runtime,quality=quality)
    loop_result=_loop_review(plan,payload,snapshot,context,runtime)
    return {"state":runtime["state"],"quality":quality,"runtime":runtime,"journalPath":str(journal_path),"saved":False,"loopReview":loop_result,
            "meaning":"Native save/recenter and post-save rebinding are a separate required step."}


def _reshape_material(plan,runtime,snapshot):
    intent=plan["materialIntent"];parts=snapshot_parts(snapshot);issues=[];checked=[]
    for target in plan["partIds"]:
        rule=intent.get("byPartId",{}).get(str(target),intent)
        actual=parts.get(str(target),{}).get("materialIds",[])
        before=runtime["checkpointBaseline"]["baselineParts"][str(target)].get("materialIds",[])
        expected=rule.get("materialIds")
        if rule.get("preserve") is True:expected=before
        if expected is not None:
            checked.append(target)
            if actual!=expected:issues.append({"partId":target,"actual":actual,"expected":expected})
        elif "materialId" in rule:
            slots=rule.get("slots",list(range(len(actual))));checked.append(target)
            if not actual or any(isinstance(slot,bool) or not isinstance(slot,int) or slot<0 or slot>=len(actual) or actual[slot]!=rule["materialId"] for slot in slots):
                issues.append({"partId":target,"actual":actual,"rule":rule})
    return {"status":"fail" if issues else "pass" if set(checked)==set(plan["partIds"]) else "unknown","issues":issues,"checkedPartIds":checked}


def _reshape_quality(plan,runtime,snapshot,payload,context,phase):
    callback=(context or {}).get("validateGeometry" if phase=="geometry" else "validateFinal")
    evidence=callback(plan,{str(i):i for i in plan["partIds"]},snapshot) if callable(callback) else payload.get("geometryEvidence" if phase=="geometry" else "finalEvidence")
    if not isinstance(evidence,dict) or evidence.get("identity")!=identity(snapshot):
        return {"status":"unknown","reason":"fresh_"+phase+"_evidence_required"}
    if not set(runtime["reviewPartIds"])<=set(evidence.get("partIds",[])):
        return {"status":"unknown","reason":"subject_or_impact_coverage_missing","requiredPartIds":runtime["reviewPartIds"]}
    material=_reshape_material(plan,runtime,snapshot)
    if material["status"]!="pass":return {"status":material["status"],"reason":"material_intent_unverified","materialReport":material}
    result=evaluate(plan["qualityProfile"],evidence)
    required=("subjectValid","impactValid","lockedPartsPreserved")
    missing=[key for key in required if evidence.get("checks",{}).get(key) is not True]
    if missing:result.update(status="fail" if any(evidence.get("checks",{}).get(k) is False for k in missing) else "unknown",
                             reason="in_place_checks_missing_or_failed",missingChecks=missing)
    return result


def _run_reshape(plan,path,payload,context,live):
    """Reuses the same mutation journal and reconciliation rules as replacement."""
    journal=run_journal.status(path);entries=journal["entries"]
    if entries and entries[0].get("planHash")!=plan["contentHash"]:raise ReferenceError("plan_changed","Journal belongs to a different immutable plan")
    if journal["pendingWrites"]:raise ReferenceError("result_unknown","Resolve pending operation without replay before continuing",pendingWrites=journal["pendingWrites"])
    runtime=_state(entries)
    if runtime and runtime["state"]=="finalized":
        current=_snapshot(live);_guard(runtime,current)
        loop_result=_loop_review(plan,payload,current,context,runtime)
        visual=payload.get("visualEvidence",{})
        if visual.get("identity")==identity(current) and visual.get("reviewed") is True and visual.get("imagePaths") and not runtime["acceptance"]["visualReviewed"]:
            runtime["acceptance"]["visualReviewed"]=True;_record(path,"visual_review_recorded",runtime,visualEvidence=visual)
        return {"state":"finalized","runtime":runtime,"journalPath":str(path),"saved":False,"replayed":False,"loopReview":loop_result}
    if runtime and runtime["state"]=="reconcileRequired":raise ReferenceError("reconcile_required","Resolve recorded state before continuing")
    if runtime and runtime["state"] in ("failed","restored"):raise ReferenceError("new_plan_required","Terminal plans require a new reviewed plan")
    if runtime is None:
        current=_snapshot(live);report=changes(plan["binding"],current,plan["guardPartIds"])
        if report["status"]!="compatible":raise ReferenceError("state_changed","Plan baseline changed",changeReport=report)
        permitted=set(plan["partIds"])|set(plan.get("expectedChanges",{}).get("allowedChangedPartIds",[]))
        if not permitted<=set(plan["guardPartIds"]) or permitted&set(plan["lockedPartIds"]):
            raise ReferenceError("invalid_scope","Expected changed parts must be guarded and cannot be locked")
        runtime={"state":"preflighted","mode":"reshape","planId":plan["planId"],"oldPartIds":[],"newPartIds":[],
                 "guardPartIds":plan["guardPartIds"],"reviewPartIds":plan["guardPartIds"],"permittedChangedPartIds":sorted(permitted),
                 "binding":bind(current,plan["guardPartIds"]),"temporaryIds":{},"completedStages":[],"pendingStage":None,"checkpoint":None,
                 "checkpointBaseline":{"identity":identity(current),"baselineParts":snapshot_parts(current),"contextState":snapshot_context(current)},
                 "lockedParts":{str(i):snapshot_parts(current)[str(i)] for i in plan["lockedPartIds"]},
                 "restoreOwnedPartIds":sorted(permitted),
                 "acceptance":{"writesSucceeded":False,"geometryPassed":False,"finalGeometryPassed":False,"visualReviewed":False,
                               "nativeSaved":False,"userAestheticApproval":False}}
        _record(path,"plan_started",runtime,planHash=plan["contentHash"])
    if "checkpoint" not in runtime["completedStages"]:
        receipt=_mutate(live,path,runtime,"craft.checkpoint.create",{"name":"reshape-"+plan["planId"]},"checkpoint",plan)
        runtime["checkpoint"]={"id":receipt.get("id"),"craftSessionId":runtime["binding"]["identity"]["craftSessionId"]}
        _record(path,"checkpoint_recorded",runtime)
    if "edit" not in runtime["completedStages"]:
        _batches(plan,path,runtime,live,"edit",plan["editOperations"])
    runtime["acceptance"]["writesSucceeded"]=True
    current=_snapshot(live);_guard(runtime,current)
    if "geometry" not in runtime["completedStages"]:
        quality=_reshape_quality(plan,runtime,current,payload,context,"geometry")
        if quality["status"]!="pass":
            runtime["state"]="applying";_record(path,"geometry_pending",runtime,quality=quality)
            return {"state":"applying","stopReason":"geometry_evidence_required" if quality["status"]=="unknown" else "geometry_failed",
                    "quality":quality,"runtime":runtime,"saved":False,"journalPath":str(path)}
        runtime["completedStages"].append("geometry");runtime["acceptance"]["geometryPassed"]=True
        runtime["state"]="geometryValidated";_record(path,"geometry_validated",runtime,quality=quality)
    quality=_reshape_quality(plan,runtime,current,payload,context,"final")
    runtime["acceptance"]["finalGeometryPassed"]=quality["status"]=="pass"
    # A path returned by a capture is deliberately not a visual review receipt.
    visual=payload.get("visualEvidence",{})
    if visual.get("identity")==identity(current) and visual.get("reviewed") is True and visual.get("imagePaths"):
        runtime["acceptance"]["visualReviewed"]=True
    runtime["state"]="finalized" if quality["status"]=="pass" else "geometryValidated"
    _record(path,"finalization_checked",runtime,quality=quality)
    loop_result=_loop_review(plan,payload,current,context,runtime)
    return {"state":runtime["state"],"quality":quality,"runtime":runtime,"journalPath":str(path),"saved":False,"loopReview":loop_result,
            "meaning":"In-place writes, geometry, visual review, native save and user aesthetic approval are separate records."}


def reconcile(plan,journal_path,payload=None,context=None):
    """Resolve a known operation by read-only query. Never issues the pending mutation."""
    validate(plan);live=_live(context);payload=payload or {};status=run_journal.status(journal_path)
    runtime=_state(status["entries"])
    if runtime is None:raise ReferenceError("journal_empty","No execution exists to reconcile")
    pending=status["pendingWrites"]
    if not pending:
        snapshot=_snapshot(live);report=changes(runtime["binding"],snapshot,runtime["guardPartIds"])
        return {"state":runtime["state"],"changeReport":report,"automaticResume":False,"meaning":"Manual changes need a new reviewed plan; this action does not overwrite them."}
    prepared=pending[-1];unknown=[e for e in status["entries"] if e.get("requestId")==prepared["requestId"] and e["event"]=="write_unknown"]
    recorded_id=unknown[-1].get("operationId") if unknown else None
    operation_id=payload.get("operationId") or recorded_id
    if recorded_id and operation_id!=recorded_id:
        raise ReferenceError("operation_mismatch","Only the originally recorded operation may resolve this pending request")
    if not operation_id:return {"state":"reconcileRequired","requestId":prepared["requestId"],"reason":"operation_id_required","replayed":False}
    if not recorded_id:
        return {"state":"reconcileRequired","requestId":prepared["requestId"],"operationId":operation_id,"reason":"request_to_operation_attribution_unverified","replayed":False}
    job=unwrap(live("operation.status",{"id":operation_id}))
    if not isinstance(job,dict) or job.get("operationId",operation_id)!=operation_id:
        raise ReferenceError("operation_mismatch","Status returned another operation")
    if job.get("state") in ("queued","running"):return {"state":"reconcileRequired","operation":job,"replayed":False}
    if job.get("state")=="result_expired":return {"state":"reconcileRequired","reason":"operation_result_expired","operationId":operation_id,"replayed":False}
    receipt=job.get("result")
    if job.get("state") in ("failed","cancelled"):
        runtime["state"]="failed";runtime["pendingStage"]=None
        _record(journal_path,"write_failed",runtime,requestId=prepared["requestId"],operationId=operation_id,operation=job,nextAction="new_plan_required")
        return {"state":"failed","replayed":False,"restorationRequired":True}
    if job.get("state")!="succeeded" or not receipt:
        return {"state":"reconcileRequired","reason":"operation_terminal_result_unverified","operation":job,"replayed":False}
    receipt=unwrap(receipt);snapshot=_snapshot(live)
    receipt_identity=identity(snapshot) if prepared["command"]=="craft.checkpoint.create" else identity(receipt)
    if prepared["command"]=="craft.checkpoint.create" and any(receipt.get(key)!=receipt_identity.get(key) for key in ("craftSessionId","revision","fingerprint")):
        return {"state":"reconcileRequired","reason":"checkpoint_state_changed","replayed":False}
    if receipt_identity!=identity(snapshot):return {"state":"reconcileRequired","reason":"post_operation_state_changed","replayed":False}
    actual_parts=snapshot_parts(snapshot)
    if any(actual_parts.get(key)!=value for key,value in runtime.get("lockedParts",{}).items()):
        return {"state":"reconcileRequired","reason":"locked_scope_changed","replayed":False}
    if any(item.get("partId") in runtime["oldPartIds"] for item in receipt.get("reusedPartIds",[])):
        return {"state":"reconcileRequired","reason":"old_id_reused","replayed":False}
    if runtime.get("mode")=="reshape":
        prewrite=prepared.get("beforeBinding") or runtime["binding"]
        delta=changes(prewrite,snapshot,list(int(k) for k in prewrite["baselineParts"]))
        unexpected=set(delta["changedPartIds"])-set(runtime["permittedChangedPartIds"])
        if set(actual_parts)!=set(runtime["binding"]["baselineParts"]) or unexpected or delta["globalConflicts"] or delta["materialConflicts"] or delta["topologyConflicts"]:
            # Attribution is now known: close the pending write as a success,
            # but never execute its stage again or accept its undeclared delta.
            runtime["state"]="failed";runtime["completedStages"].append(runtime["pendingStage"]);runtime["pendingStage"]=None
            _record(journal_path,"write_completed",runtime,requestId=prepared["requestId"],operationId=operation_id,
                    receipt=receipt,reconciled=True,readbackAccepted=False,changeReport=delta,nextAction="new_plan_required")
            return {"state":"failed","reason":"unexpected_readback_changes","replayed":False,"newPlanRequired":True,"changeReport":delta}
    elif runtime.get("pendingStage")!="restore":
        try:_replacement_readback(plan,runtime,prepared.get("beforeBinding") or runtime["binding"],snapshot,prepared.get("payload",{}),receipt)
        except ReferenceError as error:
            runtime["state"]="failed";runtime["completedStages"].append(runtime["pendingStage"]);runtime["pendingStage"]=None
            _record(journal_path,"write_completed",runtime,requestId=prepared["requestId"],operationId=operation_id,receipt=receipt,reconciled=True,readbackAccepted=False,changeReport=error.details,nextAction="new_plan_required")
            return {"state":"failed","reason":"unexpected_readback_changes","replayed":False,"newPlanRequired":True,"changeReport":error.details}
    runtime["temporaryIds"].update(receipt.get("temporaryIds",{}));runtime["guardPartIds"]=sorted((set(runtime["guardPartIds"])|set(runtime["temporaryIds"].values()))&set(int(k) for k in snapshot_parts(snapshot)))
    runtime["newPartIds"]=sorted(set(runtime.get("newPartIds",[]))|set(runtime["temporaryIds"].values())|{i for change in receipt.get("actualChanges",[]) for i in (change.get("partIds",[]) if change.get("kind")=="part.add" else change.get("createdPartIds",[]))})
    runtime["guardPartIds"]=sorted(set(runtime["guardPartIds"])|set(runtime["newPartIds"]))
    runtime["binding"]=bind(snapshot,runtime["guardPartIds"]);stage=runtime["pendingStage"]
    if stage=="checkpoint":runtime["checkpoint"]={"id":receipt.get("id"),"craftSessionId":identity(snapshot)["craftSessionId"]}
    runtime["completedStages"].append(stage);runtime["pendingStage"]=None;runtime["state"]="applying"
    _record(journal_path,"write_completed",runtime,requestId=prepared["requestId"],operationId=operation_id,receipt=receipt,reconciled=True)
    return {"state":"applying","resolvedStage":stage,"replayed":False,"runtime":runtime}


def _restore_owned_ids(plan):
    ids=set(plan.get("oldPartIds",[]))|set(plan.get("partIds",[]))
    for stage in ("migrationOperations","finalizeOperations"):
        for op in plan.get(stage,[]):
            ids.update(op[field] for field in ("partId","partA","partB","sourcePartId","targetPartId") if isinstance(op.get(field),int))
            ids.update(i for i in op.get("partIds",[]) if isinstance(i,int))
    return sorted(ids)


def _restore_external_guard(runtime,snapshot):
    """Latest bindings retain player edits, but cannot authorize undoing them.

    Compare external parts and shared state to the immutable checkpoint, not to
    a later baseline that has intentionally absorbed unrelated player changes.
    """
    before=runtime["checkpointBaseline"];baseline=before["baselineParts"];current=snapshot_parts(snapshot)
    owned=set(runtime.get("restoreOwnedPartIds",runtime.get("oldPartIds",[])))|set(runtime.get("newPartIds",[]))|set(runtime.get("temporaryIds",{}).values())
    external=[int(key) for key in set(baseline)|set(current) if int(key) not in owned and baseline.get(key)!=current.get(key)]
    old_context=before.get("contextState",{});new_context=snapshot_context(snapshot)
    old_edges={canonical_connection_key(c):c for c in old_context.get("connections",[])}
    new_edges={canonical_connection_key(c):c for c in new_context["connections"]}
    external_edges=[key for key in set(old_edges)^set(new_edges) if any(not {c["partA"],c["partB"]}&owned for c in (old_edges.get(key),new_edges.get(key)) if c)]
    globals_changed=[key for key in ("materials","variables","authoredState") if old_context.get(key)!=new_context.get(key)]
    if external or external_edges or globals_changed:
        raise ReferenceError("restore_would_overwrite_user_changes","Whole-craft checkpoint restore would overwrite changes retained after checkpoint",
                             checkpointIdentity=before["identity"],externalPartIds=sorted(external),externalConnectionKeys=sorted(external_edges),sharedStateChanges=globals_changed)


def restore(plan,journal_path,payload=None,context=None):
    """Same-session checkpoint restore, only when no unaccounted user changes exist."""
    validate(plan);live=_live(context);status=run_journal.status(journal_path);runtime=_state(status["entries"])
    if not runtime or not runtime.get("checkpoint"):raise ReferenceError("checkpoint_unavailable","No verified same-session checkpoint exists")
    if status["pendingWrites"]:raise ReferenceError("result_unknown","Resolve pending operation before any restore")
    snapshot=_snapshot(live);report=changes(runtime["binding"],snapshot,list(int(key) for key in runtime["binding"].get("baselineParts",{})))
    if report["status"]!="compatible" or report.get("unrelated") or report.get("unrelatedConnectionChanges") or report.get("unrelatedMaterialChanges"):
        raise ReferenceError("restore_would_overwrite_user_changes","Whole-craft rollback would overwrite unaccounted current changes",changeReport=report)
    if identity(snapshot)["craftSessionId"]!=runtime["checkpoint"]["craftSessionId"]:
        raise ReferenceError("checkpoint_expired","Native checkpoints do not survive changing craft or restarting")
    runtime.setdefault("restoreOwnedPartIds",_restore_owned_ids(plan))
    _restore_external_guard(runtime,snapshot)
    _mutate(live,journal_path,runtime,"craft.rollback",{"checkpointId":runtime["checkpoint"]["id"]},"restore",plan)
    restored=_snapshot(live);expected=runtime["checkpointBaseline"]["baselineParts"]
    if snapshot_parts(restored)!=expected or snapshot_context(restored)!=runtime["checkpointBaseline"].get("contextState",snapshot_context(restored)):
        runtime["state"]="reconcileRequired";_record(journal_path,"restore_mismatch",runtime)
        raise ReferenceError("restore_mismatch","Checkpoint returned but exact part-state readback differs from original baseline")
    runtime["state"]="restored";runtime["binding"]=bind(restored);_record(journal_path,"restored",runtime)
    return {"state":"restored","identity":identity(restored),"saved":False}
