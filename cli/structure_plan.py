"""Immutable, reviewable replacement plans, with explicitly typed nested references."""
from copy import deepcopy
import uuid
from reference_storage import ReferenceError, digest, utc_now
from reference_binding import bind, snapshot_parts, snapshot_context, identity, canonical_connection_key
from structure_model import part_ids

KIND="sp2build.structurePlan"
REFERENCE_KEYS={"customPartIds","targetPartIds","hostPartId","parentPartId","targetPartId","cuttingPartIds"}


def _dependencies(parts,old_ids):
    result=[]
    for key,part in parts.items():
        if int(key) in old_ids:continue
        for node in _walk_nodes(part.get("serializedState")):
            for attr,value in node.get("attributes",{}).items():
                if attr in REFERENCE_KEYS or (node.get("tag")=="PartTargeting.State" and attr=="partIds" and node.get("attributes",{}).get("targetMode")=="Custom"):
                    try: ids=[int(i.strip()) for i in value.split(",") if i.strip()]
                    except (AttributeError,ValueError):
                        result.append({"partId":int(key),"attribute":attr,"status":"unparsed_reference","value":value});continue
                    hits=sorted(old_ids.intersection(ids))
                    if hits:result.append({"partId":int(key),"attribute":attr,"oldPartIds":hits,"status":"migration_required"})
    return result


def _walk_nodes(node):
    if not node:return
    yield node
    for child in node.get("children",[]):yield from _walk_nodes(child)


def inspect_impact(snapshot,old_part_ids):
    parts=snapshot_parts(snapshot);old=set(part_ids(old_part_ids,"oldPartIds"));context=snapshot_context(snapshot)
    if any(str(i) not in parts for i in old):raise ReferenceError("part_not_found","Impact inspection targets missing parts")
    internal=[];external=[]
    for connection in context["connections"]:
        a,b=connection["partA"],connection["partB"]
        if a in old or b in old:
            item={**connection,"key":canonical_connection_key(connection)}
            (internal if a in old and b in old else external).append(item)
    group_ids={parts[str(i)].get("symmetryId",0) for i in old}-{0}
    groups=[{"groupId":group,"oldPartIds":[i for i in sorted(old) if parts[str(i)].get("symmetryId")==group],
             "outsidePartIds":[int(key) for key,part in parts.items() if part.get("symmetryId")==group and int(key) not in old]} for group in sorted(group_ids)]
    nested=_dependencies(parts,old);implicit=[];ownership=[]
    ownership_modifiers={"ControlSurfacePart.State","ProceduralMissileSubPart.State","Wheel.State","GearLeg.State","ProceduralLandingGear.State"}
    for key,part in parts.items():
        for node in _walk_nodes(part.get("serializedState")):
            tag=node.get("tag","")
            if tag=="PartTargeting.State" and node.get("attributes",{}).get("targetMode")!="Custom" and int(key) not in old:
                implicit.append({"partId":int(key),"targetMode":node["attributes"].get("targetMode"),"status":"geometric_targeting_requires_check"})
            if tag in ownership_modifiers and (int(key) in old or any(i in old for i in part.get("connectedPartIds",[]))):
                ownership.append({"partId":int(key),"modifier":tag,"status":"native_ownership_requires_check"})
    material_ids=sorted({material for i in old for material in parts[str(i)].get("materialIds",[])})
    material_users={str(material):[int(key) for key,part in parts.items() if material in part.get("materialIds",[]) and int(key) not in old] for material in material_ids}
    return {"identity":identity(snapshot),"oldPartIds":sorted(old),"externalConnections":external,"internalConnections":internal,
            "symmetryGroups":groups,"nestedReferences":nested,"implicitTargeting":implicit,"nativeOwnership":ownership,
            "materialIds":material_ids,"outsideMaterialUsers":material_users,"paletteObservable":context["materials"] is not None,
            "status":"dependencies_present" if external or internal or groups or nested or implicit or ownership else "no_declared_dependencies",
            "limitations":["Implicit geometric targeting and native animated ownership require same-revision live evidence.","Reference attributes are parsed from an explicit allowlist; unknown modifiers remain outside this declared coverage."]}


def _removed(expected,name):
    value=expected.get(name,[])
    if not isinstance(value,list) or any(not isinstance(item,dict) or not item.get("key") or not item.get("reason") for item in value):
        raise ReferenceError("invalid_plan","Dependency removals require explicit key and reason",field=name)
    return {str(item["key"]) for item in value}


def _topology_preflight(impact,mapping,migrations,final,expected):
    operations=migrations+final;required=[]
    for category,allow_name in (("externalConnections","removeExternalConnections"),("internalConnections","removeInternalConnections")):
        removed=_removed(expected,allow_name)
        valid_keys={connection["key"] for connection in impact[category]}
        if removed-valid_keys:raise ReferenceError("invalid_plan","Removal refers to an unknown original connection",keys=sorted(removed-valid_keys))
        for connection in impact[category]:
            a=mapping.get(str(connection["partA"]),connection["partA"]);b=mapping.get(str(connection["partB"]),connection["partB"])
            if a==b or connection["key"] in removed:continue
            candidates=[op for op in migrations if op.get("kind")=="connection.connect" and ((op.get("partA"),op.get("partB")) in ((a,b),(b,a)))]
            if not candidates:required.append({"connection":connection,"requiredNewEndpoints":[a,b]})
    if required:raise ReferenceError("dependency_uncovered","Every old connection needs an explicit new connection or reviewed removal",connections=required)
    removed_groups=_removed(expected,"removeSymmetryGroups")
    valid_group_keys={str(group["groupId"]) for group in impact["symmetryGroups"]}
    if removed_groups-valid_group_keys:raise ReferenceError("invalid_plan","Removal refers to an unknown original symmetry group",keys=sorted(removed_groups-valid_group_keys))
    for group in impact["symmetryGroups"]:
        old_group=group["oldPartIds"]+group["outsidePartIds"]
        if not any(op.get("kind")=="symmetry.unlink" and op.get("partId") in old_group for op in migrations):
            raise ReferenceError("dependency_uncovered","Old symmetry group must be explicitly unlinked before deletion",group=group)
        new_members={mapping.get(str(i),i) for i in old_group}
        if str(group["groupId"]) not in removed_groups and not any(op.get("kind")=="symmetry.link" and new_members<=set(op.get("partIds",[])) for op in operations):
            raise ReferenceError("dependency_uncovered","Symmetry needs an explicit new link or reviewed removal",group=group)


def create(payload):
    if payload.get("mode") == "reshape":return create_reshape(payload)
    snapshot=payload.get("snapshot")
    if not snapshot:raise ReferenceError("invalid_input","Plan requires a current snapshot (includeXml:true)")
    from reference_binding import unwrap
    if not unwrap(snapshot).get("xml"):raise ReferenceError("snapshot_incomplete","Replacement planning requires includeXml:true for dependency inspection")
    ident=identity(snapshot);parts=snapshot_parts(snapshot)
    old=set(part_ids(payload.get("oldPartIds",[]),"oldPartIds"))
    if not old:raise ReferenceError("invalid_scope","Replacement requires explicit nonempty oldPartIds")
    locked=set(part_ids(payload.get("lockedPartIds",[]),"lockedPartIds"))
    if old & locked:raise ReferenceError("locked_scope","Replacement intersects locked parts",partIds=sorted(old&locked))
    if not all(str(i) in parts for i in old):raise ReferenceError("part_not_found","Old parts missing from snapshot")
    creates=deepcopy(payload.get("createOperations",[]));migrations=deepcopy(payload.get("migrationOperations",[]))
    final=deepcopy(payload.get("finalizeOperations",[]));new_names=[]
    for operation in creates:
        if operation.get("kind")=="part.add":
            name=operation.get("temporaryId")
            if not name or name in new_names:raise ReferenceError("invalid_plan","Each new part needs a unique temporaryId")
            new_names.append(name)
        elif operation.get("kind") not in ("shape.update","properties.set","part.update","appearance.set","transform.apply"):
            raise ReferenceError("invalid_plan","Unsupported operation in creation stage",kind=operation.get("kind"))
        else:
            targets=operation.get("partIds",[operation.get("partId")])
            if not targets or any(target not in new_names for target in targets):
                raise ReferenceError("invalid_plan","Creation stage may configure only previously declared new temporary parts")
    pure_retirement=isinstance(payload.get("semanticMapping"),dict) and bool(payload["semanticMapping"]) and all(values==[] for values in payload["semanticMapping"].values())
    if not new_names and not pure_retirement:raise ReferenceError("invalid_plan","Creation stage must create parts unless every source is explicitly retired")
    for operation in migrations+final:
        if operation.get("kind") in ("part.add","part.delete"):
            raise ReferenceError("invalid_plan","Migration/finalization may not create or delete parts")
        targets=[operation.get(field) for field in ("partId","partA","partB","sourcePartId","targetPartId")]+operation.get("partIds",[])
        if any(target in locked for target in targets if isinstance(target,int)):
            raise ReferenceError("locked_scope","Migration/finalization targets a locked part")
        if operation.get("kind")=="appearance.set" and operation.get("mode")=="shared":
            raise ReferenceError("invalid_scope","Shared-palette mutation needs a separate reviewed whole-craft plan")
    mapping={str(k):v for k,v in payload.get("partMapping",{}).items()}
    semantic=deepcopy(payload.get("semanticMapping",{key:[value] for key,value in mapping.items()}))
    if not isinstance(semantic,dict) or set(semantic)!=set(str(i) for i in old) or any(not isinstance(values,list) or any(not isinstance(value,str) or value not in new_names for value in values) or len(set(values))!=len(values) for values in semantic.values()):
        raise ReferenceError("invalid_plan","semanticMapping must map every old ID to explicit new temporary IDs or an empty retirement list")
    if set(mapping)!={key for key,values in semantic.items() if values} or any(value not in semantic[key] for key,value in mapping.items()):
        raise ReferenceError("invalid_plan","partMapping requires one declared connection anchor for each non-retired source")
    ownership=deepcopy(payload.get("ownershipMapping",[]));protected_mapping=deepcopy(payload.get("protectedFieldMapping",[]))
    if not isinstance(ownership,list) or any(not isinstance(row,dict) for row in ownership) or not isinstance(protected_mapping,list) or any(not isinstance(row,dict) for row in protected_mapping):raise ReferenceError("invalid_plan","Ownership and protected field mappings must be lists of records")
    if "semanticMapping" in payload:
        def declared_owner(sources,targets):
            found=[row for row in ownership if isinstance(row,dict) and set(row.get("sourcePartIds",[]))==set(sources) and set(row.get("targetPartIds",[]))==set(targets) and row.get("reason") and row.get("structureId")==payload.get("structureId") and row.get("structureId")]
            if len(found)!=1:raise ReferenceError("invalid_plan","Split/retired/merged ownership requires explicit structure-bound intent",sourcePartIds=sources,targetPartIds=targets)
            return found[0]
        supports=set()
        for key,values in semantic.items():
            if len(values)!=1:
                row=declared_owner([int(key)],values)
                if not values:
                    ids=row.get("supportPartIds",[])
                    if not isinstance(ids,list) or not ids or any((isinstance(i,bool) or not isinstance(i,(int,str)) or isinstance(i,int) and (str(i) not in parts or i in old) or isinstance(i,str) and i not in new_names) for i in ids):
                        raise ReferenceError("invalid_plan","Retirement needs existing surviving or declared new region support")
                    supports.update(ids)
        for target in new_names:
            sources=[int(key) for key,values in semantic.items() if target in values]
            if len(sources)>1:declared_owner(sources,[target])
        if set(new_names)-{name for values in semantic.values() for name in values}-{i for i in supports if isinstance(i,str)}:
            raise ReferenceError("invalid_plan","Every new part needs semantic ownership or an explicit retirement-support role")
    declared=deepcopy(payload.get("referencePaths",[]))
    for ref in declared:
        if (ref.get("stage","migration") not in ("migration","finalize") or ref.get("encoding") not in ("integer","array","csv")
            or isinstance(ref.get("operationIndex"),bool) or not isinstance(ref.get("operationIndex"),int) or ref["operationIndex"]<0
            or not isinstance(ref.get("path"),str) or not ref["path"].startswith("/")):
            raise ReferenceError("invalid_plan","Nested references require stage, operationIndex, JSON pointer and explicit encoding")
    touched=set(old)|locked|set(part_ids(payload.get("boundaryPartIds",[]),"boundaryPartIds"))
    impact=inspect_impact(snapshot,sorted(old));expected=payload.get("expectedChanges",{})
    retired={int(key) for key,values in semantic.items() if not values}
    for category,allow_name in (("externalConnections","removeExternalConnections"),("internalConnections","removeInternalConnections")):
        removed=_removed(expected,allow_name)
        if any((edge["partA"] in retired or edge["partB"] in retired) and edge["key"] not in removed for edge in impact[category]):
            raise ReferenceError("dependency_uncovered","Retired part connections require explicit reviewed removals")
    if any(set(group["oldPartIds"])&retired and str(group["groupId"]) not in _removed(expected,"removeSymmetryGroups") for group in impact["symmetryGroups"]):
        raise ReferenceError("dependency_uncovered","Retired symmetry membership requires explicit reviewed group removal")
    _topology_preflight(impact,mapping,migrations,final,expected)
    for connection in impact["externalConnections"]:touched.update((connection["partA"],connection["partB"]))
    for group in impact["symmetryGroups"]:touched.update(group["outsidePartIds"])
    for row in ownership:touched.update(i for i in row.get("supportPartIds",[]) if isinstance(i,int))
    for name,items in (("nativeDependencyEvidence",impact["nativeOwnership"]),("targetingEvidence",impact["implicitTargeting"])):
        evidence=payload.get(name)
        if items and (not isinstance(evidence,dict) or evidence.get("identity")!=ident or evidence.get("verified") is not True
                      or not set(item["partId"] for item in items)<=set(evidence.get("partIds",[]))):
            raise ReferenceError("dependency_evidence_required","Same-revision live ownership/targeting inspection is required before planning",evidenceField=name,parts=items)
        if evidence:
            for dependency in evidence.get("nativeDependencies",[]):
                touched.update((dependency["partId"],dependency["hostPartId"]))
    for operation in migrations+final:
        for field in ("partId","partA","partB","sourcePartId","targetPartId"):
            if isinstance(operation.get(field),int):touched.add(operation[field])
        for value in operation.get("partIds",[]):
            if isinstance(value,int):touched.add(value)
        if operation.get("kind")=="symmetry.create":
            raise ReferenceError("invalid_plan","Implicit mirrored creation is not supported in replacement stages; declare candidates explicitly")
    dependencies=_dependencies(parts,old)
    extra=set(part_ids(expected.get("allowedChangedPartIds",[]),"allowedChangedPartIds"))
    if not extra<=touched or extra&locked:
        raise ReferenceError("invalid_scope","Explicit callback allowance must stay within the guarded unlocked region")
    covered=set()
    for spec in declared:
        if spec.get("stage","migration")!="migration":continue
        try:operation=migrations[spec["operationIndex"]]
        except IndexError as exc:raise ReferenceError("invalid_reference_path","Reference operation index is outside stage") from exc
        field=spec["path"].split("/")[-1].replace("~1","/").replace("~0","~")
        if operation.get("kind")=="properties.set":covered.add((operation.get("partId"),field.split(".")[-1]))
    uncovered=[dep for dep in dependencies if (dep["partId"],dep["attribute"]) not in covered or dep["status"]=="unparsed_reference"]
    if uncovered:raise ReferenceError("dependency_uncovered","Nested references require explicit migration operations",dependencies=uncovered)
    if not payload.get("materialIntent"):
        raise ReferenceError("material_intent_required","Plan must declare material intent and its validation evidence")
    batch_size=payload.get("batchSize",4)
    if isinstance(batch_size,bool) or not isinstance(batch_size,int) or not 1<=batch_size<=100:
        raise ReferenceError("invalid_plan","batchSize must be 1..100 native operations")
    plan={"kind":KIND,"schemaVersion":1,"planId":str(uuid.uuid4()),"createdAt":utc_now(),"state":"planned",
          "batchSize":batch_size,
          "structureId":payload.get("structureId"),"craftIdentity":ident,"oldPartIds":sorted(old),"lockedPartIds":sorted(locked),
          "guardPartIds":sorted(touched),"binding":bind(snapshot,sorted(touched)),"createOperations":creates,
          "migrationOperations":migrations,"finalizeOperations":final,"referencePaths":declared,"partMapping":mapping,
          "semanticMapping":semantic,"ownershipMapping":ownership,"protectedFieldMapping":protected_mapping,
          "materialIntent":deepcopy(payload["materialIntent"]),"dependencies":dependencies,"impact":impact,
          "nativeDependencyEvidence":deepcopy(payload.get("nativeDependencyEvidence")),"targetingEvidence":deepcopy(payload.get("targetingEvidence")),
          "qualityProfile":deepcopy(payload.get("qualityProfile")),"expectedChanges":deepcopy(payload.get("expectedChanges",{})),
          "loopJournalPath":payload.get("loopJournalPath"),
          "limitations":["Cross-batch replacement is recoverable, not atomic.","Unlisted reference fields are not guessed.","Material properties require explicit readback evidence."]}
    if plan.get("loopJournalPath"):
        import build_loop
        loop=build_loop.dispatch("inspect",{"journalPath":plan["loopJournalPath"]})["loop"]
        frozen={};protection_checks=[]
        for goal in loop["goals"]:
            for field in goal.get("protectionBaseline",[]):
                key=str(field["partId"])
                if key not in semantic:continue
                declared=[row for row in protected_mapping if row.get("sourcePartId")==field["partId"] and row.get("sourcePath")==field["path"]]
                if len(semantic[key])!=1 and len(declared)!=1:
                    raise ReferenceError("protected_mapping_required","Plan must explicitly preserve protected fields before splitting or retiring a source",sourcePartId=field["partId"],path=field["path"])
                if len(declared)>1:raise ReferenceError("protected_mapping_conflict","Duplicate protected-field mapping")
                targets=declared[0].get("targets") if declared else [{"partId":semantic[key][0],"path":field["path"]}]
                allowed=semantic[key] or next((row.get("supportPartIds",[]) for row in ownership if row.get("sourcePartIds")==[field["partId"]] and row.get("targetPartIds")==[]),[])
                if not isinstance(targets,list) or not targets:raise ReferenceError("protected_mapping_required","Protected obligation must have a surviving field")
                for target in targets:
                    if not isinstance(target,dict) or target.get("partId") not in allowed or not isinstance(target.get("path"),str) or not target["path"].startswith("/"):
                        raise ReferenceError("protected_mapping_conflict","Protection transfer leaves the explicit ownership region")
                    if "value" in target and target["value"]!=field["value"]:raise ReferenceError("protected_mapping_conflict","Frozen values cannot be relaxed by replacement planning")
                    target_key=(target["partId"],target["path"])
                    if target_key in frozen and frozen[target_key]!=field["value"]:raise ReferenceError("protected_mapping_conflict","Merged ownership has conflicting protected values")
                    frozen[target_key]=deepcopy(field["value"])
                    protection_checks.append({"sourcePartId":field["partId"],"sourcePath":field["path"],"partId":target_key[0],"path":target_key[1],"value":deepcopy(field["value"])})
        plan["protectedTransferBaseline"]=protection_checks
    plan["contentHash"]=digest(plan)
    # Validate pointer shape and encoding during planning, before any live call.
    compile_operations(plan,"migration",{name:100000+i for i,name in enumerate(new_names)})
    compile_operations(plan,"finalize",{name:100000+i for i,name in enumerate(new_names)})
    return plan


def create_reshape(payload):
    """Plan in-place authoring without inventing replacement IDs or deleting parts."""
    snapshot=payload.get("snapshot")
    from reference_binding import unwrap
    if not snapshot or not unwrap(snapshot).get("xml"):
        raise ReferenceError("snapshot_incomplete","In-place planning requires includeXml:true")
    parts=snapshot_parts(snapshot);ident=identity(snapshot)
    targets=set(part_ids(payload.get("partIds",[]),"partIds"))
    locked=set(part_ids(payload.get("lockedPartIds",[]),"lockedPartIds"))
    if not targets:raise ReferenceError("invalid_scope","In-place shaping requires explicit partIds")
    if targets&locked:raise ReferenceError("locked_scope","In-place scope intersects locked parts")
    edits=deepcopy(payload.get("editOperations",[]))
    if not edits:raise ReferenceError("invalid_plan","In-place plan requires editOperations")
    allowed={"shape.update","properties.set","part.update","appearance.set","transform.apply"}
    for operation in edits:
        if operation.get("kind") not in allowed:
            raise ReferenceError("invalid_plan","In-place edits cannot add, delete or change assembly topology",kind=operation.get("kind"))
        if operation.get("symmetric") or operation.get("assembly"):
            raise ReferenceError("invalid_scope","Declare all in-place targets explicitly; implicit symmetry/assembly edits are unsupported")
        if operation.get("kind") in ("shape.update","properties.set","part.update","transform.apply"):
            # shape.update propagates to enabled symmetry peers when omitted.
            # Never rely on a native default for an explicitly scoped plan.
            operation["symmetric"]=False
        if operation.get("groupId") is not None:
            raise ReferenceError("invalid_scope","In-place transforms require explicit partIds, not an implicit local group")
        if operation.get("kind")=="appearance.set" and operation.get("mode")=="shared":
            raise ReferenceError("invalid_scope","Shared material edits require a separate whole-craft review")
        operation_ids=operation.get("partIds",[operation.get("partId")])
        if not operation_ids or any(isinstance(i,bool) or not isinstance(i,int) or i not in targets for i in operation_ids):
            raise ReferenceError("invalid_scope","Every in-place operation target must belong to partIds")
    boundary=set(part_ids(payload.get("boundaryPartIds",[]),"boundaryPartIds"))
    touched=targets|locked|boundary
    touched.update(op["anchorPartId"] for op in edits if isinstance(op.get("anchorPartId"),int))
    impact=inspect_impact(snapshot,sorted(targets))
    for connection in impact["externalConnections"]:touched.update((connection["partA"],connection["partB"]))
    for group in impact["symmetryGroups"]:touched.update(group["outsidePartIds"])
    touched.update(dep["partId"] for dep in impact["nestedReferences"])
    if any(str(i) not in parts for i in touched):raise ReferenceError("part_not_found","In-place scope contains missing parts")
    if not payload.get("qualityProfile"):raise ReferenceError("profile_not_frozen","In-place plan requires a frozen quality profile")
    from quality_gates import evaluate
    evaluate(payload["qualityProfile"],{"metrics":[],"checks":{}})
    if not isinstance(payload.get("materialIntent"),dict) or not payload["materialIntent"]:
        raise ReferenceError("material_intent_required","In-place plan requires material intent or explicit preserve")
    size=payload.get("batchSize",4)
    if isinstance(size,bool) or not isinstance(size,int) or not 1<=size<=100:raise ReferenceError("invalid_plan","batchSize must be 1..100")
    plan={"kind":KIND,"schemaVersion":1,"planId":str(uuid.uuid4()),"createdAt":utc_now(),"state":"planned","mode":"reshape",
          "batchSize":size,"structureId":payload.get("structureId"),"craftIdentity":ident,"oldPartIds":[],"partIds":sorted(targets),
          "lockedPartIds":sorted(locked),"guardPartIds":sorted(touched),"binding":bind(snapshot,sorted(touched)),
          "editOperations":edits,"createOperations":[],"migrationOperations":[],"finalizeOperations":[],"partMapping":{},"referencePaths":[],
          "impact":impact,"materialIntent":deepcopy(payload["materialIntent"]),"qualityProfile":deepcopy(payload["qualityProfile"]),
          "expectedChanges":deepcopy(payload.get("expectedChanges",{})),"loopJournalPath":payload.get("loopJournalPath"),
          "limitations":["In-place execution does not create or delete parts.","Native rebuild and finite geometry checks do not imply visual approval or native save.",
                         "Geometry neighbours not present in boundaryPartIds require a separate impact report."]}
    plan["contentHash"]=digest(plan)
    return plan


def validate(plan):
    if plan.get("kind")!=KIND or plan.get("schemaVersion")!=1:raise ReferenceError("incompatible_schema","Unsupported structure plan")
    if digest({k:v for k,v in plan.items() if k!="contentHash"})!=plan.get("contentHash"):
        raise ReferenceError("plan_changed","Plan content differs from its immutable hash; create a new plan")
    return plan


def _pointer_get(root,pointer):
    keys=[key.replace("~1","/").replace("~0","~") for key in pointer.lstrip("/").split("/")]
    current=root
    try:
        for key in keys[:-1]:current=current[int(key)] if isinstance(current,list) else current[key]
        key=int(keys[-1]) if isinstance(current,list) else keys[-1]
        return current,key,current[key]
    except (KeyError,ValueError,IndexError,TypeError) as exc:raise ReferenceError("invalid_reference_path","Reference path does not exist",path=pointer) from exc


def compile_operations(plan,stage,temporary_ids):
    operations=deepcopy(plan[stage+"Operations"])
    old_to_new={int(old):temporary_ids[temp] for old,temp in plan["partMapping"].items()}
    top_fields=("partId","partA","partB","sourcePartId","targetPartId","anchorPartId","wingPartId")
    for operation in operations:
        for field in top_fields:
            if isinstance(operation.get(field),str) and operation[field] in temporary_ids:operation[field]=temporary_ids[operation[field]]
        if "partIds" in operation:operation["partIds"]=[temporary_ids.get(v,v) if isinstance(v,str) else v for v in operation["partIds"]]
    for spec in plan["referencePaths"]:
        if spec.get("stage","migration")!=stage:continue
        try:operation=operations[spec["operationIndex"]]
        except IndexError as exc:raise ReferenceError("invalid_reference_path","Reference operation index is outside stage") from exc
        parent,key,value=_pointer_get(operation,spec["path"])
        encoding=spec["encoding"]
        values=[value] if encoding=="integer" else value.split(",") if encoding=="csv" and isinstance(value,str) else value
        if not isinstance(values,list):raise ReferenceError("invalid_reference_type","Reference encoding does not match field",path=spec["path"])
        mapped=[]
        for item in values:
            if isinstance(item,str) and item in temporary_ids:mapped.append(temporary_ids[item]);continue
            if isinstance(item,bool) or not isinstance(item,(int,str)):
                raise ReferenceError("invalid_reference_type","Expected integer ID or temporaryId",value=item)
            try:old=int(item)
            except ValueError as exc:raise ReferenceError("invalid_reference_type","Expected declared ID or temporaryId",value=item) from exc
            if old<0:raise ReferenceError("invalid_reference_type","Part reference IDs must be nonnegative",value=item)
            semantic=plan.get("semanticMapping",{})
            if encoding!="integer" and str(old) in semantic:
                mapped.extend(temporary_ids[name] for name in semantic[str(old)])
            elif encoding=="integer" and str(old) in semantic and not semantic[str(old)]:
                raise ReferenceError("invalid_reference_type","A retired scalar reference needs an explicit migration/removal",sourcePartId=old)
            else:mapped.append(old_to_new.get(old,old))
        parent[key]=mapped[0] if encoding=="integer" else ",".join(str(i) for i in mapped) if encoding=="csv" else mapped
    return operations
