"""SP2 Build Assistant CLI. Python standard library only; UTF-8 JSON interface."""
from __future__ import annotations

import time
_MODULE_STARTED = time.monotonic()

import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
import uuid
import reference_cli

def trace_timing(stage, started):
    """Opt-in local diagnostics on stderr; never include discovery tokens or bodies."""
    if os.environ.get("SP2BUILD_TRACE_TIMINGS") == "1":
        print(json.dumps({"stage": stage, "milliseconds": round((time.monotonic()-started)*1000, 3)}), file=sys.stderr)

VERSION = "0.7.7a1"
READS = {
    "craft.status": {},
    "native.state":{"id":"integer"}, "mechanical.get":{"id":"integer"},
    "wing.stations":{"id":"integer","positions":"array"},
    "airfoils.describe":{"name":"string","reynolds":"number","mach":"number","anglesDegrees":"array"},
    "model.dependencies":{"craftSessionId":"string","expectedRevision":"integer","partIds":"array"},
    "logic.dependencies":{"variable":"string"},
    "parts.query": {"partIds":"array", "name":"string", "type":"string", "fields":"array", "offset":"integer", "limit":"integer", "craftSessionId":"string", "expectedRevision":"integer"},
    "scope.get": {"scopeId":"string", "craftSessionId":"string"},
    "designer.crafts": {"query":"string", "offset":"integer", "limit":"integer"},
    "appearance.get": {"partIds":"array", "offset":"integer", "limit":"integer"},
    "resources.list": {"category":"string", "partId":"integer", "offset":"integer", "limit":"integer"},
    "groups.resolve": {"craftSessionId":"string", "expectedRevision":"integer", "selector":"object"},
    "decal.pose.get": {"id":"integer"},
    **{name: {"craftSessionId":"string", "expectedRevision":"integer", "partIds":"array", "partIdsA":"array", "partIdsB":"array", "frame":"object", "plane":"object", "region":"object", "sampleSpacingMetres":"number", "limit":"integer", "includeHidden":"boolean", "export":"boolean", "exportMeshes":"boolean", "source":"string", "vertexAttributes":"array"} for name in ("geometry.measure", "geometry.section", "geometry.seam", "geometry.symmetry")},
    "craft.diff": {"checkpointId": "string", "limit": "integer"},
    "properties.describe": {"id":"integer", "templateId":"string", "type":"string", "family":"string", "query":"string", "fields":"array", "offset":"integer", "limit":"integer"},
    "properties.get": {"id":"integer", "family":"string", "query":"string", "fields":"array", "offset":"integer", "limit":"integer"},
    "designer.capture": {"craftSessionId":"string", "expectedRevision":"integer", "views":"array", "resolution":"object", "focusPartIds":"array", "cuttingOutlinesVisible":"boolean"},
    "craft.centers": {"craftSessionId":"string", "expectedRevision":"integer", "detail":"string", "metric":"string", "focus":"string", "focusSelector":"object", "limit":"integer", "offset":"integer", "frame":"object", "images":"boolean", "resolution":"object", "baseline":"string"},
    "visual.resolve": {"craftSessionId":"string", "expectedRevision":"integer", "groups":"array", "maxParts":"integer"},
    "visual.capture": {"craftSessionId":"string", "expectedRevision":"integer", "groups":"array", "maxParts":"integer", "views":"array", "resolution":"object", "frame":"object", "details":"string", "includeHidden":"boolean", "overlays":"object"},
    "visual.pick": {"captureId":"string", "view":"string", "x":"integer", "y":"integer"},
    "capabilities": {}, "designer.status": {},
    "designer.selection": {}, "parts.geometry": {"id": "integer"},
    "designer.raycast": {"origin": "array", "direction": "array", "distance": "number"},
    "shape.get": {"id": "integer"}, "shape.schema": {"family": "string"}, "symmetry.get": {"part": "integer"},
    "craft.snapshot": {"includeXml": "boolean"},
    "parts.list": {"type": "string", "query": "string", "offset": "integer", "limit": "integer"},
    "parts.get": {"id": "integer"}, "parts.assembly": {"id": "integer", "symmetric": "boolean"}, "connections.list": {"view": "string"}, "connections.points": {"part": "integer"},
    "spatial.query": {"partA": "integer", "partB": "integer"},
    "catalog.categories": {}, "catalog.subcategories": {"category": "string"},
    "catalog.list": {"category": "string", "subcategory": "string", "query": "string", "offset": "integer", "limit": "integer"},
    "catalog.search": {"query": "string", "offset": "integer", "limit": "integer"},
    "catalog.get": {"id": "string"}, "catalog.schema": {"id": "string", "type": "string"},
    "catalog.export": {}, "outputs.list": {"part": "integer", "view": "string"}, "variables.list": {"view": "string"},
    "funky.list": {}, "funky.describe": {"name": "string"}, "funky.validate": {"expression": "string", "type": "string","partId":"integer","controllerIndex":"integer","field":"string"},
    "craft.history": {}, "craft.checkpoint.list": {}, "craft.checkpoint.get": {"id": "string"},
    "batch.preview": {"craftSessionId": "string", "expectedRevision": "integer", "operations": "array","modelScope":"object"},
}
WRITES = {
    "scope.capture": {"craftSessionId":"string", "expectedRevision":"integer", "partIds":"array", "boundaryPartIds":"array", "ownerId":"string", "spatialMarginMetres":"number"},
    "scope.release": {"scopeId":"string", "craftSessionId":"string"},
    "scoped.batch.apply": {"craftSessionId":"string", "scopeId":"string", "operations":"array", "chunkSize":"integer"},
    "designer.control": {"action":"string", "expectedScene":"string", "craftSessionId":"string", "expectedRevision":"integer", "expectedCraftName":"string", "discardCurrent":"boolean", "craftId":"string", "partId":"integer", "clear":"boolean", "name":"string", "overwrite":"boolean", "expectedSavedName":"string", "expectedSavedModifiedUtc":"string"},
    "acceptance.native": {"craftSessionId":"string", "expectedRevision":"integer", "expectedCraftName":"string", "action":"string", "partId":"integer", "modifierType":"string", "modifierIndex":"integer", "member":"string", "element":"string", "attribute":"string", "value":["boolean","string","number","array","object"]},
    "batch.apply": {"craftSessionId": "string", "expectedRevision": "integer", "operations": "array","modelScope":"object"},
    "craft.undo": {"craftSessionId": "string", "expectedRevision": "integer", "expectedHeadHash": "string"},
    "craft.rollback": {"craftSessionId": "string", "expectedRevision": "integer", "checkpointId": "string"},
    "craft.checkpoint.create": {"craftSessionId": "string", "expectedRevision": "integer", "name": "string","pinned":"boolean"},
    "craft.checkpoint.prune":{"craftSessionId":"string","expectedRevision":"integer","ids":"array","includePinned":"boolean"},
}
OP_SCHEMAS = {
    "native.state":{"partId":["integer","string"],"changes":"array"},
    "part.retype":{"partId":["integer","string"],"partType":"string","acceptConnectionLoss":"boolean","temporaryId":"string"},
    "mechanical.update":{"partId":["integer","string"],"startWorld":"array","endWorld":"array","radiusMultiplier":"number","bootA":"boolean","bootB":"boolean"},
    "appearance.set": {"mode":"string", "materialId":"integer", "partIds":"array", "slots":"array", "patch":"object"},
    "transform.apply": {"partIds":"array", "groupId":"string", "frame":"object", "mode":"string", "translation":"array", "position":"array", "rotationQuaternion":"array", "pivot":"array", "anchorPartId":["integer","string"], "symmetric":"boolean"},
    "transform.align": {"partIds":"array", "groupId":"string", "sourcePartId":["integer","string"], "sourcePointId":"integer", "targetPartId":["integer","string"], "targetPointId":"integer", "offset":"array", "axis":"string", "symmetric":"boolean"},
    "decal.pose.set": {"partId":["integer","string"], "frame":"object", "position":"array", "rotationQuaternion":"array", "symmetric":"boolean"},
    "properties.set": {"partId":["integer","string"], "patch":"object", "symmetric":"boolean"},
    "part.add": {"templateId": "string", "temporaryId": "string", "position": "array", "rotation": "array", "rootOnly": "boolean"},
    "part.clone": {"partIds": "array", "temporaryIds": "array"},
    "part.mirror": {"partIds": "array", "temporaryIds": "array", "linked":"boolean"},
    "connection.auto": {"partA":"integer","partB":"integer","symmetric":"boolean"},
    "hole.create": {"templateId":"string", "temporaryId":"string", "targetPartIds":"array", "position":"array", "rotationQuaternion":"array", "size":"array"},
    "hole.update": {"partId":"integer", "targetPartIds":"array", "position":"array", "rotationQuaternion":"array", "size":"array"},
    "part.update": {"partId": ["integer", "string"], "changes": "array", "symmetric": "boolean"},
    "craft.refresh": {},
    "shape.update": {"partId": ["integer", "string"], "patch": "object", "symmetric": "boolean"},
    "wing.control.add": {"wingPartId": ["integer", "string"], "style": "string", "patch": "object", "temporaryId": "string"},
    "fuselage.match": {"partId": ["integer", "string"], "sectionIndex": "integer"},
    "symmetry.link": {"partIds": "array"}, "symmetry.unlink": {"partId": ["integer", "string"]},
    "symmetry.create": {"partId": ["integer", "string"]}, "symmetry.enable": {"partId": ["integer", "string"], "enabled": "boolean"},
    "part.delete": {"partId": ["integer", "string"], "symmetric": "boolean", "assembly": "boolean"},
    "connection.connect": {"partA": ["integer", "string"], "partB": ["integer", "string"], "attachPointA": "integer", "attachPointB": "integer", "symmetric": "boolean"},
    "connection.disconnect": {"partA": ["integer", "string"], "partB": ["integer", "string"], "symmetric": "boolean"},
    "variable.add": {"variable": "string", "function": "string", "priority": "integer", "activator": "string"},
    "variable.update": {"index": "integer", "variable": "string", "function": "string", "priority": "integer", "activator": "string"},
    "variable.delete": {"index": "integer"}, "variable.reorder": {"order": "array"},
    "output.bind": {"partId": ["integer", "string"], "modifier": "string", "modifierIndex":"integer", "outputId": "string", "variable": "string", "priority": "integer", "activator": "string"},
    "output.update": {"partId": ["integer", "string"], "modifier": "string", "modifierIndex":"integer", "outputId": "string", "variable": "string", "priority": "integer", "activator": "string"},
    "output.unbind": {"partId": ["integer", "string"], "modifier": "string", "modifierIndex":"integer", "outputId": "string"},
}
ALIASES = {"parts.add": "part.add", "parts.update": "part.update", "parts.delete": "part.delete",
    "connections.connect": "connection.connect", "connections.disconnect": "connection.disconnect",
    "variables.add": "variable.add", "variables.update": "variable.update", "variables.delete": "variable.delete", "variables.reorder": "variable.reorder",
    "outputs.bind": "output.bind", "outputs.update": "output.update", "outputs.unbind": "output.unbind"}
ALIASES.update({k: k for k in ("craft.refresh", "shape.update", "wing.control.add", "fuselage.match", "symmetry.link", "symmetry.unlink", "symmetry.create", "symmetry.enable")})
ALIASES["properties.set"] = "properties.set"
ALIASES.update({name:name for name in ('part.retype','mechanical.update')})
ALIASES.update({name:name for name in ("appearance.set", "transform.apply", "transform.align", "decal.pose.set")})
LOCAL = {"commands.list", "commands.schema", "instances.list", "version", "skill.path", "knowledge.catalog", "knowledge.funky", "knowledge.complex"}
LOCAL |= reference_cli.COMMANDS
KNOWLEDGE_COMMANDS = {'knowledge.status','knowledge.search','knowledge.get','knowledge.export','knowledge.refresh'}
LOCAL |= KNOWLEDGE_COMMANDS

def knowledge_module():
    # Source-tree compatibility CLI uses the same SDK implementation; packaged
    # route1 launchers already execute sp2model.command_host directly.
    sdk = str(Path(__file__).resolve().parents[1] / 'sdk')
    if sdk not in sys.path: sys.path.insert(0, sdk)
    from sp2model import knowledge
    return knowledge
TERMINAL = {"succeeded", "failed", "cancelled", "result_expired"}
EXIT_CODES = {"invalid_input": 2, "unsupported_command": 2, "bridge_not_running": 3,
              "multiple_instances": 3, "bridge_unreachable": 3, "session_conflict": 4,
              "revision_conflict": 4, "request_id_conflict": 4, "history_conflict": 4, "scope_conflict":4,
              "wait_timeout": 8, "operation_not_found": 9}

class CliError(Exception):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code, self.details = code, details

def ok(data):
    return {"success": True, "schemaVersion": "1", "data": data}

def parse(argv: list[str]):
    words, options, missing_values = [], {}, []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            options["help"] = True
        elif arg.startswith("--"):
            key = arg[2:]
            if key in ("json", "async", "include-xml", "images"):
                options[key] = True
            else:
                if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                    missing_values.append(key)
                else:
                    i += 1
                    options[key] = argv[i]
        else:
            words.append(arg)
        i += 1
    command = ".".join(words)
    if missing_values:
        # Do not imply that an invented option exists simply because it has no
        # value. Resolve the complete command before reporting its missing flag.
        common = {"input", "output", "timeout", "instance", "request-id"}
        if command in ("visual.capture", "designer.capture", "craft.centers", "operation.wait", "operation.result") or command.startswith("geometry."):
            common.add("output-dir")
        fields = schema(command).get("properties", {}) if command else {}
        for key in missing_values:
            camel = key.split("-")[0] + "".join(x.title() for x in key.split("-")[1:])
            if key not in common and camel not in fields:
                raise CliError("invalid_input", f"Unknown option --{key} for {command or 'global help'}; use commands schema")
            raise CliError("invalid_input", f"--{key} requires a value")
    return command, options

def schema(command: str, operation_only=False):
    if command in KNOWLEDGE_COMMANDS:
        return knowledge_module().input_schema(command)
    if command in reference_cli.COMMANDS:
        return reference_cli.input_schema(command)
    if command == "designer.control":
        from designer_control import input_schema
        return input_schema()
    if command == "acceptance.native":
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from acceptance_contracts import input_schema
        return input_schema()
    if command == "designer.capture":
        return visual_module().designer_schema()
    if command == "craft.centers":
        return centers_module().schema()
    if command in LOCAL or command.startswith("operation."):
        fields = {"commands.schema": {"command": "string", "operation": "string"},
                  "knowledge.complex": {"family": "string"}}.get(command, {"id": "string"} if command.startswith("operation.") else {})
        result = {"type": "object", "properties": {k: {"type": v} for k, v in fields.items()}, "additionalProperties": False}
        if command.startswith("operation."):
            result["required"] = ["id"]
        if command == "commands.schema":
            result["oneOf"] = [{"required": ["command"]}, {"required": ["operation"]}]
        return result
    if command.startswith("visual."):
        if command not in READS:
            raise CliError("unsupported_command", f"No request schema for {command}")
        return visual_module().schema(command)
    if command in ALIASES and not operation_only:
        operation = schema(ALIASES[command], operation_only=True)
        operation["required"] = [k for k in operation["required"] if k != "kind"]
        return {"type": "object", "properties": {"craftSessionId": {"type": "string"}, "expectedRevision": {"type": "integer"},
            "requestId": {"type": "string"}, "operation": operation},
            "required": ["craftSessionId", "expectedRevision", "operation"], "additionalProperties": False}
    operation_contract=command in OP_SCHEMAS and (operation_only or command not in READS)
    if operation_contract:
        fields = {"kind": "string", **OP_SCHEMAS[command]}
    else:
        fields = {**READS, **WRITES}.get(command)
    if fields is None:
        raise CliError("unsupported_command", f"No request schema for {command}")
    properties = {k: {"type": v} for k, v in fields.items()}
    if "view" in properties:
        properties["view"].update(enum=["legacy", "structured"], default="legacy", description="DLL 0.3.2+: structured returns typed rows and shared sources[].modifiers, omitting raw XML and output-less parts. Default legacy preserves the prior response shape; inspect data.view.")
    if command == "variable.reorder":
        properties["order"].update(items={"type": "integer", "minimum": 0}, uniqueItems=True,
            description="List ALL old zero-based setter indices in the desired NEW sequence, each exactly once. For three setters, [2,0,1] moves old index 2 first. This is not a list of destination positions or swap pairs. Re-query indices after edits.", examples=[[2, 0, 1]])
    for key in ("partId", "wingPartId", "partA", "partB", "sourcePartId", "targetPartId", "anchorPartId"):
        if operation_contract and key in properties:
            properties[key]["type"]=["integer","string"]
            properties[key]["description"] = "Current numeric ID or a live temporaryId from an earlier operation. A deleted numeric ID stays invalid within this batch even if recycled."
    if operation_contract:
        for key in ("partIds","targetPartIds"):
            if key in properties:properties[key].update(minItems=1,maxItems=2048,uniqueItems=True,items={"type":["integer","string"]})
    if "temporaryId" in properties:
        properties["temporaryId"].update(minLength=1, description="Unique for the whole batch, including previously deleted temporary bindings.")
    if command in WRITES:
        properties["requestId"] = {"type": "string", "minLength": 1, "description": "Required in CLI input unless supplied with --request-id; forwarded in the bridge request envelope."}
    required = {
        "scope.capture":["craftSessionId","expectedRevision","partIds"],
        "scope.get":["scopeId"], "scope.release":["scopeId"],
        "scoped.batch.apply":["craftSessionId","scopeId","operations"],
        "craft.diff":["checkpointId"], "resources.list":["category"], "decal.pose.get":["id"],
        "groups.resolve":["craftSessionId","expectedRevision","selector"],
        "appearance.set":["kind","mode","materialId"], "transform.apply":["kind","mode"],
        "transform.align":["kind","sourcePartId","targetPartId"],
        "part.clone":["kind","partIds","temporaryIds"],
        "part.mirror":["kind","partIds","temporaryIds","linked"],
        "connection.auto":["kind","partA","partB"],
        "hole.create":["kind","templateId","temporaryId","targetPartIds","size","position","rotationQuaternion"],
        "hole.update":["kind","partId"],
        "decal.pose.set":["kind","partId","position","rotationQuaternion"],
        "geometry.measure":["craftSessionId","expectedRevision","partIdsA","partIdsB"],
        "geometry.section":["craftSessionId","expectedRevision","partIds","plane"],
        "geometry.seam":["craftSessionId","expectedRevision","partIdsA","partIdsB","plane","region"],
        "geometry.symmetry":["craftSessionId","expectedRevision","partIdsA","partIdsB","plane"],
        "properties.get": ["id"], "properties.set": ["kind", "partId", "patch"],
        "batch.apply": ["craftSessionId", "expectedRevision", "operations"],
        "batch.preview": ["craftSessionId", "expectedRevision", "operations"],
        "craft.undo": ["craftSessionId", "expectedRevision"],
        "craft.rollback": ["craftSessionId", "expectedRevision", "checkpointId"],
        "craft.checkpoint.create": ["craftSessionId", "expectedRevision"],
        "parts.get": ["id"], "parts.assembly": ["id"], "connections.points": ["part"], "spatial.query": ["partA", "partB"],
        "parts.geometry": ["id"], "shape.get": ["id"], "shape.schema": ["family"], "designer.raycast": ["origin", "direction"],
        "craft.refresh": ["kind"], "shape.update": ["kind", "partId", "patch"],
        "wing.control.add": ["kind", "wingPartId", "style", "patch"], "fuselage.match": ["kind", "partId", "sectionIndex"],
        "symmetry.link": ["kind", "partIds"], "symmetry.unlink": ["kind", "partId"], "symmetry.create": ["kind", "partId"], "symmetry.enable": ["kind", "partId", "enabled"],
        "catalog.get": ["id"], "catalog.subcategories": ["category"], "funky.validate": ["expression"], "funky.describe": ["name"],
        "part.add": ["kind", "templateId"], "part.update": ["kind", "partId", "changes"], "part.delete": ["kind", "partId"],
        "connection.connect": ["kind", "partA", "partB", "attachPointA", "attachPointB"],
        "connection.disconnect": ["kind", "partA", "partB"], "variable.add": ["kind", "variable", "function"],
        "variable.update": ["kind", "index"], "variable.delete": ["kind", "index"], "variable.reorder": ["kind", "order"],
        "output.bind": ["kind", "partId", "modifier", "outputId", "variable"],
        "output.update": ["kind", "partId", "modifier", "outputId"], "output.unbind": ["kind", "partId", "modifier", "outputId"],
    }.get(command, [])
    result = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": properties, "required": required, "additionalProperties": False}
    if operation_contract:properties['kind']['const']=command
    if command == "part.add":
        properties["position"].update(description="Target world position in metres of the template's first part; other parts retain their relative offsets after rotation. Omit to retain the template origin.")
        properties["rotation"].update(description="Unity Euler rotation OFFSET in degrees, applied around the template's first part and composed with each template part's existing rotation. Omitted or [0,0,0] preserves template orientation; this is not an absolute final world rotation.")
        properties["temporaryId"].update(description="Batch-local reference to the first part created by the template. Multi-part templates return all created IDs in actualChanges.partIds.")
        properties["rootOnly"].update(description="Route A plugin option: instantiate only a certified native fuselage or wing template root, omitting the template assembly's other parts and connections. Defaults false.")
    if command == "connection.connect":
        result["description"] = "Creates a native connection, not a general snapping operation. Native modifiers may reshape/reposition parts: a fuselage/cone with autoResize=true can copy its neighbour's section and length and align to it. To preserve manually configured fuselage dimensions, explicitly set shape.update.patch.autoResize=false before connecting, then read back shape and pose."
    if "operations" in properties:
        properties["operations"].update(minItems=1, maxItems=100, items={"oneOf": [schema(kind, operation_only=True) for kind in OP_SCHEMAS]})
    if command == "scope.capture":
        properties["partIds"].update(minItems=1,uniqueItems=True,items={"type":"integer","minimum":0})
        properties["spatialMarginMetres"].update(minimum=0,maximum=10,default=0.02)
        result["description"]="Capture a strict current scope with writable parts, protected boundary/dependencies and shared-state fingerprints. Native attachment, symmetry, cutting and spatial neighbors are guarded separately."
    if command == "scoped.batch.apply":
        properties["chunkSize"].update(minimum=1,maximum=4,default=1)
        allowed=("part.update","shape.update","properties.set","transform.apply","transform.align","decal.pose.set","appearance.set")
        properties["operations"]["items"]={"oneOf":[schema(kind,operation_only=True) for kind in allowed]}
        result["description"]="Fairly interleave atomic in-place chunks, with at least one ordinary editor frame between chunks. Unrelated revisions are accepted; scope/dependency/shared-state conflicts stop subsequent writes. Completed chunks are retained on later failure/cancel; no whole-task rollback. Topology and shared palette edits require a separate strict batch. Native synchronous rebuilds cannot be preempted."
    if "kind" in properties:
        properties["kind"]["const"] = command
    if command == "part.update":
        result["description"] = "Edits native attributes at Part-relative paths. DLL 0.4.8+ also validates the InputController.State serializer fields omitted by native metadata: input, activationGroup, invert, min, max, zeroOnDeactivate and invertType. Discover these in catalog.schema parts[].toolEditableExtensions or designer.status.inputControllerEditing; repeated controllers use InputController.State[index]."
        properties["changes"]["items"] = {"type": "object", "required": ["attribute", "value"], "properties": {
            "path": {"type": "string"}, "attribute": {"type": "string"}, "value": {"type": ["string", "number", "boolean", "array", "null"]}}, "additionalProperties": False}
    if command == "catalog.schema":
        result["oneOf"] = [{"required": ["id"]}, {"required": ["type"]}]
    if command == "properties.describe":
        result["oneOf"] = [{"required":["id"]},{"required":["templateId"]},{"required":["type"]}]
    if command.startswith("properties."):
        if "fields" in properties:
            properties["fields"].update(items={"type":"string"}, uniqueItems=True)
            properties["offset"]["minimum"] = 0
            properties["limit"].update(minimum=1,maximum=1000)
        if command == "properties.set":
            properties["patch"].update(minProperties=1,maxProperties=100,description="propertyId to typed JSON value map. Discover IDs and effective constraints with properties.describe. Validate every member before the first setter; prerequisite changes belong in an earlier operation.")
    if command in ("shape.update", "wing.control.add", "shape.schema"):
        result = shape_contracts_module().enrich(command, result)
    if command.startswith(("appearance.","transform.","geometry.","resources.","decal.pose.")):
        import importlib.util
        spec=importlib.util.spec_from_file_location("sp2build_precision_contracts",Path(__file__).with_name("precision_contracts.py"))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.enrich(command,result)
    if command in ('native.state','part.retype','mechanical.get','mechanical.update','wing.stations','airfoils.describe','parts.query','model.dependencies','craft.checkpoint.prune','batch.preview','batch.apply'):
        from modeling_contracts import enrich
        result=enrich(command,result)
    return result

def is_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)

def instance_responds(item):
    """Authenticate discovery without enqueueing a command or reading a craft.

    A live PID and open port are insufficient: Windows reuses old PIDs and the
    bridge reuses ports. Old crash records otherwise identify an unrelated
    process as a second game. All shipped bridges authenticate before lookup.
    """
    request = Request(item["baseUrl"] + "v1/operations/discovery-" + uuid.uuid4().hex,
                      headers={"X-SP2Build-Token": item["token"]}, method="GET")
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=1) as response:
            response.read(8192)
    except HTTPError as exc:
        try:
            data = json.loads(exc.read(8192).decode("utf-8"))
            return exc.code == 400 and data.get("success") is False and data.get("error", {}).get("code") == "operation_not_found"
        except (ValueError, UnicodeError):
            return False
    except (URLError, OSError):
        return False
    return False


def instances(selected=None):
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SP2BuildAssistant" / "instances"
    result = []
    for path in directory.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8-sig"))
            if selected is not None and str(item.get("pid")) != str(selected) and item.get("instanceId") != selected:
                continue
            if not is_running(int(item["pid"])):
                continue
            if not item["baseUrl"].startswith("http://127.0.0.1:"):
                continue
            port = int(item["baseUrl"].split(":")[-1].rstrip("/"))
            if 1 <= port <= 65535 and instance_responds(item):
                result.append(item)
        except (ValueError, OSError, KeyError):
            continue
    return result

def select_instance(options):
    started = time.monotonic()
    candidates = instances(options.get("instance"))
    trace_timing("instance_discovery", started)
    if "instance" in options:
        candidates = [x for x in candidates if str(x["pid"]) == options["instance"] or x["instanceId"] == options["instance"]]
    if not candidates:
        raise CliError("bridge_not_running", "No running SP2 Build Assistant DLL found. Start the game after DLL installation.")
    if len(candidates) != 1:
        raise CliError("multiple_instances", "Use --instance PID from instances list")
    return candidates[0]

def http(instance, route, payload=None, method="GET"):
    started = time.monotonic()
    request = Request(instance["baseUrl"] + route.lstrip("/"),
        data=None if payload is None else json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "X-SP2Build-Token": instance["token"]}, method=method)
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
            result = json.load(response)
    except HTTPError as exc:
        try:
            result = json.loads(exc.read().decode("utf-8"))
        except (ValueError, UnicodeError):
            raise CliError("bridge_unreachable", f"HTTP {exc.code} without structured response") from exc
    except (URLError, OSError) as exc:
        raise CliError("bridge_unreachable", str(exc)) from exc
    trace_timing("http_"+method, started)
    if not result.get("success"):
        error = result.get("error", {})
        raise CliError(error.get("code", "execution_failed"), error.get("message", "Bridge request failed"))
    return result["data"]

def wait(instance, operation_id: str, timeout: float):
    deadline = time.monotonic() + timeout
    while True:
        job = http(instance, f"v1/operations/{operation_id}")
        if job["state"] in TERMINAL:
            if job["result"] is None:
                raise CliError("result_expired", "Result payload is no longer retained. The operation may have executed; inspect current state and do not resubmit with a new requestId.",
                               operationId=operation_id, instancePid=instance["pid"], completionState=job.get("completionState"),
                               resultRetention=job.get("resultRetention"))
            result = job["result"]
            result["operationId"] = operation_id
            result["instancePid"] = instance["pid"]
            return result
        if time.monotonic() >= deadline:
            raise CliError("wait_timeout", "Task is still active. Query operation status/wait; do not blindly retry.", operationId=operation_id, state=job["state"], instancePid=instance["pid"])
        time.sleep(0.05)

def load_args(command, options):
    args = {}
    if "input" in options:
        raw = sys.stdin.buffer.read() if options["input"] == "-" else Path(options["input"]).read_bytes()
        args = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(args, dict):
            raise CliError("invalid_input", "Input must be a JSON object")
    ignored = {"input", "output", "json", "async", "timeout", "instance", "help", "request-id", "command"}
    if command in ("visual.capture", "designer.capture", "craft.centers") or command.startswith("geometry."):
        ignored.add("output-dir")
    fields = ({name: value.get('type') for name,value in schema(command)['properties'].items()}
              if command in reference_cli.build_review_cli.COMMANDS or command in KNOWLEDGE_COMMANDS else
              reference_cli.FIELDS if command in reference_cli.COMMANDS else {**READS, **WRITES}.get(command, {}))
    for key, value in options.items():
        if key in ignored:
            continue
        camel = key.split("-")[0] + "".join(x.title() for x in key.split("-")[1:])
        if camel not in fields:
            raise CliError("invalid_input", f"Unknown option --{key} for {command}; use commands schema")
        if fields[camel] == "integer":
            value = int(value)
        elif isinstance(fields[camel], list):
            value = json.loads(value)
        elif fields[camel] in ("array", "object"):
            value = json.loads(value)
        elif fields[camel] == "number":
            value = float(value)
        elif fields[camel] == "boolean" and not isinstance(value, bool):
            if str(value).lower() not in ("true", "false"):
                raise CliError("invalid_input", f"--{key} requires true or false")
            value = str(value).lower() == "true"
        args[camel] = value
    allowed = set(fields) | {"requestId"}
    unknown = set(args) - allowed
    if unknown:
        raise CliError("invalid_input", "Unknown input keys: " + ", ".join(sorted(unknown)))
    for key in schema(command).get("required", []):
        if key == "requestId" and options.get("request-id"):
            continue
        if key not in args:
            raise CliError("invalid_input", f"{key} is required")
    return args

def visual_module():
    # Resolve only the sibling installed module; no PATH/import-cache dependency.
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp2build_visual", Path(__file__).with_name("visual.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def centers_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp2build_centers", Path(__file__).with_name("centers.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shape_contracts_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp2build_shape_contracts", Path(__file__).with_name("shape_contracts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contracts_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp2build_contracts", Path(__file__).with_name("contracts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command_names():
    return sorted(set(READS) | set(WRITES) | LOCAL | set(ALIASES) | {"operation.status", "operation.wait", "operation.result", "operation.cancel"})


def help_data(command):
    names = command_names()
    matches = [name for name in names if name.startswith(command + ".")]
    if command and command not in names and not matches:
        raise CliError("unsupported_command", command + "; use sp2build commands list")
    result = {
        "usage": "sp2build <group> <command> [--input FILE|-] [--output FILE] [--instance PID|ID] [--timeout SECONDS] [--async] [--json] [--help]",
        "globalOptions": {
            "--input": "Read a UTF-8 JSON request from FILE, or stdin with -. Supported by bridge commands and required for shortcut writes; local discovery and operation.* use flags.",
            "--output": "Save a returned result as JSON to FILE; stdout contains path, sha256 and resultSuccess. Early CLI failures may only return an error on stdout without creating a file.",
            "--instance": "Select a running bridge by PID or instanceId from instances list; needed if multiple games run.",
            "--timeout": "Maximum synchronous wait in seconds, default 20, range (0,600]. A timeout does not cancel the operation.",
            "--async": "For submitted bridge commands, return job acceptance instead of waiting. Retrieve the final result with operation wait/result.",
            "--request-id": "Request deduplication key. Required for writes unless requestId is present in the input JSON.",
            "--json": "Accepted for explicitness; all output is UTF-8 JSON even without this flag.",
            "--help": "Show offline help for this command or group, without contacting the game. -h is equivalent."
        },
        "contextOptions": {"--output-dir": {"commands": ["visual.capture", "designer.capture", "craft.centers", "geometry.measure", "geometry.section", "geometry.seam", "geometry.symmetry", "operation.wait", "operation.result"],
            "description": "Root directory for downloaded visual artifacts, default ~/.sp2build/captures. Applies when the result contains a capture; each capture gets its own subdirectory."}},
        "examples": ["sp2build parts get --help", "sp2build visual capture --help", "sp2build commands schema --command parts.get", "sp2build commands schema --operation connection.connect"],
        "target": "Part editing targets the current open designer aircraft. designer control accepts native saved-craft IDs for load and relative save names for save; arbitrary filesystem paths are not accepted."
    }
    if not command or command not in names:
        result["commands"] = matches if command else names
        return result
    request = schema(command)
    shortcut = command in ALIASES
    result.update(command=command, entityKind="command", operationKind=ALIASES.get(command),
                  invocation="sp2build " + command.replace(".", " "),
                  schemaQuery="sp2build commands schema --command " + command,
                  inputMode="guarded_operation_file" if shortcut else "flags_or_json_file" if command in reference_cli.COMMANDS else "flags_only" if command in LOCAL or command.startswith("operation.") else "flags_or_json_file",
                  requiredInputFields=request.get("required", []), arguments=[])
    for name, field in request.get("properties", {}).items():
        if shortcut or name == "requestId":
            continue
        flag = "--" + "".join("-" + char.lower() if char.isupper() else char for char in name)
        item = {"flag": flag, "field": name, "required": name in request.get("required", [])}
        item.update({key: field[key] for key in ("type", "enum", "default", "description") if key in field})
        if field.get("type") in ("array", "object") or "oneOf" in field:
            item["encoding"] = "JSON value; prefer --input for complex payloads."
        if flag in ("--include-xml", "--images"):
            item["encoding"] = "Presence flag; omit it for false, or use includeXml in input JSON."
        result["arguments"].append(item)
    if shortcut:
        result["inputGuidance"] = "Use --input FILE|- containing craftSessionId, expectedRevision, operation, and requestId (or --request-id). Operation fields are nested in operation, not direct CLI flags."
    if command == "commands.schema":
        result["inputGuidance"] = "Supply exactly one of --command CLI_NAME or --operation KIND."
    return result


def visual_download(instance, result, options):
    if result.get("success") and "artifactBase" in result.get("data", {}):
        return visual_module().download(instance, result, options.get("output-dir"), CliError)
    if result.get("success") and isinstance(result.get("data", {}).get("visual"), dict) and "artifactBase" in result["data"]["visual"]:
        wrapped = {"success": True, "data": result["data"]["visual"], "operationId": result.get("operationId")}
        result["data"]["visual"] = visual_module().download(instance, wrapped, options.get("output-dir"), CliError)["data"]
    return result


def _execute(argv):
    command, options = parse(argv)
    if command == "acceptance.host":
        from acceptance_host import execute as host_execute
        return host_execute(options, CliError), options
    if options.get("help") or not command:
        return ok(help_data(command)), options
    if command == "version":
        return ok({"version": VERSION, "python": sys.version.split()[0]}), options
    if command == "commands.list":
        return ok({"commands": command_names(), "operationKinds": OP_SCHEMAS,
                   "commandDetails": [{"name": name, "entityKind": "command", "invocation": "sp2build " + name.replace(".", " "),
                                       "operationKind": ALIASES.get(name), "mutates": name in WRITES or name in ALIASES or name in reference_cli.MUTATES,
                                       "execution": knowledge_module().COMMANDS[name]["execution"] if name in KNOWLEDGE_COMMANDS else "worker" if name in reference_cli.WORKER else "local_with_live" if name in reference_cli.LIVE else "local" if name in LOCAL else "bridge",
                                       "schemaQuery": "sp2build commands schema --command " + name, **({"testOnly": True, "availability": "loaded_dev17_or_later_acceptance_build_and_named_fixture"} if name == "acceptance.native" else {}), **({"minimumPluginVersion": "0.4.0"} if name == "craft.centers" else {})} for name in command_names()],
                   "operationDetails": [{"name": kind, "entityKind": "operation", "cliCommands": [name for name, op in ALIASES.items() if op == kind],
                                         "schemaQuery": "sp2build commands schema --operation " + kind,
                                         "usage": "batch.apply operations[].kind; not a standalone CLI command name"} for kind in OP_SCHEMAS]}), options
    if command == "commands.schema":
        if bool(options.get("command")) == bool(options.get("operation")):
            raise CliError("invalid_input", "Supply exactly one of --command NAME or --operation KIND")
        target = options.get("command") or options["operation"]
        operation = "operation" in options or (target in OP_SCHEMAS and target not in ALIASES and target not in READS)
        contracts = contracts_module()
        if operation:
            if target not in OP_SCHEMAS:
                raise CliError("unsupported_command", "Unknown operation kind: " + target)
            return ok({"command": target, "entityKind": "operation", "operationKind": target, "contractVersion": VERSION,
                       "inputSchema": schema(target, operation_only=True),
                       "resultSchema": contracts.with_defs(contracts.ref("Change")),
                       "cliCommands": [name for name, kind in ALIASES.items() if kind == target],
                       "schemaQuery": "sp2build commands schema --operation " + target,
                       "usage": "Insert into batch.apply operations[]. There is no standalone operation response envelope.",
                       "legacyQuery": "operation" not in options}), options
        if target not in command_names():
            raise CliError("unsupported_command", target)
        output = (knowledge_module().COMMANDS[target]['outputSchema'] if target in KNOWLEDGE_COMMANDS else
                  reference_cli.output_schema(target) if target in reference_cli.COMMANDS else contracts.output_schema(ALIASES.get(target) and "batch.apply" or target))
        return ok({"command": target, "entityKind": "command", "operationKind": ALIASES.get(target), "contractVersion": VERSION,
                   "inputSchema": schema(target), "outputSchema": output,
                   "outputSchemaCoverage": "submitted_command_dependent" if target in ("operation.wait", "operation.result") else "documented_data_fields",
                   "requestId": "Outer envelope field required for writes; put requestId beside craftSessionId in CLI input files.",
                   "compatibility": "Additive fields are optional for older bridges. Structured views require DLL 0.3.2+; craft.centers and centers overlays require loaded DLL 0.4.0+. CLI installation does not reload the DLL.",
                   **contracts.auxiliary_schemas()}), options
    if command == "instances.list":
        return ok({"instances": [{k: v for k, v in x.items() if k != "token"} for x in instances()]}), options
    if command == "skill.path":
        return ok({"path": str(Path(__file__).resolve().parent.parent / "skills" / "sp2-build-assistant")}), options
    if command in reference_cli.COMMANDS:
        payload=load_args(command,options)
        if command in reference_cli.build_review_cli.MUTATES and options.get('request-id'):
            if payload.get('requestId') and payload['requestId'] != options['request-id']:
                raise CliError('invalid_input','requestId and --request-id must agree')
            payload['requestId']=options['request-id']
        def live(native_command,native_payload):
            native_options={k:v for k,v in options.items() if k in ('instance','timeout','output-dir')}
            instance=select_instance(native_options)
            if native_command=='operation.status':
                return ok(http(instance,'v1/operations/'+native_payload['id']))
            body=dict(native_payload)
            request_id=body.pop('requestId',None) or uuid.uuid4().hex
            accepted=http(instance,'v1/operations',{'command':native_command,'args':body,'requestId':request_id},'POST')
            return visual_download(instance,wait(instance,accepted['operationId'],float(options.get('timeout',120))),native_options)
        try:
            data=reference_cli.dispatch(command,payload,live)
            return data if isinstance(data,dict) and 'success' in data else ok(data),options
        except Exception as error:
            if isinstance(error,CliError): raise
            code=getattr(error,'code','invalid_input')
            details=getattr(error,'details',{})
            raise CliError(code,str(error),**(details if isinstance(details,dict) else {})) from error
    if command in KNOWLEDGE_COMMANDS:
        module = knowledge_module()
        from sp2model import Runtime
        runtime = Runtime(instance=options.get('instance'), timeout=float(options.get('timeout',30)))
        try:
            return ok(module.Knowledge(runtime,resource_dir=Path(__file__).resolve().parents[1]/'knowledge/v077').call(command,load_args(command,options))),options
        except Exception as error:
            raise CliError(getattr(error,'code','knowledge_error'),str(error),**getattr(error,'details',{})) from error
    if command in ("knowledge.catalog", "knowledge.funky", "knowledge.complex"):
        name = {"knowledge.catalog": "catalog.json", "knowledge.funky": "funky.json", "knowledge.complex": "complex-parts.json"}[command]
        path = Path(__file__).resolve().parent.parent / "knowledge" / name
        if not path.is_file():
            raise CliError("knowledge_not_installed", "Build/deploy package lacks generated knowledge: " + name)
        knowledge = json.loads(path.read_text(encoding="utf-8-sig"))
        if command == "knowledge.complex" and options.get("family"):
            knowledge["families"] = [f for f in knowledge["families"] if f["id"] == options["family"]]
            if not knowledge["families"]:
                raise CliError("invalid_input", "Unknown complex part family")
        return ok({"dataSource": "versioned_offline_knowledge", "knowledge": knowledge}), options
    timeout = float(options.get("timeout", 20))
    if timeout <= 0 or timeout > 600:
        raise CliError("invalid_input", "timeout must be in (0,600]")
    if command.startswith("operation."):
        operation_id = options.get("id")
        if not operation_id:
            raise CliError("invalid_input", "--id is required")
        if command not in ("operation.wait", "operation.result", "operation.status", "operation.cancel"):
            raise CliError("unsupported_command", command)
        instance = select_instance(options)
        if command in ("operation.wait", "operation.result"):
            return visual_download(instance, wait(instance, operation_id, timeout), options), options
        if command not in ("operation.status", "operation.cancel"):
            raise CliError("unsupported_command", command)
        return ok(http(instance, f"v1/operations/{operation_id}", method="DELETE" if command == "operation.cancel" else "GET")), options
    if command in ALIASES:
        if "input" not in options:
            raise CliError("invalid_input", "Shortcut writes use --input with craftSessionId, expectedRevision, requestId and operation")
        args = json.loads((sys.stdin.buffer.read() if options["input"] == "-" else Path(options["input"]).read_bytes()).decode("utf-8-sig"))
        operation = args.pop("operation", None)
        if not isinstance(operation, dict):
            raise CliError("invalid_input", "operation object is required")
        operation["kind"] = ALIASES[command]
        args["operations"] = [operation]
        command = "batch.apply"
    elif command in READS or command in WRITES:
        args = load_args(command, options)
    else:
        raise CliError("unsupported_command", command)
    instance = select_instance(options)
    if command in ("designer.control", "designer.crafts"):
        probe = http(instance, "v1/operations", {"command":"designer.status", "args":{}, "requestId":uuid.uuid4().hex}, "POST")
        available = wait(instance, probe["operationId"], timeout)
        if not available.get("success") or not available.get("data", {}).get("designerControl", {}).get("available"):
            raise CliError("unsupported_bridge_feature", "Native scene control requires a loaded DLL 0.5.0+. Installing the CLI alone does not reload the game.")
        if command == "designer.control" and args.get("action") not in available["data"]["designerControl"].get("actions", []):
            raise CliError("unsupported_bridge_feature", "This control action is not supported by the loaded DLL. save/new require DLL 0.5.1+; restart after deployment.")
    if command == "acceptance.native":
        probe = http(instance, "v1/operations", {"command":"designer.status", "args":{}, "requestId":uuid.uuid4().hex}, "POST")
        available = wait(instance, probe["operationId"], timeout)
        if not available.get("success") or not available.get("data", {}).get("acceptanceNative", {}).get("available"):
            raise CliError("acceptance_build_required", "This test-only command requires a loaded dev17+ acceptance DLL. It is disabled in distribution builds; deploying a DLL does not reload it.")
    if command.startswith(("properties.", "appearance.", "geometry.", "groups.", "transform.", "resources.", "decal.pose.")) or command == "craft.diff" or (command in ("batch.apply", "batch.preview") and any(isinstance(op, dict) and op.get("kind", "").startswith(("properties.", "appearance.", "transform.", "decal.pose.")) for op in args.get("operations", []))):
        try:
            plugin_version = tuple(int(x) for x in instance.get("pluginVersion", "0.0.0").split(".")[:3])
        except ValueError:
            plugin_version = (0, 0, 0)
        if plugin_version < (0, 5, 0):
            raise CliError("unsupported_bridge_feature", "Effective properties require loaded DLL 0.5.0+. Restart after deployment; an older loaded DLL cannot execute the new operation.")
    if command == "designer.capture":
        try:
            plugin_version = tuple(int(x) for x in instance.get("pluginVersion", "0.0.0").split(".")[:3])
        except ValueError:
            plugin_version = (0, 0, 0)
        if plugin_version < (0, 4, 11):
            raise CliError("unsupported_bridge_feature", "Designer screenshots require loaded DLL 0.4.11+. Deploying files does not reload the running DLL.")
        if any(isinstance(view, dict) and view.get("view") == "fixed" for view in args.get("views", [])) and plugin_version < (0, 5, 0):
            raise CliError("unsupported_bridge_feature", "Fixed camera replay requires loaded DLL 0.5.0+. The running DLL is older than the installed CLI.")
    if command == "craft.centers" or (command == "visual.capture" and isinstance(args.get("overlays"), dict) and args["overlays"].get("centers")):
        try:
            plugin_version = tuple(int(x) for x in instance.get("pluginVersion", "0.0.0").split(".")[:3])
        except ValueError:
            plugin_version = (0, 0, 0)
        if plugin_version < (0, 4, 0):
            raise CliError("unsupported_bridge_feature", "Centers require loaded DLL 0.4.0+. Deploying files does not reload the running DLL.")
        if command == "craft.centers" and "baseline" in args:
            args["baseline"] = centers_module().load_baseline(args["baseline"], CliError)
    input_request_id = args.pop("requestId", None)
    request_id = options.get("request-id") or input_request_id
    if command in WRITES and not request_id:
        raise CliError("invalid_input", "Writes require requestId in the input or --request-id. Retain it to query/retry uncertain outcomes.")
    job = http(instance, "v1/operations", {"command": command, "args": args, "requestId": request_id or uuid.uuid4().hex}, "POST")
    if options.get("async"):
        return ok({**job, "instancePid": instance["pid"]}), options
    result = visual_download(instance, wait(instance, job["operationId"], timeout), options)
    if args.get("view") == "structured" and result.get("success") and result.get("data", {}).get("view") != "structured":
        raise CliError("unsupported_bridge_feature", "Structured views require a loaded DLL 0.3.2+. The bridge returned a legacy result; installing the CLI alone does not reload the DLL.", operationId=job["operationId"], instancePid=instance["pid"])
    return result, options

def execute(argv):
    result, options = _execute(argv)
    if not options.get('help'):
        import build_guidance
        command, _ = parse(argv)
        result = build_guidance.decorate(command, result)
    return result, options


def main(argv=None):
    started = time.monotonic()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    trace_timing("cli_module_import", _MODULE_STARTED)
    options = {}
    try:
        result, options = execute(sys.argv[1:] if argv is None else argv)
    except (CliError, OSError, ValueError, KeyError, TypeError) as exc:
        error = exc if isinstance(exc, CliError) else CliError("invalid_input", str(exc))
        result = {"success": False, "schemaVersion": "1", "error": {"code": error.code, "message": str(error), **error.details}}
        import build_guidance
        try:
            command, _ = parse(sys.argv[1:] if argv is None else argv)
            result = build_guidance.decorate(command, result)
        except (CliError, ValueError):
            pass
    output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if "output" in options:
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
        receipt = ok({"path": str(path), "sha256": hashlib.sha256((output + "\n").encode("utf-8")).hexdigest(), "resultSuccess": result["success"]})
        if 'guidance' in result: receipt['guidance'] = result['guidance']
        output = json.dumps(receipt, ensure_ascii=False)
    trace_timing("cli_main_before_stdout", started)
    print(output)
    return 0 if result["success"] else EXIT_CODES.get(result.get("error", {}).get("code"), 5)

if __name__ == "__main__":
    raise SystemExit(main())
