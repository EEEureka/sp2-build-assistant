"""Session-scoped bindings, save recenter tracking, and three-way change protection."""
from __future__ import annotations

from copy import deepcopy
import xml.etree.ElementTree as ET
from .reference_storage import ReferenceError, digest, utc_now
from .registration import register_points, transform_point, compose, identity_transform, norm


def unwrap(result):
    if isinstance(result,dict) and result.get("success") is False:
        error=result.get("error",{})
        if not isinstance(error,dict):error={"message":str(error)}
        details=deepcopy(error.get("details",{})) if isinstance(error.get("details"),dict) else {}
        details.update({k:deepcopy(v) for k,v in error.items() if k not in ("code","message")})
        # wait() adds attribution beside the result, not inside error.details.
        # Keep both the usable attribution and the complete native response.
        for key in ("operationId","instancePid","writeDisposition"):
            if key in result:details[key]=deepcopy(result[key])
        details["response"]=deepcopy(result)
        raise ReferenceError(error.get("code","live_failed"),error.get("message","Live request failed"),**details)
    if isinstance(result,dict) and "data" in result:
        return result["data"]
    return result


def identity(snapshot):
    value=unwrap(snapshot)
    ident=value.get("identity",{})
    if not ident.get("craftSessionId") or isinstance(ident.get("revision"),bool) or not isinstance(ident.get("revision"),int):
        raise ReferenceError("invalid_snapshot", "Snapshot requires craftSessionId and revision")
    if ident.get("stateUncertain"):
        raise ReferenceError("state_uncertain", "Live state is uncertain; reconcile before continuing")
    return deepcopy(ident)


def _node(element):
    return {"tag":element.tag,"attributes":dict(sorted(element.attrib.items())),"text":element.text if element.text and element.text.strip() else None,
            "children":[_node(child) for child in element]}


def semantic_xml(xml):
    """Authored XML identity v3; input remains intact for saves and evidence.

    These four precise native paths contain generated aerodynamic result arrays.
    Editable drag metadata and modifier-local attributes remain significant.
    """
    try:root=ET.fromstring(xml)
    except ET.ParseError as exc:raise ReferenceError("invalid_snapshot","Snapshot aircraft XML is invalid") from exc
    if root.tag=="Aircraft":
        for element in root.findall("./Assembly/Parts/Part")+root.findall("./CraftDrag"):
            for key in ("drag","dragArea"):element.attrib.pop(key,None)
    return root


def _semantic_part(part):
    value=deepcopy(part);node=value.get("serializedState")
    if node and node.get("tag")=="Part":
        for key in ("drag","dragArea"):node.get("attributes",{}).pop(key,None)
    return value


def snapshot_parts(snapshot):
    value=unwrap(snapshot)
    parts={str(p["id"]):deepcopy(p) for p in value.get("parts",[])}
    if len(parts)!=len(value.get("parts",[])):
        raise ReferenceError("invalid_snapshot", "Snapshot contains duplicate part IDs")
    if value.get("xml"):
        try:
            root=semantic_xml(value["xml"])
            for element in root.findall("./Assembly/Parts/Part"):
                key=element.get("id")
                if key in parts:
                    parts[key]["serializedState"]=_node(element)
        except ET.ParseError as exc:
            raise ReferenceError("invalid_snapshot", "Snapshot aircraft XML is invalid") from exc
    return parts


def snapshot_context(snapshot):
    """Assembly edges and shared state are not children of individual Part XML."""
    value=unwrap(snapshot);connections=[];materials=None;variables=value.get("variables");authored=None
    if value.get("xml"):
        try:
            root=semantic_xml(value["xml"])
            nodes=root.findall("./Assembly/Connections/Connection")
            for node in nodes:
                attrs=node.attrib
                a,b=int(attrs["partA"]),int(attrs["partB"])
                pa=sorted(int(x) for x in attrs.get("attachPointsA","").split(",") if x.strip())
                pb=sorted(int(x) for x in attrs.get("attachPointsB","").split(",") if x.strip())
                if a>b:a,b,pa,pb=b,a,pb,pa
                connections.append({"partA":a,"partB":b,"attachPointsA":pa,"attachPointsB":pb})
            theme=root.find("Theme")
            materials=[_node(node) for node in theme.findall("Material")] if theme is not None else None
            node=root.find("Variables")
            if node is not None:variables=_node(node)
            # Parts, connections, materials and variables have their own scoped
            # comparisons. Retain every other authored global XML field.
            global_root=deepcopy(root)
            assembly=global_root.find("Assembly")
            if assembly is not None:
                for tag in ("Parts","Connections"):
                    for node in assembly.findall(tag):assembly.remove(node)
            theme=global_root.find("Theme")
            if theme is not None:
                for node in theme.findall("Material"):theme.remove(node)
            for node in global_root.findall("Variables"):global_root.remove(node)
            authored=_node(global_root)
        except (ET.ParseError,ValueError,KeyError) as exc:
            raise ReferenceError("invalid_snapshot","Invalid assembly connection or shared-state XML") from exc
    elif value.get("connections"):
        for node in value["connections"].get("children",[]):
            attrs=node.get("attributes",{})
            if node.get("element")!="Connection":continue
            try:
                a,b=int(attrs["partA"]),int(attrs["partB"])
                pa=sorted(int(x) for x in attrs.get("attachPointsA","").split(",") if x.strip());pb=sorted(int(x) for x in attrs.get("attachPointsB","").split(",") if x.strip())
            except (ValueError,KeyError) as exc:raise ReferenceError("invalid_snapshot","Invalid connection record") from exc
            if a>b:a,b,pa,pb=b,a,pb,pa
            connections.append({"partA":a,"partB":b,"attachPointsA":pa,"attachPointsB":pb})
    return {"connections":sorted(connections,key=canonical_connection_key),"materials":materials,"variables":variables,"authoredState":authored,"semanticVersion":3}


def canonical_connection_key(connection):
    return str(connection["partA"])+":"+",".join(str(i) for i in connection.get("attachPointsA",[]))+"|"+str(connection["partB"])+":"+",".join(str(i) for i in connection.get("attachPointsB",[]))


def part_signature(part, include_pose=True):
    value=_semantic_part(part)
    value.pop("typeName",None)
    if not include_pose:
        for key in ("position","rotationEulerDegrees","rotationQuaternion"):
            value.pop(key,None)
        node=value.get("serializedState")
        if node:
            for key in ("position","rotation","rotationQuaternion"):
                node["attributes"].pop(key,None)
    return digest(value)


def bind(snapshot, part_ids=None, anchors=None, reference_transform=None):
    ident=identity(snapshot)
    parts=snapshot_parts(snapshot)
    selected=list(parts) if part_ids is None else [str(i) for i in part_ids]
    missing=[int(i) for i in selected if i not in parts]
    if missing:
        raise ReferenceError("part_not_found", "Binding parts are missing", partIds=missing)
    anchor_values=[]
    for anchor in anchors or []:
        key=str(anchor["partId"])
        if key not in parts:
            raise ReferenceError("part_not_found", "Anchor part is missing", partId=anchor["partId"])
        anchor_values.append({"partId":int(key),"position":deepcopy(parts[key]["position"]),"intrinsicHash":part_signature(parts[key],False)})
    return {"schemaVersion":1,"identity":ident,"craftName":unwrap(snapshot).get("name"),"boundAt":utc_now(),
            "partIds":[int(i) for i in selected],"parts":{i:parts[i] for i in selected},
            "baselineParts":parts,
            "contextState":snapshot_context(snapshot),
            "partHashes":{i:part_signature(parts[i]) for i in selected},"anchors":anchor_values,
            "referenceToCraft":reference_transform or identity_transform(),"transformHistory":[],
            "observability":{"serializedPartState":bool(unwrap(snapshot).get("xml")),"paletteProperties":snapshot_context(snapshot)["materials"] is not None,
                             "persistentPartIdentity":False,"semanticVersion":3},
            "meaning":"Numeric IDs are scoped to this session; cross-session binding requires explicit mapping and geometry checks."}


def changes(binding, snapshot, affected_ids=None, reused_ids=None):
    current_id=identity(snapshot)
    if current_id["craftSessionId"]!=binding["identity"]["craftSessionId"]:
        return {"status":"rebind_required","reason":"session_changed","conflicts":[],"unrelated":[],"changedPartIds":[]}
    parts=snapshot_parts(snapshot)
    affected=set(str(i) for i in (binding["partIds"] if affected_ids is None else affected_ids))
    baseline={key:_semantic_part(part) for key,part in binding.get("baselineParts",binding["parts"]).items()}
    changed=[key for key in sorted(set(baseline)|set(parts),key=int) if baseline.get(key)!=parts.get(key)]
    reused=set(str(i["partId"] if isinstance(i,dict) else i) for i in (reused_ids or []))
    conflicts=[int(key) for key in changed if key in affected]
    conflicts=sorted(set(conflicts)|{int(key) for key in reused if key in affected})
    before_context=binding.get("contextState",{});after_context=snapshot_context(snapshot)
    before_connections={canonical_connection_key(c):c for c in before_context.get("connections",[])}
    after_connections={canonical_connection_key(c):c for c in after_context["connections"]}
    connection_changes=[{"key":key,"before":before_connections.get(key),"after":after_connections.get(key)} for key in sorted(set(before_connections)^set(after_connections))]
    topology_conflicts=[change for change in connection_changes if any(str(connection[key]) in affected for connection in (change["before"],change["after"]) if connection for key in ("partA","partB"))]
    before_materials=before_context.get("materials");after_materials=after_context["materials"];material_conflicts=[];material_changes=[]
    if before_materials is not None and after_materials is not None:
        material_changes=[i for i in range(max(len(before_materials),len(after_materials))) if (before_materials[i] if i<len(before_materials) else None)!=(after_materials[i] if i<len(after_materials) else None)]
        used={material for key in affected for part in (baseline.get(key),parts.get(key)) if part for material in part.get("materialIds",[])}
        material_conflicts=sorted(used&set(material_changes))
    global_conflicts=["variables"] if before_context.get("variables")!=after_context["variables"] else []
    if "authoredState" in before_context and before_context["authoredState"]!=after_context["authoredState"]:
        global_conflicts.append("authoredXml")
    return {"status":"state_changed" if conflicts or topology_conflicts or material_conflicts or global_conflicts else "compatible", "conflicts":conflicts,
            "unrelated":[int(key) for key in changed if key not in affected],"changedPartIds":[int(key) for key in changed],
            "reusedPartIds":[int(key) for key in sorted(reused,key=int)],"identity":current_id,
            "topologyConflicts":topology_conflicts,"materialConflicts":material_conflicts,"globalConflicts":global_conflicts,
            "unrelatedConnectionChanges":[c for c in connection_changes if c not in topology_conflicts],"unrelatedMaterialChanges":[i for i in material_changes if i not in material_conflicts],
            "baselineRevision":binding["identity"]["revision"]}


def _flatten(value, prefix=""):
    if isinstance(value,dict):
        result={}
        for key,item in value.items(): result.update(_flatten(item,prefix+"/"+str(key)))
        return result
    return {prefix:value}


def three_way(base, proposed, current):
    """Field-level merge for planning only. Arrays remain atomic; never mutates live state."""
    b,p,c=_flatten(base),_flatten(proposed),_flatten(current)
    missing=object(); conflicts=[]; intended=[]; unrelated=[]
    for key in sorted(set(b)|set(p)|set(c)):
        bv,pv,cv=b.get(key,missing),p.get(key,missing),c.get(key,missing)
        ours=pv!=bv; theirs=cv!=bv
        if ours and theirs and pv!=cv: conflicts.append(key)
        elif ours: intended.append(key)
        elif theirs: unrelated.append(key)
    return {"status":"conflict" if conflicts else "mergeable","conflicts":conflicts,"intendedChanges":intended,"preservedCurrentChanges":unrelated}


def rebind(binding,snapshot,part_mapping=None,tolerance=1e-4):
    """Validate a rigid save/recenter. New session needs an explicit old→new mapping."""
    current_id=identity(snapshot); parts=snapshot_parts(snapshot)
    same_session=current_id["craftSessionId"]==binding["identity"]["craftSessionId"]
    if not same_session and not part_mapping:
        raise ReferenceError("rebind_required", "New session requires explicit old-to-current part mapping")
    mapping={str(k):str(v) for k,v in (part_mapping or {str(i):i for i in binding["partIds"]}).items()}
    if len(set(mapping.values()))!=len(mapping):
        raise ReferenceError("invalid_binding", "Part mapping must be one-to-one")
    sources=[]; targets=[]
    if len(binding.get("anchors",[]))<3:
        raise ReferenceError("underconstrained", "Recenter tracking requires at least three noncollinear anchors")
    for anchor in binding["anchors"]:
        key=mapping.get(str(anchor["partId"]))
        if key not in parts or part_signature(parts[key],False)!=anchor["intrinsicHash"]:
            # The numeric id is different across sessions; compare intrinsic part content without id.
            old=deepcopy(binding["parts"].get(str(anchor["partId"]),{})); new=deepcopy(parts.get(key,{}))
            old.pop("id",None);new.pop("id",None)
            for item in (old,new):
                if item.get("serializedState"): item["serializedState"]["attributes"].pop("id",None)
            if not key or key not in parts or part_signature(old,False)!=part_signature(new,False):
                raise ReferenceError("state_changed", "Anchor changed or was reused; cannot infer a rigid recenter",partId=anchor["partId"])
        sources.append(anchor["position"]);targets.append(parts[key]["position"])
    transform=register_points(sources,targets,tolerance)
    if transform["status"]!="registered":
        raise ReferenceError("nonrigid_change", "Anchors do not share a rigid transform",registration=transform)
    local_changes=[]
    for old_key,old_part in binding["parts"].items():
        key=mapping.get(old_key)
        if key not in parts:
            local_changes.append({"partId":int(old_key),"reason":"missing"});continue
        expected=transform_point(transform,old_part["position"])
        residual=norm([a-b for a,b in zip(expected,parts[key]["position"])])
        # A change in intrinsic state is always local, even if the origin follows the anchors.
        old=deepcopy(old_part);new=deepcopy(parts[key])
        old.pop("id",None);new.pop("id",None)
        for item in (old,new):
            if item.get("serializedState"):item["serializedState"]["attributes"].pop("id",None)
        rotation_residual=0.
        if old.get("rotationQuaternion") and new.get("rotationQuaternion"):
            import math
            ax,ay,az,aw=transform["rotationQuaternion"];bx,by,bz,bw=old["rotationQuaternion"]
            expected_q=[aw*bx+ax*bw+ay*bz-az*by,aw*by-ax*bz+ay*bw+az*bx,aw*bz+ax*by-ay*bx+az*bw,aw*bw-ax*bx-ay*by-az*bz]
            actual_q=new["rotationQuaternion"]
            cosine=abs(sum(a*b for a,b in zip(expected_q,actual_q)))/(norm(expected_q)*norm(actual_q))
            rotation_residual=math.degrees(2*math.acos(min(1.,cosine)))
        if residual>tolerance or rotation_residual>1e-4 or part_signature(old,False)!=part_signature(new,False):
            local_changes.append({"partId":int(key),"reason":"local_change","positionResidualMetres":residual,"rotationResidualDegrees":rotation_residual})
    updated=bind(snapshot,[int(mapping[k]) for k in binding["parts"] if mapping.get(k) in parts],
                 [{"partId":int(mapping[str(a["partId"])])} for a in binding["anchors"]],
                 compose(transform,binding["referenceToCraft"]))
    updated["transformHistory"]=binding.get("transformHistory",[])+[{"at":utc_now(),"fromIdentity":binding["identity"],"toIdentity":current_id,"transform":transform}]
    return {"binding":updated,"registration":transform,"localChanges":local_changes,"status":"local_changes_present" if local_changes else "rigid_rebound"}
