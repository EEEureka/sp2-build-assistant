"""Persistent logical names and groups, with evidence-bound native identities.

Project files are SDK metadata. They are never written into native aircraft XML.
Rebinding is explicit and cannot use a recycled numeric ID as identity evidence.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import uuid

from .errors import ModelingError
from .geometry import magnitude, multiply, rotate, sub
from .transport import canonical_json


def same_identity(left, right):
    return all(left.get(k) == right.get(k) for k in ("craftSessionId", "revision", "fingerprint"))


def label(value, what="name"):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ModelingError("invalid_input", f"{what} must contain 1..128 nonblank characters.")
    return value


def evidence(row, snapshot):
    required = ("contentFingerprint", "partFingerprint", "lifetimeId")
    if any(not isinstance(row.get(k), str) or not row[k] for k in required):
        raise ModelingError("binding_evidence_unavailable", "Persistent objects require native content, exact-part and lifetime evidence.")
    frame = snapshot["craftFrame"]
    q = frame["rotationQuaternion"]
    inverse = (-q[0], -q[1], -q[2], q[3])
    return {"type": row["type"], **{key: row[key] for key in required},
            "contentFingerprintAlgorithm": row.get("contentFingerprintAlgorithm"),
            "relativePosition": list(rotate(inverse, sub(row["position"], frame["position"]))),
            "relativeRotation": list(multiply(inverse, row["rotationQuaternion"])),
            "bindingRoundtripState":deepcopy(row.get('bindingRoundtripState'))}


def _endpoint_roundtrip(old,current):
    a,b=deepcopy(old.get('bindingRoundtripState')),deepcopy(current.get('bindingRoundtripState'))
    if not a or not b or old['type']!='JDriveShaft-1' or current['type']!='JDriveShaft-1':return None
    deltas=[]
    try:
        for tree in (a,b):
            states=[s for s in tree.get('children',[]) if s.get('element')=='JDriveShaft.State']
            if len(states)!=1:return None
            attrs=states[0]['attributes'];pair=[]
            for key in ('start','end'):
                values=tuple(float(v.strip()) for v in attrs[key].strip('()').split(','))
                if len(values)!=3 or any(not math.isfinite(v) for v in values):return None
                pair.append(values);attrs.pop(key)
            deltas.append(pair)
    except (KeyError,ValueError,TypeError):return None
    if a!=b:return None
    error=max(magnitude(sub(x,y)) for x,y in zip(*deltas))
    return error if error<=.000002 else None


def matching_evidence(old, current, *, same_epoch, accept_native_endpoint_roundtrip=False):
    if (old["type"] != current["type"] or (old["contentFingerprint"] != current["contentFingerprint"] and
            not (accept_native_endpoint_roundtrip and not same_epoch and _endpoint_roundtrip(old,current) is not None))
            or old.get("contentFingerprintAlgorithm") != current.get("contentFingerprintAlgorithm")):
        return False
    if same_epoch and old["lifetimeId"] != current["lifetimeId"]:
        return False
    if magnitude(sub(old["relativePosition"], current["relativePosition"])) > 0.00002:
        return False
    qa, qb = old["relativeRotation"], current["relativeRotation"]
    # q and -q encode the same rotation. This is a finite float round-trip
    # allowance, not permission to accept arbitrary native shape normalization.
    return min(magnitude(sub(qa, qb)), magnitude(tuple(a+b for a, b in zip(qa, qb)))) <= 0.00002


class Project:
    SCHEMA = "sp2model.project/1"

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            initial = {"schemaVersion": self.SCHEMA, "projectId": uuid.uuid4().hex,
                       "objects": {}, "groups": {}, "materials": {}, "processedOperations": []}
            try:
                with self.path.open("xb") as stream:
                    stream.write(canonical_json(initial)); stream.flush(); os.fsync(stream.fileno())
            except FileExistsError:
                pass
        self.reload()

    def reload(self):
        try:
            raw = self.path.read_bytes()
            data = json.loads(raw)
            if data.get("schemaVersion") != self.SCHEMA or not all(isinstance(data.get(k), dict) for k in ("objects", "groups", "materials")):
                raise ValueError()
        except (OSError, ValueError, TypeError):
            raise ModelingError("invalid_project", "Project metadata is missing, malformed or has an unsupported schema.") from None
        self._data, self._disk_hash = data, hashlib.sha256(raw).hexdigest()
        return self

    @property
    def id(self):
        return self._data["projectId"]

    @property
    def objects(self):
        return deepcopy(self._data["objects"])

    @property
    def groups(self):
        return deepcopy(self._data["groups"])

    @property
    def materials(self):
        return deepcopy(self._data["materials"])

    @property
    def semantic_shapes(self):
        return deepcopy(self._data.get("semanticShapes", {}))

    @contextmanager
    def _write_lock(self):
        path = self.path.with_name(self.path.name + ".lock")
        try:
            stream = path.open("xb")
        except FileExistsError:
            raise ModelingError("project_busy", "Another project update is active. A lock left by a crashed process needs explicit review.") from None
        try:
            with stream:
                stream.write(str(os.getpid()).encode("ascii")); stream.flush(); os.fsync(stream.fileno())
            yield
        finally:
            path.unlink(missing_ok=True)

    def update(self, *, objects=None, groups=None, materials=None, processed_operations=None, semantic_shapes=None):
        with self._write_lock():
            self._update(objects=objects, groups=groups, materials=materials, processed_operations=processed_operations, semantic_shapes=semantic_shapes)

    def _update(self, *, objects=None, groups=None, materials=None, processed_operations=None, semantic_shapes=None):
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self._disk_hash:
            raise ModelingError("project_conflict", "Another process changed this project. Reload and review before updating metadata.")
        data = deepcopy(self._data)
        for key, replacement in (("objects", objects), ("groups", groups), ("materials", materials), ("processedOperations", processed_operations), ("semanticShapes", semantic_shapes)):
            if replacement is not None:
                data[key] = deepcopy(replacement)
        raw = canonical_json(data)
        temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("xb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        # Fail closed if another writer won while this update was prepared.
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self._disk_hash:
            temporary.unlink()
            raise ModelingError("project_conflict", "Project changed during metadata update.")
        os.replace(temporary, self.path)
        self._data, self._disk_hash = data, hashlib.sha256(raw).hexdigest()

    def bound(self, row, identity, instance_id):
        matches = []
        for logical_id, item in self._data["objects"].items():
            if item.get("retired"):
                continue
            binding = item.get("binding")
            if (binding and binding["instanceId"] == instance_id and binding["partId"] == row["id"]
                    and same_identity(binding["identity"], identity)
                    and item["evidence"]["lifetimeId"] == row.get("lifetimeId")):
                matches.append((logical_id, deepcopy(item)))
        if len(matches) > 1:
            raise ModelingError("binding_ambiguous", "Multiple logical objects claim the same live part.")
        return matches[0] if matches else None

    @staticmethod
    def binding(row, snapshot, instance_id):
        return {"instanceId": instance_id, "identity": deepcopy(snapshot["identity"]), "partId": row["id"]}

    def track(self, row, snapshot, instance_id, *, name, tags=(), logical_id=None):
        name = label(name)
        if isinstance(tags, str):
            raise ModelingError("invalid_input", "tags must be a collection of tag strings.")
        tags = sorted(set(label(tag, "tag") for tag in tags))
        current = self.bound(row, snapshot["identity"], instance_id)
        logical_id = logical_id or (current[0] if current else uuid.uuid4().hex)
        objects = self.objects
        if objects.get(logical_id, {}).get("retired"):
            raise ModelingError("reference_retired", "A retired logical ID cannot be assigned to a new native object.",
                                {"logicalId": logical_id, "retirement": objects[logical_id]["retired"]})
        objects[logical_id] = {"name": name, "tags": tags, "evidence": evidence(row, snapshot),
                               "binding": self.binding(row, snapshot, instance_id)}
        self.update(objects=objects)
        return logical_id

    def rebind(self, snapshot, instance_id, *, logical_ids=None, mapping=None, accept_native_endpoint_roundtrip=False, _evidence_objects=None):
        objects = self.objects
        # Only the task's explicitly reviewed exact-checkpoint reconciliation
        # supplies historical evidence. Matching remains strict and atomic.
        if _evidence_objects is not None:
            for key,item in _evidence_objects.items():
                if key not in objects:raise ModelingError('invalid_reference','Checkpoint evidence belongs to another project')
                objects[key]=deepcopy(item)
        # Automatic candidate enumeration excludes tombstones. Explicitly
        # requesting one still fails, including an explicit native mapping.
        logical_ids = [key for key, item in objects.items() if not item.get("retired")] if logical_ids is None else list(logical_ids)
        for key in logical_ids + list(mapping or {}):
            if objects.get(key, {}).get("retired"):
                raise ModelingError("reference_retired", "This logical object was conclusively removed or replaced and cannot be rebound.",
                                    {"logicalId": key, "retirement": objects[key]["retired"]})
        if len(set(logical_ids)) != len(logical_ids) or any(key not in objects for key in logical_ids):
            raise ModelingError("invalid_reference", "Rebind requires distinct logical IDs from this project.")
        mapping = {} if mapping is None else mapping
        if any(key not in logical_ids for key in mapping):
            raise ModelingError("invalid_reference", "Explicit mapping contains objects outside this rebind request.")
        candidates = [(row, evidence(row, snapshot)) for row in snapshot["parts"]]
        selected = {}
        for logical_id in logical_ids:
            item = objects[logical_id]
            old_binding = item.get("binding") or item.get("previousBinding")
            same_epoch = bool(old_binding and old_binding["instanceId"] == instance_id
                              and old_binding["identity"]["craftSessionId"] == snapshot["identity"]["craftSessionId"])
            matches = [(row, ev) for row, ev in candidates
                       if matching_evidence(item["evidence"], ev, same_epoch=same_epoch,accept_native_endpoint_roundtrip=accept_native_endpoint_roundtrip)
                       and (logical_id not in mapping or row["id"] == mapping[logical_id])]
            if len(matches) != 1:
                raise ModelingError("binding_ambiguous" if len(matches) > 1 else "binding_mismatch",
                                    "Logical object has no unique matching native content, pose and lifetime evidence.",
                                    {"logicalId": logical_id, "name": item["name"], "candidateIds": [r["id"] for r, _ in matches],
                                     "nativeEndpointRoundtripCandidates":[{'partId':row['id'],'maximumEndpointDifferenceMetres':_endpoint_roundtrip(item['evidence'],ev),'toleranceMetres':.000002}
                                         for row,ev in candidates if not same_epoch and _endpoint_roundtrip(item['evidence'],ev) is not None],
                                     "hint":"Review native endpoint roundtrip differences explicitly; accept_native_endpoint_roundtrip=True enables only this bounded cross-session policy. Other fields, pose, uniqueness and lifetime guards remain."})
            row, ev = matches[0]
            if row["id"] in selected.values():
                raise ModelingError("binding_ambiguous", "Two logical objects would bind to one native part.")
            selected[logical_id] = row["id"]
            item.update(binding=self.binding(row, snapshot, instance_id), evidence=ev)
        self.update(objects=objects)
        return selected

    def after_execution(self, snapshot, instance_id, baseline, result, plan):
        """Advance identities only through an observed, successful own operation."""
        operation_id = result.get("operationId")
        processed = self._data.get("processedOperations", [])
        if operation_id and operation_id in processed:
            return
        objects = self.objects
        rows = {row["id"]: row for row in snapshot["parts"]}
        # Native receipts include diagnostic objects; older fixtures can use
        # numeric IDs. Neither form authorizes keeping a recycled binding.
        reused = set()
        for entry in result.get("reusedPartIds", []):
            identifier = entry.get("partId") if isinstance(entry, dict) else entry
            if not isinstance(identifier, int) or isinstance(identifier, bool):
                raise ModelingError("binding_evidence_unavailable", "Native reused-part evidence has an invalid part ID.")
            reused.add(identifier)
        for item in objects.values():
            if item.get("retired"):
                continue
            binding = item.get("binding")
            if not binding or binding["instanceId"] != instance_id:
                continue
            row = rows.get(binding["partId"])
            current_evidence = None if row is None else evidence(row, snapshot)
            if plan.get('scoped'):
                if binding['identity']['craftSessionId'] != baseline['craftSessionId'] or current_evidence is None: continue
                if row['id'] in plan['writablePartIds']:
                    original = plan.get('scopedBeforeEvidence', {}).get(str(row['id']))
                    if original is None or plan.get('scopedCraftFrame') != snapshot['craftFrame'] or not matching_evidence(item['evidence'], original, same_epoch=True): continue
                elif not matching_evidence(item['evidence'], current_evidence, same_epoch=True):
                    # A concurrent edit is not absorbed as our own operation.
                    continue
            elif not same_identity(binding['identity'], baseline): continue
            if (row is None or row["id"] in reused
                    or row.get("lifetimeId") != item["evidence"]["lifetimeId"]):
                reason = "deleted" if row is None else "native_id_reused" if row["id"] in reused else "lifetime_replaced"
                item.update(previousBinding=binding, binding=None, retired={
                    "reason": reason, "operationId": operation_id, "instanceId": instance_id,
                    "partId": binding["partId"], "identity": deepcopy(snapshot["identity"])})
                continue
            item.update(binding=self.binding(row, snapshot, instance_id), evidence=current_evidence)
        mapping = result.get("temporaryIds", {})
        for name, obj in plan.get("objects", {}).items():
            identifier = mapping.get(obj["temporaryId"])
            if identifier is None or identifier not in rows:
                continue
            row = rows[identifier]
            existing = next((key for key, value in objects.items() if not value.get("retired") and value.get("creationRequestId") == result.get("operationId")
                             and value.get("temporaryId") == obj["temporaryId"]), None)
            logical_id = existing or uuid.uuid4().hex
            objects[logical_id] = {"name": name, "tags": [], "evidence": evidence(row, snapshot),
                "binding": self.binding(row, snapshot, instance_id), "creationRequestId": result.get("operationId"), "temporaryId": obj["temporaryId"]}
        groups = self.groups
        for name, group in plan.get("groups", {}).items():
            label(name, "group name")
            ids = [mapping.get(ref, ref) for ref in group["partIds"]]
            members = []
            for identifier in ids:
                keys = [key for key, item in objects.items() if not item.get("retired") and item.get("binding") and item["binding"]["partId"] == identifier
                        and same_identity(item["binding"]["identity"], snapshot["identity"])]
                if not keys and identifier in rows:
                    row = rows[identifier]
                    key = uuid.uuid4().hex
                    objects[key] = {"name": (row.get("name") or f"part-{identifier}")[:128], "tags": [],
                                    "evidence": evidence(row, snapshot), "binding": self.binding(row, snapshot, instance_id)}
                    keys = [key]
                if len(keys) != 1:
                    raise ModelingError("binding_ambiguous", "Logical group member is missing or has multiple native bindings.")
                members.extend(keys)
            groups[name] = members
        semantics=self.semantic_shapes
        for name,definition in plan.get("semanticShapes",{}).items():
            current=deepcopy(definition)
            ids=[mapping.get(ref,ref) for ref in current['parts']]
            if any(identifier not in rows for identifier in ids):
                raise ModelingError('semantic_binding_missing','A semantic member is missing after execution')
            current['parts']=ids
            for field in ('poses','configurations'):
                current[field]={str(mapping.get(ref,ref) if not str(ref).isdigit() else mapping.get(ref,int(ref))):value for ref,value in current[field].items()}
            current['identity']=deepcopy(snapshot['identity'])
            current['instanceId']=instance_id
            semantics[name]=current
        self.update(objects=objects, groups=groups, semantic_shapes=semantics,
                    processed_operations=processed + ([operation_id] if operation_id else []))
