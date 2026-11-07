"""Scene references, immutable preview approval and recoverable native batches."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import uuid
from .errors import ModelingError
from .transport import BridgeClient, canonical_json
from .geometry import Frame, rotate, dot, sub, magnitude
from .journal import Journal
from .project import Project, label
from .objects import MaterialRef


def _same(a, b):
    return all(a.get(k) == b.get(k) for k in ("craftSessionId", "revision", "fingerprint"))


def _digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class PartRef:
    id: int
    name: str
    type: str
    logical_id: str
    _identity: dict = field(repr=False)
    _instance: str = field(repr=False)
    _pose: dict = field(repr=False)
    tags: tuple = ()
    project_id: str | None = None

    @property
    def native_name(self):
        return self._pose.get("name", "")

    @property
    def logical_name(self):
        return self.name if self.project_id is not None else None

    @property
    def binding_status(self):
        return "bound" if self.project_id is not None else "native_only"

    def to_dict(self):
        """Export captured public data; this never refreshes or authorizes it."""
        return {"id":self.id,"name":self.name,"type":self.type,"logicalId":self.logical_id,
                "nativeName":self.native_name,"logicalName":self.logical_name,"bindingStatus":self.binding_status,
                "position":deepcopy(self._pose.get('position')),"rotationQuaternion":deepcopy(self._pose.get('rotationQuaternion')),
                "scale":deepcopy(self._pose.get('scale')),"tags":list(self.tags),"projectId":self.project_id}

    @property
    def frame(self):
        return Frame.from_pose(self._pose, binding=(self._instance, self._identity["craftSessionId"], self._identity["revision"], self._identity["fingerprint"]))


class Scene:
    def __init__(self, session, snapshot):
        self._session=session
        self.name = snapshot["name"]
        self.identity = deepcopy(snapshot["identity"])
        self.parts = tuple(session._part(row, self.identity) for row in snapshot["parts"])
        self.connections = deepcopy(snapshot.get("connections"))
        self.craft_frame = Frame.from_pose(snapshot["craftFrame"], binding=(session.client.instance["instanceId"],
                self.identity["craftSessionId"], self.identity["revision"], self.identity["fingerprint"]))

    def to_dict(self):
        """Export this captured scene without reading the game or Session."""
        return {'name':self.name,'identity':deepcopy(self.identity),'parts':[p.to_dict() for p in self.parts],
                'connections':deepcopy(self.connections),'craftFrame':self.craft_frame.to_dict()}

    def select(self, *, name=None, type=None, tags=()):
        if isinstance(tags, str):
            raise ModelingError("invalid_input", "tags must be a collection of strings.")
        required = set(tags)
        if name is not None and self._session.project:
            known=[(key,item) for key,item in self._session.project.objects.items() if item['name']==name]
            if known and not any(p.project_id is not None and p.name==name for p in self.parts):
                retired=all(item.get('retired') for key,item in known)
                raise ModelingError('reference_retired' if retired else 'stale_reference',
                    'Logical name is retired or unbound; inspect bindings and explicitly select/rebind current objects. Native-name fallback is disabled for this alias.',
                    {'logicalName':name,'logicalIds':[key for key,item in known],'bindingStatus':'retired' if retired else 'unbound'})
        return tuple(p for p in self.parts if (name is None or p.name == name) and (type is None or p.type == type)
                     and required.issubset(p.tags))

    def part(self, id=None, *, name=None):
        if (id is None) == (name is None):
            raise ModelingError("invalid_selector", "Choose exactly one explicit id or name.")
        matches = [p for p in self.parts if p.id == id] if id is not None else list(self.select(name=name))
        if len(matches) != 1:
            raise ModelingError("binding_ambiguous" if matches else "part_not_found", "Selector needs exactly one object.", {"matchIds": [p.id for p in matches]})
        return matches[0]


@dataclass(frozen=True)
class Preview:
    token: str
    plan_hash: str
    writable_part_ids: tuple
    report: dict


@dataclass(frozen=True)
class Receipt:
    request_id: str
    operation_id: str
    identity: dict
    objects: dict
    result: dict
    plan: dict
    journal_path: str

    def to_dict(self):
        return {"requestId": self.request_id, "operationId": self.operation_id,
                "identity": deepcopy(self.identity), "objects": {name: {"id": p.id, "logicalId": p.logical_id} for name, p in self.objects.items()},
                "result": deepcopy(self.result), "plan": deepcopy(self.plan), "journalPath": self.journal_path}


class Session:
    """An explicit binding to one instance and one currently open craft.

    References intentionally expire on ANY native revision change in a1. Calling
    inspect acknowledges a new baseline, but never refreshes an existing plan.
    """
    def __init__(self, client, *, craft=None, journal_dir=None, project_path=None, summary_only=False):
        self.client = client
        self.capabilities = client.call("craft.status" if summary_only else "capabilities")
        capability = self.capabilities.get("modelingSdk", {})
        if capability.get("contract") != "sp2model/1" or capability.get("scope") != "sp2model.scope/1":
            raise ModelingError("sdk_plugin_mismatch", "This SDK needs the route A plugin with model-scope guards.", {"required": "sp2model/1"})
        if not self.capabilities.get("designerReady"):
            raise ModelingError("designer_not_ready", "Open the intended craft in the native designer first.")
        self._snapshot = deepcopy(self.capabilities) if summary_only else client.call("craft.snapshot")
        self._summary_only = summary_only
        if craft is not None and craft not in (self._snapshot["name"], self._snapshot["identity"]["craftSessionId"]):
            raise ModelingError("craft_mismatch", "The currently open craft does not match the requested target.")
        self._session_id = self._snapshot["identity"]["craftSessionId"]
        self._templates, self._previews, self._receipts, self._executions = {}, {}, {}, {}
        self._restore_reviews = {}
        self._restore_executions = {}
        directory = journal_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SP2BuildAssistant" / "agent-sdk" / "journals"
        self.journal = Journal(directory)
        self.project = None if project_path is None else Project(project_path)
        self.last_control = None

    @classmethod
    def attach(cls, instance=None, craft=None, *, discovery_dir=None, journal_dir=None, timeout=30, project_path=None, summary_only=False):
        return cls(BridgeClient.discover(instance, discovery_dir, timeout), craft=craft, journal_dir=journal_dir, project_path=project_path, summary_only=summary_only)

    @property
    def identity(self):
        return deepcopy(self._snapshot["identity"])

    def _part(self, row, identity):
        # Conservative epoch binding makes deleted/recycled numeric IDs unusable.
        binding = f'{self.client.instance["instanceId"]}:{identity["craftSessionId"]}:{identity["revision"]}:{row["id"]}'
        tracked = self.project.bound(row, identity, self.client.instance["instanceId"]) if self.project else None
        if tracked:
            logical_id, item = tracked
            return PartRef(row["id"], item["name"], row["type"], logical_id, deepcopy(identity),
                           self.client.instance["instanceId"], deepcopy(row), tuple(item["tags"]), self.project.id)
        return PartRef(row["id"], row.get("name", ""), row["type"], uuid.uuid5(uuid.NAMESPACE_URL, binding).hex,
                       deepcopy(identity), self.client.instance["instanceId"], deepcopy(row))

    def inspect(self):
        snapshot = self.client.call("craft.snapshot")
        if snapshot["identity"]["craftSessionId"] != self._session_id:
            raise ModelingError("session_conflict", "The craft was replaced or reloaded. Attach a new session explicitly.")
        self._snapshot = snapshot
        self._summary_only = False
        return Scene(self, snapshot)

    def status(self, *, refresh=True):
        """Compact live identity; never transports parts or refreshes old references."""
        status = self.client.call("craft.status") if refresh or not self._summary_only else deepcopy(self._snapshot)
        if not status.get("identity") or status["identity"]["craftSessionId"] != self._session_id:
            raise ModelingError("session_conflict", "The designer craft is no longer this session.", {"observed": status})
        public = self.client.instance
        return {**status, "instance": {key: public[key] for key in ("instanceId", "pid", "pluginVersion", "protocolVersion", "baseUrl") if key in public}}

    def query(self, *, part_ids=None, name=None, type=None, fields=None, offset=0, limit=50, identity=None, logical_name=None, tags=(), group=None):
        """Bounded native page; pass its identity to every subsequent page."""
        args = {"offset": offset, "limit": limit}
        if isinstance(tags,str):raise ModelingError('invalid_input','tags must be an explicit collection')
        local_filter=logical_name is not None or bool(tags) or group is not None
        selected_objects=None
        if local_filter:
            project=self._ensure_project();objects=project.objects
            if group is not None and group not in project.groups:raise ModelingError('group_not_found','Logical group is not present')
            keys=set(project.groups[group]) if group is not None else set(objects)
            selected_objects={key:item for key,item in objects.items() if key in keys and (logical_name is None or item['name']==logical_name) and set(tags)<=set(item['tags'])}
            retired=[key for key,item in selected_objects.items() if item.get('retired')]
            if retired:raise ModelingError('reference_retired','Filtered logical objects contain retired members',{'logicalIds':retired})
            invalid=[key for key,item in selected_objects.items() if not item.get('binding') or item['binding']['instanceId']!=self.client.instance['instanceId'] or not _same(item['binding']['identity'],self.identity)]
            if invalid:raise ModelingError('stale_reference','Filtered logical objects need explicit current rebind',{'logicalIds':invalid})
            identifiers={item['binding']['partId'] for item in selected_objects.values()}
            part_ids=sorted(identifiers if part_ids is None else identifiers.intersection(part_ids))
            identity=self.identity if identity is None else identity
        if self.project and fields is not None:fields=list(dict.fromkeys([*fields,'lifetimeId','name']))
        for key, value in (("partIds", part_ids), ("name", name), ("type", type), ("fields", fields)):
            if value is not None: args[key] = deepcopy(value)
        if identity is not None:
            args.update(craftSessionId=identity["craftSessionId"], expectedRevision=identity["revision"])
        page = self.client.call("parts.query", args)
        if page["identity"]["craftSessionId"] != self._session_id:
            raise ModelingError("session_conflict", "Query belongs to a new craft session.")
        if identity is not None and not _same(identity, page["identity"]):
            raise ModelingError("revision_conflict", "Query pages changed identity.")
        if self.project:
            for row in page['items']:
                bound=self.project.bound(row,page['identity'],self.client.instance['instanceId'])
                if selected_objects is not None and (bound is None or bound[0] not in selected_objects):raise ModelingError('stale_reference','A queried logical object no longer matches its native lifetime')
                row['nativeName']=row.get('name');row['logicalId']=None if bound is None else bound[0]
                row['logicalName']=None if bound is None else bound[1]['name'];row['tags']=[] if bound is None else bound[1]['tags']
                row['bindingStatus']='native_only' if bound is None else 'bound'
        return page

    def dependencies(self, parts):
        if isinstance(parts,PartRef):parts=[parts]
        ids=[self._resolve_ref(part) for part in parts]
        result=self.client.call("model.dependencies", {"craftSessionId":self._session_id,"expectedRevision":self.identity["revision"],"partIds":ids})
        if not _same(result["identity"],self.identity):raise ModelingError("stale_evidence","Dependency report changed identity")
        return result

    def _resolve_ref(self, value):
        if not isinstance(value, PartRef):
            raise ModelingError("invalid_reference", "Select a PartRef from scene.part(id=...) or scene.select(...); raw numeric write references are not accepted.")
        if value._instance != self.client.instance["instanceId"] or not _same(value._identity, self.identity):
            raise ModelingError("stale_reference", "Object belongs to another instance, session or revision. Query the original execution before any retry; explicitly reselect current members.",
                {"partId": value.id, "logicalId": value.logical_id, "name": value.name,
                 "expected": {"instanceId": value._instance, **value._identity},
                 "actual": {"instanceId": self.client.instance["instanceId"], **self.identity},
                 "cause": "not_inferred", "nextAction": "resume_original_execution_then_rebind"})
        if value.id not in {p["id"] for p in self._snapshot["parts"]}:
            raise ModelingError("stale_reference", "Object is no longer present.")
        return value.id

    def plan(self, *, frame=None, length_unit="m", writable=None, variables=()):
        from .plan import Plan
        if self._summary_only:
            raise ModelingError("full_inspection_required", "A compact status is not a modeling baseline. Call inspect() before constructing a plan.")
        return Plan(self, frame=frame, length_unit=length_unit, writable=writable, variables=variables)

    def native_plan(self, operations, *, writable, variables=(), material_ids=()):
        from .native import NativePlan
        return NativePlan(self, operations, writable=writable, variables=variables, material_ids=material_ids)

    def scope(self, parts, *, boundary=(), owner_id):
        from .native import NativeScope
        return NativeScope(self, parts, boundary=boundary, owner_id=owner_id)

    def read(self, command, **arguments):
        """Published native query with captured identity added when required."""
        from .registry import schema, validate
        from .transport import READ_COMMANDS
        if command not in READ_COMMANDS:
            raise ModelingError('read_only', 'Use a reviewed plan or dedicated recovery/control method for writes.')
        spec = schema(command)
        fields = spec.get('properties', {})
        args = deepcopy(arguments)
        if 'craftSessionId' in fields: args.setdefault('craftSessionId', self.identity['craftSessionId'])
        if 'expectedRevision' in fields: args.setdefault('expectedRevision', self.identity['revision'])
        validate(args, spec)
        return self.client.call(command, args)

    def service(self, command, *, native_scope=None, **arguments):
        """Reference, fit, build-loop and structured revision services."""
        from .runtime import Runtime
        runtime = Runtime(client=self.client, journal_dir=self.journal.directory / 'services')
        return runtime.call(command, arguments, session=self, native_scope=native_scope)

    def undo_preview(self):
        history = self.client.call('craft.history')
        self._fresh(self.identity)
        token = uuid.uuid4().hex
        if not hasattr(self, '_undo_reviews'): self._undo_reviews = {}
        self._undo_reviews[token] = {'identity': self.identity, 'history': deepcopy(history)}
        return {'token': token, 'scope': 'whole_craft', 'identity': self.identity, 'history': history,
                'meaning': 'Undo may affect concurrent work; review history and explicitly accept whole-craft scope.'}

    def undo(self, token, *, accept_whole_craft=False):
        review = getattr(self, '_undo_reviews', {}).get(token)
        if review is None or accept_whole_craft is not True:
            raise ModelingError('review_required', 'Review undo_preview and accept whole-craft scope.')
        self._fresh(review['identity'])
        current = self.client.call('craft.history')
        if current != review['history']: raise ModelingError('history_conflict', 'History changed after review.')
        args = {'craftSessionId': self.identity['craftSessionId'], 'expectedRevision': self.identity['revision']}
        if current.get('headHash'): args['expectedHeadHash'] = current['headHash']
        result = self._native_command('craft.undo', args)
        self._undo_reviews.pop(token, None)
        self.inspect()
        return result

    def _validate_frame(self, frame):
        binding = getattr(frame, "_binding", None)
        current = (self.client.instance["instanceId"], self._session_id, self.identity["revision"], self.identity["fingerprint"])
        if binding is not None and binding != current:
            raise ModelingError("stale_frame", "Captured craft/part frame belongs to an old native state. Inspect and capture it again, or explicitly use a custom world frame.")

    def _resolve_template(self, style):
        if style not in self._templates:
            names = {"Body": ("Fuselage", "JFuselage-1"), "Cone": ("Nose Cone", "JFuselage-Cone-1"),
                     "Curved": ("Curved Fuselage", "JFuselage-2"), "Wing": ("Primary Wing", "JWing-1"),
                     "Hole": ("Hole", "ModifierWindow-1")}
            if style not in names:
                raise ModelingError("unsupported_template", "Unsupported native constructor: " + style)
            native_name, native_type = names[style]
            candidates = self.client.call("catalog.search", {"query": native_name, "limit": 1000})["listing"]["items"]
            candidates = [p for p in candidates if p["name"] == native_name and p["source"] == "builtin" and p["creatable"]]
            if len(candidates) != 1:
                raise ModelingError("template_ambiguous", "No unique built-in native template for " + style)
            entry = candidates[0]
            schema = self.client.call("catalog.schema", {"id": entry["id"]})["templates"][0]
            if not schema["parts"] or schema["parts"][0]["partType"] != native_type:
                raise ModelingError("unsupported_template", "The discovered template root does not match the native constructor.")
            part = schema["parts"][0]
            self._templates[style] = {"id": entry["id"], "type": part["partType"], "defaultState": part["defaultState"],
                                      "metadata": deepcopy(part.get("metadata", {})), "parts": deepcopy(schema["parts"]), "schema": deepcopy(schema)}
        return deepcopy(self._templates[style])

    def templates(self, *, query=None, offset=0, limit=100):
        args={"offset":offset,"limit":limit}
        if query is not None: args["query"]=query
        return self.client.call("catalog.list", args)

    def template(self, template_id):
        label(template_id, "template id")
        entry=self.client.call("catalog.get", {"id":template_id})
        schema=self.client.call("catalog.schema", {"id":template_id})["templates"][0]
        return {**entry,"schema":schema}

    def _fresh(self, identity):
        status = self.client.call("designer.status")
        if not status.get("identity") or not _same(status["identity"], identity):
            raise ModelingError("revision_conflict", "Native state changed. Inspect and construct a new plan; this plan is not rebased automatically.", {"expected": identity, "actual": status.get("identity")})

    @staticmethod
    def _writes(plan):
        ids = set()
        for op in plan["operations"]:
            for key in ("partId", "partA", "partB", "sourcePartId", "targetPartId", "wingPartId", "anchorPartId"):
                if type(op.get(key)) is int:
                    ids.add(op[key])
            ids.update(x for x in op.get("partIds", []) if type(x) is int)
            ids.update(x for x in op.get("targetPartIds", []) if type(x) is int)
        explicit = plan["writablePartIds"]
        if explicit is not None and not ids.issubset(explicit):
            raise ModelingError("scope_violation", "The plan refers to parts outside its explicit writable set.")
        return sorted(ids if explicit is None else explicit)

    def _args(self, plan, writes):
        args = {"craftSessionId": plan["baselineIdentity"]["craftSessionId"], "expectedRevision": plan["baselineIdentity"]["revision"],
                "operations": deepcopy(plan["operations"]), "modelScope": {"version": "sp2model.scope/1", "writablePartIds": writes,
                 "variableNames": deepcopy(plan.get("variableNames", [])),
                 "paletteAppend": any(op["kind"] == "appearance.set" and op.get("mode") == "clone" for op in plan["operations"])}}
        if plan.get('writableMaterialIds'): args['modelScope']['writableMaterialIds'] = deepcopy(plan['writableMaterialIds'])
        return args

    def _preview(self, plan):
        document = plan.to_dict()
        if not _same(document["baselineIdentity"], self.identity):
            raise ModelingError("revision_conflict", "Plan and inspected baseline differ.")
        self._fresh(document["baselineIdentity"])
        writes = self._writes(document)
        symmetry = None
        if any(op["kind"] in {"symmetry.create", "part.mirror"} for op in document["operations"]):
            symmetry = self.client.call("symmetry.get")
            if not _same(symmetry["identity"], document["baselineIdentity"]):
                raise ModelingError("revision_conflict", "Symmetry settings changed while previewing.")
            if symmetry["configuration"]["mode"] != "Mirrored":
                raise ModelingError("unsupported_symmetry", "mirror requires native Mirrored mode; radial duplication is a different operation.")
        report = self.client.call("batch.preview", self._args(document, writes))
        if symmetry is not None:
            report["nativeSymmetry"] = symmetry["configuration"]
        token = uuid.uuid4().hex
        preview = Preview(token, _digest(document), tuple(writes), deepcopy(report))
        self._previews[token] = preview
        return preview

    def _apply(self, plan, preview_token):
        document = plan.to_dict()
        preview = self._previews.get(preview_token)
        if preview is None or preview.plan_hash != _digest(document):
            raise ModelingError("preview_mismatch", "Preview is missing, from another session, or the plan changed after preview.")
        if preview_token in self._receipts:
            return self._receipts[preview_token]
        if preview_token in self._executions:
            receipt = self.resume(self._executions[preview_token])
            self._receipts[preview_token] = receipt
            return receipt
        pending = self.journal.pending(self.client.instance["instanceId"], self._session_id)
        if pending:
            raise ModelingError("pending_execution", "Resolve the earlier execution before another write; do not replay it.", {"journals": pending})
        self._fresh(document["baselineIdentity"])
        request = uuid.uuid4().hex
        args = self._args(document, list(preview.writable_part_ids))
        if "nativeSymmetry" in preview.report:
            args["modelExpectedSymmetry"] = deepcopy(preview.report["nativeSymmetry"])
        record = {"schemaVersion": "sp2model.execution/1", "requestId": request, "operationId": None, "state": "prepared",
                  "instance": self.client.instance, "baselineIdentity": document["baselineIdentity"], "plan": document,
                  "payloadHash": _digest(args), "args": args}
        path = self.journal.create(record)
        self._executions[preview_token] = path
        observer = getattr(self, "_on_execution_prepared", None)
        if observer is not None:
            try: observer(path)
            except Exception as error:
                # Linking failed before submit was called. Preserve a terminal
                # unsent record rather than leaving a phantom pending request.
                failure = ModelingError('journal_link_failed', 'Execution linking failed before native submission.',
                    {'journalPath': str(path), 'requestId': request, 'writeDisposition': 'not_submitted', 'reason': str(error)})
                record.update(state='failed', error=failure.to_dict())
                self.journal.update(path, record)
                raise failure from error
        try:
            record["operationId"] = self.client.submit("batch.apply", args, request_id=request)
            record["state"] = "submitted"
            self.journal.update(path, record)
            result = self.client.wait(record["operationId"])
        except ModelingError as error:
            uncertain = error.details.get("outcome") == "unknown" or error.code in {"outcome_unknown", "wait_timeout", "result_expired", "operation_not_found", "transport_error", "invalid_response"}
            record["state"] = "outcome_unknown" if uncertain else "failed"
            record["error"] = error.to_dict()
            self.journal.update(path, record)
            error.details["journalPath"] = str(path)
            raise
        record.update(state="succeeded", result=result)
        self.journal.update(path, record)
        receipt = self._receipt(record, path)
        self._receipts[preview_token] = receipt
        self.inspect()
        return receipt

    def _receipt(self, record, path):
        result, plan = deepcopy(record["result"]), record["plan"]
        mapping, refs = result.get("temporaryIds", {}), {}
        snapshot = self.client.call("craft.snapshot")
        if _same(snapshot["identity"], result["identity"]):
            self._snapshot = snapshot
            if self.project:
                self.project.after_execution(snapshot, self.client.instance["instanceId"], record["baselineIdentity"], result, plan)
            actual = {p["id"]: p for p in snapshot["parts"]}
            for name, obj in plan["objects"].items():
                id = mapping.get(obj["temporaryId"])
                if id is not None and id in actual:
                    refs[name] = self._part(actual[id], result["identity"])
            result["objectBindingStatus"] = "current_native_readback"
        else:
            result["objectBindingStatus"] = "stale_no_live_references"
            result["bindingReason"] = "Execution succeeded but native state changed. Inspect and select objects explicitly; historical IDs are not rebound automatically."
        return Receipt(record["requestId"], record["operationId"], deepcopy(result["identity"]), refs, deepcopy(result), deepcopy(plan), str(path))

    def resume(self, journal_path):
        """Read or finish an existing result. NEVER submits an operation."""
        document = json.loads(Path(journal_path).read_text(encoding='utf-8'))
        if document.get('schemaVersion') == 'sp2model.runtime/1':
            from .runtime import Runtime
            if document.get('args', {}).get('craftSessionId') not in (None, self._session_id):
                raise ModelingError('session_conflict', 'Use Runtime.resume to query this historical craft epoch without rebinding.')
            result = Runtime(client=self.client, journal_dir=Path(journal_path).parent).resume(journal_path)
            if document.get('command') == 'scoped.batch.apply':
                from .native import deliver_scoped
                return deliver_scoped(self, result, document)
            return result
        record = Journal.read(journal_path)
        if record["instance"]["instanceId"] != self.client.instance["instanceId"]:
            raise ModelingError("instance_conflict", "The process restarted or another instance is attached; review native content before explicit re-binding.")
        if record.get("kind") != "control" and record["baselineIdentity"]["craftSessionId"] != self._session_id:
            raise ModelingError("session_conflict", "The journal belongs to another craft session.")
        if record["state"] == "failed":
            e = record["error"]
            raise ModelingError(e["code"], e["message"], e.get("details"))
        if record["state"] != "succeeded":
            if not record.get("operationId"):
                lookup = getattr(self.client, "lookup_request", None)
                try:
                    if not callable(lookup):
                        raise ModelingError("request_lookup_unavailable", "This client does not support request lookup.")
                    job = lookup(record["requestId"])
                    if not isinstance(job.get("operationId"), str) or not job["operationId"]:
                        raise ModelingError("bridge_protocol_error", "Request lookup did not return an operation ID.")
                except ModelingError as cause:
                    error = ModelingError("outcome_unknown", "The original request could not be located. Its outcome remains unknown; the payload will not be replayed.",
                        {"requestId": record["requestId"], "journalPath": str(journal_path), "instance": self.client.instance,
                         "lookupError": cause.to_dict(), "outcome": "unknown", "retrySafe": False})
                    record.update(state="outcome_unknown", error=error.to_dict())
                    Journal.update(journal_path, record)
                    raise error from None
                record.update(operationId=job["operationId"], state="submitted")
                record.pop("error", None)
                Journal.update(journal_path, record)
            try:
                result = self.client.wait(record["operationId"])
            except ModelingError as error:
                error.details["journalPath"] = str(journal_path)
                if error.details.get("outcome") != "unknown" and error.code not in {"wait_timeout", "result_expired", "operation_not_found", "transport_error", "invalid_response"}:
                    record.update(state="failed", error=error.to_dict())
                    Journal.update(journal_path, record)
                raise
            record.update(state="succeeded", result=result)
            Journal.update(journal_path, record)
        if record.get("kind") == "control":
            self.last_control = {**deepcopy(record["result"]), "requestId": record["requestId"], "journalPath": str(journal_path)}
            if record["args"]["action"] == "save":
                snapshot = self.client.call("craft.snapshot")
                if _same(snapshot["identity"], record["result"]["identity"]):
                    self._snapshot = snapshot
                    if self.project:
                        self.project.after_execution(snapshot, self.client.instance["instanceId"], record["baselineIdentity"], record["result"], {})
            return self.last_control
        if record.get("kind") == "native_command":
            return {**deepcopy(record["result"]), "requestId": record["requestId"], "journalPath": str(journal_path)}
        return self._receipt(record, journal_path)

    def _native_command(self, command, args, *, prepared=None):
        """Durable non-plan native operation. Resume queries, never replays it."""
        pending = self.journal.pending(self.client.instance["instanceId"], self._session_id)
        if pending:
            raise ModelingError("pending_execution", "Query the existing execution before another write", {"journals":pending})
        self._fresh(self.identity)
        request = uuid.uuid4().hex
        record = {"schemaVersion":"sp2model.execution/1", "kind":"native_command", "state":"prepared",
                  "requestId":request, "instance":self.client.instance, "baselineIdentity":self.identity,
                  "command":command, "args":deepcopy(args)}
        path = self.journal.create(record)
        observer = getattr(self, "_on_native_prepared", None)
        if observer is not None: observer(str(path))
        if prepared is not None: prepared(str(path))
        try:
            operation_id = self.client.submit(command, args, request_id=request)
            record.update(state="submitted", operationId=operation_id)
            self.journal.update(path, record)
            result = self.client.wait(operation_id)
        except ModelingError as error:
            unknown = error.details.get("outcome") == "unknown" or error.code in {"outcome_unknown","wait_timeout","result_expired","operation_not_found"}
            record.update(state="outcome_unknown" if unknown else "failed", error=error.to_dict())
            self.journal.update(path, record)
            error.details.update(journalPath=str(path), requestId=request)
            raise
        record.update(state="succeeded", result=result)
        self.journal.update(path, record)
        return {**deepcopy(result), "requestId":request, "journalPath":str(path)}

    def checkpoints(self):
        return self.client.call("craft.checkpoint.list")

    def checkpoint(self, name, *, pinned=True):
        label(name, "checkpoint name")
        if type(pinned) is not bool: raise ModelingError("invalid_input", "pinned must be boolean")
        result = self._native_command("craft.checkpoint.create", {"craftSessionId":self._session_id,
            "expectedRevision":self.identity["revision"], "name":name, "pinned":pinned})
        return {**result, "lifecycle": {"storage": "native_session_checkpoint", "sessionBound": True,
            "craftSessionId": self._session_id, "survivesReopen": False, "survivesRestart": False,
            "invalidatedBy": ["craft_load", "process_exit", "explicit_prune", "native_capacity_eviction"],
            "capacityPolicy": "Query checkpoints() for current native capacity; pinned does not survive a craft epoch change.",
            "persistentAlternative": "Explicitly save a named native craft copy; diagnostic exports are not restore points."}}

    def checkpoint_info(self, checkpoint_id):
        return self.client.call("craft.checkpoint.get", {"id":checkpoint_id})

    def prune_checkpoints(self, checkpoint_ids, *, include_pinned=False):
        if isinstance(checkpoint_ids, str) or type(include_pinned) is not bool:
            raise ModelingError("invalid_input", "Use an explicit checkpoint ID list and boolean include_pinned")
        return self._native_command("craft.checkpoint.prune", {"craftSessionId":self._session_id,
            "expectedRevision":self.identity["revision"], "ids":list(checkpoint_ids), "includePinned":include_pinned})

    def restore_preview(self, checkpoint_id):
        """Review whole-craft overwrite; it is never an automatic failure recovery."""
        scene = self.inspect()
        checkpoint = self.checkpoint_info(checkpoint_id)
        diff = self.client.call("craft.diff", {"checkpointId":checkpoint_id, "limit":1000})
        if not _same(scene.identity, checkpoint["identity"]) or not _same(scene.identity, diff["identity"]):
            raise ModelingError("revision_conflict", "State changed while reviewing the restore")
        review = {"baselineIdentity":scene.identity, "checkpoint":checkpoint["checkpoint"], "diff":diff["diff"],
                  "scope":"whole_current_craft", "currentPartCount":len(scene.parts),
                  "warning":"Current changes since the checkpoint will be overwritten, including unrelated edits. Review this scope explicitly.",
                  "diffDirection":"before is the checkpoint to restore; after is the current state to overwrite"}
        token = _digest(review)
        self._restore_reviews[token] = deepcopy(review)
        return {**review, "token":token}

    def restore(self, token, *, accept_whole_craft=False):
        if accept_whole_craft is not True or token not in self._restore_reviews:
            raise ModelingError("restore_review_required", "Use restore_preview and explicitly accept its whole-craft overwrite scope")
        if token in self._restore_executions:
            return self._restore_delivery(self.resume(self._restore_executions[token]))
        review = self._restore_reviews[token]
        self._fresh(review["baselineIdentity"])
        if not _same(self.identity, review["baselineIdentity"]):
            raise ModelingError("revision_conflict", "Restore review is stale")
        result = self._native_command("craft.rollback", {"craftSessionId":self._session_id,
            "expectedRevision":self.identity["revision"], "checkpointId":review["checkpoint"]["id"]},
            prepared=lambda path:self._restore_executions.__setitem__(token,path))
        return self._restore_delivery(result)

    def _restore_delivery(self,result):
        result=deepcopy(result)
        snapshot = self.client.call("craft.snapshot")
        self._snapshot = snapshot
        result["bindingStatus"] = "review_required" if self.project else "no_project"
        result["bindings"] = self.bindings()
        result["currentIdentity"] = deepcopy(snapshot["identity"])
        result['staleAtDelivery']=not _same(result.get('identity',{}),snapshot['identity'])
        return result

    def bindings(self):
        """Logical aliases, native names and retired/unbound evidence are distinct."""
        if not self.project: return []
        rows = {p["id"]:p for p in self._snapshot.get("parts", [])}
        result = []
        for logical_id, item in self.project.objects.items():
            binding = item.get("binding") or {}
            row = rows.get(binding.get("partId"))
            bound = row is not None and _same(binding.get("identity", {}), self.identity) and item.get("evidence",{}).get("lifetimeId")==row.get("lifetimeId")
            result.append({"logicalId":logical_id, "logicalName":item["name"], "nativeName":None if row is None else row.get("name"),
                           "bindingStatus":"retired" if item.get("retired") else "bound" if bound else "unbound",
                           "partId":binding.get("partId"), "tags":deepcopy(item.get("tags", [])), "retirement":deepcopy(item.get("retired"))})
        return result

    def expand(self, part):
        id = self._resolve_ref(part)
        result = self.client.call("parts.get", {"id": id})
        if not _same(result["identity"], part._identity):
            raise ModelingError("stale_reference", "Object changed while reading details.")
        return result["part"]

    def _ensure_project(self):
        if self.project is None:
            identity = self.client.instance["instanceId"] + ":" + self._session_id
            self.project = Project(self.journal.directory / "projects" / (uuid.uuid5(uuid.NAMESPACE_URL, identity).hex + ".json"))
        return self.project

    def track(self, part, *, name=None, tags=()):
        """Persist a logical name/tags with strong native identity evidence."""
        identifier = self._resolve_ref(part)
        self._fresh(self.identity)
        row = next(p for p in self._snapshot["parts"] if p["id"] == identifier)
        project = self._ensure_project()
        project.track(row, self._snapshot, self.client.instance["instanceId"], name=part.name if name is None else name, tags=tags)
        return self._part(row, self.identity)

    def group(self, name, parts):
        """Store logical membership only; no native connections are created."""
        label(name, "group name")
        parts = tuple(parts)
        if not parts:
            raise ModelingError("invalid_input", "A logical group must contain at least one part.")
        tracked = tuple(part if part.project_id == self._ensure_project().id else self.track(part) for part in parts)
        for part in tracked:
            self._resolve_ref(part)
        keys = [part.logical_id for part in tracked]
        if len(set(keys)) != len(keys):
            raise ModelingError("invalid_input", "A group cannot contain duplicate objects.")
        groups = self.project.groups
        groups[name] = keys
        self.project.update(groups=groups)
        return tracked

    def select(self, *, name=None, type=None, tags=(), group=None):
        scene = self.inspect()
        if group is None:
            return scene.select(name=name, type=type, tags=tags)
        if self.project is None or group not in self.project.groups:
            raise ModelingError("group_not_found", "Logical group is not present in this project.")
        selected = {part.logical_id: part for part in scene.select(name=name, type=type, tags=tags)}
        keys = self.project.groups[group]
        retired = [key for key in keys if self.project.objects.get(key, {}).get("retired")]
        if retired:
            raise ModelingError("reference_retired", "Group contains permanently retired objects. Replace its membership explicitly with newly tracked objects.",
                                {"group": group, "logicalIds": retired})
        live = {part.logical_id for part in scene.parts}
        if any(key not in live for key in keys):
            raise ModelingError("stale_reference", "Group has unbound members. Explicitly rebind the project first.")
        return tuple(selected[key] for key in keys if key in selected)

    def group_parts(self, name):
        return self.select(group=name)

    def semantic(self, name):
        project=self._ensure_project()
        if name not in project.semantic_shapes:
            raise ModelingError('semantic_not_found','No saved semantic shape with this name')
        definition=project.semantic_shapes[name]
        parts=self.group_parts(name)
        if [part.id for part in parts]!=definition['parts']:
            raise ModelingError('semantic_binding_mismatch','Semantic member mapping changed; review the group')
        return deepcopy(definition),parts

    def rebind(self, logical_ids=None, *, mapping=None, accept_native_endpoint_roundtrip=False):
        """Explicitly rebind by native content, relative pose and lifetime evidence.

        Mapping values must be freshly selected PartRefs, never unverified IDs.
        Ambiguous matches fail as a whole, leaving existing metadata unchanged.
        """
        project = self._ensure_project()
        self.inspect()
        native_mapping = None if mapping is None else {key: self._resolve_ref(part) for key, part in mapping.items()}
        if type(accept_native_endpoint_roundtrip) is not bool:raise ModelingError('invalid_input','accept_native_endpoint_roundtrip must be boolean')
        selected = project.rebind(self._snapshot, self.client.instance["instanceId"], logical_ids=logical_ids, mapping=native_mapping,accept_native_endpoint_roundtrip=accept_native_endpoint_roundtrip)
        self._fresh(self.identity)
        rows = {row["id"]: row for row in self._snapshot["parts"]}
        return {key: self._part(rows[identifier], self.identity) for key, identifier in selected.items()}

    def shape(self, part):
        identifier = self._resolve_ref(part)
        result = self.client.call("shape.get", {"id": identifier})
        if not _same(result["identity"], part._identity):
            raise ModelingError("stale_reference", "Part changed during shape discovery.")
        return result["shape"]

    def schema(self, part=None, *, style=None):
        if (part is None) == (style is None):
            raise ModelingError("invalid_input", "Choose a native part or constructor style.")
        if style is not None:
            return self._resolve_template(style)["schema"]
        identifier = self._resolve_ref(part)
        result = self.client.call("properties.describe", {"id": identifier, "limit": 1000})
        if not _same(result["identity"], part._identity):
            raise ModelingError("stale_reference", "Part changed during property discovery.")
        return result

    def mechanical(self, part):
        identifier=self._resolve_ref(part)
        result=self.client.call('mechanical.get',{'id':identifier})
        if not _same(result['identity'],part._identity):raise ModelingError('stale_reference','Mechanical endpoints changed during discovery')
        return result

    def wing_stations(self,part,positions):
        identifier=self._resolve_ref(part)
        result=self.client.call('wing.stations',{'id':identifier,'positions':list(positions)})
        if not _same(result['identity'],part._identity):raise ModelingError('stale_reference','Native wing stations changed during discovery')
        return result

    def airfoils(self,*,name=None):
        return self.client.call('airfoils.describe',{} if name is None else {'name':name})

    def airfoil_curve(self,name,*,reynolds,mach,angles_deg):
        return self.client.call('airfoils.describe',{'name':name,'reynolds':reynolds,'mach':mach,'anglesDegrees':list(angles_deg)})

    def control_handles(self,part):
        from .wings import ControlHandle
        from .geometry import add,scale
        state=self.shape(part)
        if state.get('family')!='controlSurface' or state.get('wingPartId') is None:raise ModelingError('unsupported_control','A native attached edge surface is required')
        host=self.inspect().part(id=state['wingPartId']);config=state['configuration'];span=config['spanRange']
        rows=self.wing_stations(host,span)['stations'];fractions=state['chordFraction'];leading=state.get('style')=='Slat'
        handles=[]
        for i,endpoint in enumerate(('inner','outer')):
            center=rows[i]['worldCenter'];chord=rows[i]['nativeChordMetres'];offset=(.5-fractions[i])*chord*(1 if leading else -1)
            hinge=None if center is None else tuple(add(center,host.frame.direction((0,0,offset*rows[i]['chordScale']))))
            handles.extend((ControlHandle(part,host,'span',endpoint,span[i],deepcopy(part._identity),None if center is None else tuple(center),rows[i]['worldPositionStatus']),
                            ControlHandle(part,host,'hinge',endpoint,fractions[i],deepcopy(part._identity),hinge,rows[i]['worldPositionStatus'])))
        return tuple(handles)

    def state(self, part):
        """Complete native Overload tree and revision-bound attribute handles."""
        from .native_state import NativePartState
        identifier = self._resolve_ref(part)
        result = self.client.call("native.state", {"id":identifier})
        if not _same(result["identity"], part._identity):
            raise ModelingError("stale_reference", "Native state changed while discovering attributes")
        return NativePartState(part, result)

    def variables(self, *, name=None):
        from .objects import SetterRef
        result=self.client.call("variables.list", {"view":"structured"})
        if not _same(result["identity"], self.identity):
            raise ModelingError("stale_evidence", "Variables changed; inspect before taking new handles")
        return tuple(SetterRef(row["index"],row["variable"],row["function"],row["priority"],row.get("activator"),deepcopy(result["identity"]),self.client.instance["instanceId"])
                     for row in result["setters"] if name is None or row["variable"]==name)

    def outputs(self, part):
        from .objects import OutputRef
        detail=self.expand(part)
        result=[]
        for modifier in detail.get("outputs", []):
            for definition in modifier["definitions"]:
                bindings=tuple(b for b in modifier["bindings"] if b["outputId"]==definition["id"])
                result.append(OutputRef(part,modifier["modifier"],modifier.get("modifierIndex",0),definition["id"],deepcopy(definition),deepcopy(bindings)))
        return tuple(result)

    def inputs(self, part):
        from .objects import ControllerRef
        detail=self.expand(part)
        return tuple(ControllerRef(part,row["index"],deepcopy(row)) for row in detail.get("inputControllers", []))

    def funky(self, *, name=None):
        return self.client.call("funky.list" if name is None else "funky.describe", {} if name is None else {"name":name})

    def logic_dependencies(self,*,variable=None):
        result=self.client.call('logic.dependencies',{} if variable is None else {'variable':variable})
        if not _same(result['identity'],self.identity):raise ModelingError('stale_evidence','Logic graph changed during discovery')
        return result

    def validate_expression(self, expression, *, part=None, type=None, controller=None, field=None):
        if controller is not None and field is None:field="input"
        if type is None:type="bool" if field=="activationGroup" else "float"
        args={"expression":expression,"type":type}
        if part is not None: args["partId"]=self._resolve_ref(part)
        if controller is not None:
            args["partId"]=self._resolve_ref(controller.part);args["controllerIndex"]=controller.index
        if field is not None: args["field"]=field
        result=self.client.call("funky.validate",args)
        if not _same(result["identity"],self.identity):raise ModelingError("stale_evidence","Expression validation belongs to a changed native state")
        return result

    def properties(self, part, *, fields=None):
        identifier = self._resolve_ref(part)
        args = {"id": identifier, "limit": 1000}
        if fields is not None:
            args["fields"] = list(fields)
        result = self.client.call("properties.get", args)
        if not _same(result["identity"], part._identity):
            raise ModelingError("stale_reference", "Part changed during property readback.")
        return result

    def property_defaults(self,*,template_id=None,part_type=None,fields=None):
        if (template_id is None)==(part_type is None):raise ModelingError('invalid_selector','Choose an explicit template_id or a native part_type with unambiguous template selection')
        args={'templateId':template_id} if template_id is not None else {'type':part_type}
        if fields is not None:args['fields']=list(fields)
        return self.client.call('properties.describe',args)

    def appearance(self, parts=None):
        args = {"limit": 2048}
        if parts is not None:
            args["partIds"] = [self._resolve_ref(part) for part in parts]
        result = self.client.call("appearance.get", args)
        if not _same(result["identity"], self.identity):
            raise ModelingError("stale_reference", "Native appearance changed during discovery.")
        return result

    def materials(self, *, name=None):
        """Current native palette entries with IDs, reserved status and values."""
        return tuple(row for row in self.appearance()["palette"] if name is None or row["name"] == name)

    def track_material(self, material_id, *, name):
        label(name, "material name")
        candidates = [row for row in self.materials() if row["id"] == material_id]
        if len(candidates) != 1:
            raise ModelingError("material_not_found", "Choose one material from the current native palette.")
        project = self._ensure_project()
        materials = project.materials
        materials[name] = {"material": deepcopy(candidates[0]), "fingerprint": _digest(candidates[0]),
                           "instanceId": self.client.instance["instanceId"], "identity": self.identity}
        project.update(materials=materials)
        return MaterialRef(material_id, name, deepcopy(candidates[0]), self.identity, self.client.instance["instanceId"], _digest(candidates[0]))

    def material(self, name, *, rebind=False):
        if self.project is None or name not in self.project.materials:
            raise ModelingError("material_not_found", "Material name is not present in this project.")
        item = self.project.materials[name]
        if not rebind and (item["instanceId"] != self.client.instance["instanceId"] or not _same(item["identity"], self.identity)):
            raise ModelingError("stale_reference", "Explicitly rebind the named material against the current palette.")
        candidates = [row for row in self.materials() if _digest(row) == item["fingerprint"]]
        if len(candidates) != 1:
            raise ModelingError("binding_ambiguous", "Named material no longer has exactly one matching palette entry.")
        if rebind:
            return self.track_material(candidates[0]["id"], name=name)
        return MaterialRef(candidates[0]["id"], name, deepcopy(candidates[0]), self.identity,
                           self.client.instance["instanceId"], item["fingerprint"])

    def _resolve_material(self, material):
        if isinstance(material, MaterialRef):
            if material._instance != self.client.instance["instanceId"] or not _same(material._identity, self.identity):
                raise ModelingError("stale_reference", "Material belongs to another instance, session or revision.")
            identifier = material.id
        elif type(material) is int:
            identifier = material
        else:
            raise ModelingError("invalid_reference", "Use a MaterialRef or an explicit native palette ID.")
        matches = [row for row in self.materials() if row["id"] == identifier and not row.get("reserved")]
        if len(matches) != 1:
            raise ModelingError("material_not_editable", "Material is absent or reserved by the game.")
        if isinstance(material, MaterialRef) and _digest(matches[0]) != material._fingerprint:
            raise ModelingError("stale_reference", "Material contents changed after discovery.")
        return identifier

    def saved_crafts(self, *, query=None, offset=0, limit=100):
        args = {"offset": offset, "limit": limit}
        if query is not None:
            args["query"] = query
        return self.client.call("designer.crafts", args)

    def _control(self, action, extra):
        pending = self.journal.pending(self.client.instance["instanceId"], self._session_id)
        if pending:
            raise ModelingError("pending_execution", "Resolve prior unknown operations before saving or reopening.", {"journals": pending})
        status = self.client.call("designer.status")
        if not status.get("identity") or not _same(status["identity"], self.identity):
            raise ModelingError("revision_conflict", "Native craft changed before control action; inspect explicitly.")
        if not isinstance(status.get("scene"), str):
            raise ModelingError("bridge_protocol_error", "Designer status omitted its native scene.")
        args = {"action": action, "expectedScene": status["scene"], "craftSessionId": self._session_id,
                "expectedRevision": self.identity["revision"], "expectedCraftName": self._snapshot["name"], **extra}
        request_id = uuid.uuid4().hex
        record = {"schemaVersion": "sp2model.execution/1", "kind": "control", "command": "designer.control",
                  "requestId": request_id, "operationId": None, "state": "prepared", "instance": self.client.instance,
                  "baselineIdentity": self.identity, "args": args, "payloadHash": _digest(args)}
        path = self.journal.create(record)
        observer = getattr(self, "_on_native_prepared", None)
        if observer is not None: observer(str(path))
        try:
            record.update(operationId=self.client.submit("designer.control", args, request_id=request_id), state="submitted")
            self.journal.update(path, record)
            result = self.client.wait(record["operationId"])
        except ModelingError as error:
            unknown = error.details.get("outcome") == "unknown" or error.code in {"outcome_unknown", "wait_timeout", "result_expired", "operation_not_found"}
            record.update(state="outcome_unknown" if unknown else "failed", error=error.to_dict())
            self.journal.update(path, record)
            error.details["journalPath"] = str(path)
            raise
        record.update(state="succeeded", result=result)
        self.journal.update(path, record)
        self.last_control = {**deepcopy(result), "requestId": request_id, "journalPath": str(path)}
        return self.last_control

    def save(self, name, *, overwrite=False):
        """Native save with explicit overwrite intent and a durable operation ID."""
        label(name, "save name")
        if type(overwrite) is not bool:
            raise ModelingError("invalid_input", "overwrite must be boolean.")
        baseline = self.identity
        result = self._control("save", {"name": name, "overwrite": overwrite})
        snapshot = self.client.call("craft.snapshot")
        if not result.get("saved") or not _same(snapshot["identity"], result["identity"]):
            raise ModelingError("stale_evidence", "Save completed but current state differs from its receipt.", {"journalPath": result["journalPath"]})
        self._snapshot = snapshot
        if self.project:
            self.project.after_execution(snapshot, self.client.instance["instanceId"], baseline, result, {})
        return result

    def reopen(self, craft_id, *, discard_current=False):
        """Load an exact native saved ID, returning an explicitly new Session.

        Persistent names are retained as unbound evidence until rebind() is
        called. Old PartRefs and checkpoints continue to refer to the old epoch.
        """
        if not isinstance(craft_id, str) or not craft_id.strip() or discard_current is not True:
            raise ModelingError("discard_confirmation_required", "Provide an exact saved craft ID and discard_current=True after saving desired edits.")
        result = self._control("load", {"craftId": craft_id, "discardCurrent": True})
        restored = Session(self.client, journal_dir=self.journal.directory,
                           project_path=None if self.project is None else self.project.path)
        if not _same(restored.identity, result["identity"]):
            raise ModelingError("stale_evidence", "Loaded craft changed before new-session attachment.", {"journalPath": result["journalPath"]})
        restored.last_control = result
        return restored

    def execute_sequence(self, builders, *, name="modeling sequence"):
        """Execute bounded fresh-plan factories, stopping at the first failure.

        Each builder(session, prior_receipts) returns one Plan. This call is the
        explicit write intent; each native batch is previewed before submission.
        The sequence is not atomic across batches. Its receipt lists completed
        boundaries and unknown operations without whole-craft rollback.
        """
        from .workflows import execute_sequence
        return execute_sequence(self, builders, name=name)

    def task(self,path,**contract):
        from .task import ModelingTask
        return ModelingTask(self,path,**contract)

    def modeling(self,directory):
        """The same semantic workspace used by sp2model model commands."""
        from .modeling import ModelingWorkspace
        return ModelingWorkspace(directory,self)

    def resume_sequence(self, path):
        """Poll an already submitted sequence boundary; never invoke a builder."""
        from .workflows import resume_sequence
        return resume_sequence(self, path)

    def continue_sequence(self, path, builders):
        """Explicitly execute remaining fresh builders after a known boundary."""
        from .workflows import continue_sequence
        return continue_sequence(self, path, builders)

    def capture(self, *, views, parts=None, width=1024, height=768, cutting_outlines_visible=None):
        args = {"craftSessionId": self._session_id, "expectedRevision": self.identity["revision"], "views": views,
                "resolution": {"width": width, "height": height}}
        if parts is not None:
            args["focusPartIds"] = [self._resolve_ref(p) for p in parts]
        if cutting_outlines_visible is not None:
            if type(cutting_outlines_visible) is not bool:raise ModelingError('invalid_input','cutting_outlines_visible must be boolean or omitted')
            args['cuttingOutlinesVisible']=cutting_outlines_visible
        return self.client.call("designer.capture", args)

    def mesh(self, parts, *, frame=None, vertex_attributes=None):
        from .verification import native_mesh_data
        from .mesh import MeshEvidence
        if isinstance(parts,PartRef):parts=[parts]
        ids=[self._resolve_ref(part) for part in parts]
        if not ids or len(ids)!=len(set(ids)):raise ModelingError("invalid_selector","Select a nonempty collection of distinct native parts")
        if frame is not None:self._validate_frame(frame)
        sample,data=native_mesh_data(self,ids,self.identity,vertex_attributes=vertex_attributes)
        return MeshEvidence(sample,data,frame=frame,_artifact_verified=True)

    def section(self, parts, origin, normal, *, frame=None, weld_tolerance_m=1e-6):
        return self.mesh(parts,frame=frame).section(origin,normal,weld_tolerance_m=weld_tolerance_m)

    def verify(self, receipt):
        from .verification import verify_receipt
        return verify_receipt(self, receipt)

    def check(self, plan):
        """Measure current objects against an expectation-only plan. No writes.

        Useful after explicit rebind or inspection. Plans containing mutations
        must be previewed/applied; check never silently ignores their actions.
        """
        from .verification import verify_plan
        return verify_plan(self, plan)
