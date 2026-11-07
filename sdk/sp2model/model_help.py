"""Small, operation-local contracts and aggregated preflight diagnostics.

This module is pure: discovery and validation never connect to a running game.
The semantic host registers its actual schemas; native contracts come from the
same registry used by the public Runtime. It is not a general JSON Schema engine.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import re
from typing import Any

from .errors import ModelingError

DEFAULT_BUDGET = 6000
MAX_BUDGET = 8191
_OPERATIONS: dict[str, dict[str, Any]] = {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _budget(value: int) -> int:
    if type(value) is not int or not 1024 <= value <= MAX_BUDGET:
        raise ModelingError("invalid_input", "max_chars must be an integer from 1024 to 8191.",
                            {"path": "$.max_chars", "minimum": 1024, "maximum": MAX_BUDGET})
    return value


def register_operation(name: str, schema: dict, *, summary: str, example: dict | None = None,
                       units: str = "Lengths in metres; angles in degrees unless a field says otherwise.",
                       frame: str = "Use the task's frozen frame. Native world coordinates require explicit conversion.",
                       next_actions: list[str] | tuple[str, ...] = (),
                       scenes: list[str] | tuple[str, ...] = (), mutates: bool = False) -> None:
    """Register a real public operation; a repeat replaces rather than merges it."""
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", name):
        raise ModelingError("invalid_input", "Operation name is not a public dotted identifier.")
    if not isinstance(schema, dict) or not isinstance(summary, str):
        raise ModelingError("invalid_input", "Operation schema and summary are required.")
    _json(schema)
    if example is not None:
        validate_arguments(example, schema)
    _OPERATIONS[name] = deepcopy({"name": name, "schema": schema, "summary": summary,
        "example": example, "units": units, "frame": frame, "nextActions": list(next_actions),
        "scenes": list(scenes), "mutates": bool(mutates), "source": "semantic"})


def _operation(name: str) -> dict:
    if name in _OPERATIONS:
        return deepcopy(_OPERATIONS[name])
    from . import registry
    contract = registry.contract(name)
    return {"name": name, "schema": contract["inputSchema"],
            "summary": contract.get("description") or contract.get("summary") or registry.public_path(name, contract),
            "example": next(iter(contract["inputSchema"].get("examples", [])), None),
            "units": "Consult operation fields for native units; never infer XML units from a display label.",
            "frame": "Native requests use the current craft session and world frame unless the field declares another frame.",
            "nextActions": [], "scenes": [], "mutates": bool(contract.get("mutates")), "source": "native"}


def _pointer(value: Any, pointer: str) -> Any:
    if pointer in ("", "#", "/"):
        return value
    if pointer.startswith("#"):
        pointer = pointer[1:]
    if not pointer.startswith("/"):
        raise ModelingError("invalid_input", "Help topic must be a JSON pointer into the operation schema.", {"topic": pointer})
    try:
        for token in pointer[1:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            value = value[int(token)] if isinstance(value, list) else value[token]
        return deepcopy(value)
    except (KeyError, IndexError, ValueError, TypeError):
        raise ModelingError("invalid_input", "Unknown contract topic.", {"topic": pointer}) from None


def _escape(token: Any) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def _overview(spec: Any, pointer: str = "") -> Any:
    if not isinstance(spec, dict):
        return {"kind": type(spec).__name__, "itemCount": len(spec) if isinstance(spec, (list, str)) else None,
                "expandTopic": pointer or "/"}
    result = {k: deepcopy(v) for k, v in spec.items()
              if k in ("type", "required", "enum", "const", "minimum", "maximum", "minItems", "maxItems", "additionalProperties")}
    fields = spec.get("properties", {})
    if fields:
        result["fields"] = [{"name": name, "type": child.get("type"), "required": name in spec.get("required", []),
            "enum": child.get("enum"), "expandTopic": pointer + "/properties/" + _escape(name)}
            for name, child in fields.items()]
    if spec.get("allOf"):
        result["conditions"] = [{"expandTopic": pointer + "/allOf/" + str(i)} for i in range(len(spec["allOf"]))]
    for key in ("oneOf", "anyOf", "$defs", "definitions", "items"):
        if key in spec:
            result[key] = {"expandTopic": pointer + "/" + key}
    return result


def operation_help(name: str, *, max_chars: int = DEFAULT_BUDGET, topic: str | None = None) -> dict:
    """Return a JSON-serializable reply smaller than max_chars, with expansion pointers.

    Budgets refer to compact UTF-8 JSON Unicode characters, not transport wrappers
    or tokens. Callers should serialize compactly and reserve wrapper overhead.
    """
    budget = _budget(max_chars)
    op = _operation(name)
    spec = _pointer(op["schema"], topic or "")
    result = {"schemaVersion": "sp2model.help/1", "operation": name, "source": op["source"],
        "summary": op["summary"], "mutates": op["mutates"], "units": op["units"], "frame": op["frame"],
        "topic": topic or "/", "contract": spec, "example": op["example"] if not topic else None,
        "nextActions": op["nextActions"], "detailComplete": True,
        "contextLimit": "A host can still summarize any earlier reply; query current facts again after context loss."}
    if len(_json(result)) <= budget:
        return result
    result["detailComplete"] = False
    result["contract"] = _overview(spec, "" if topic in (None, "/", "#") else topic.removeprefix("#"))
    result["example"] = None
    result["expand"] = {"operation": name, "topic": topic or "/", "fieldTopics": True}
    if len(_json(result)) <= budget:
        return result
    # Paginate a large property overview without dropping the fact it is partial.
    fields = result["contract"].get("fields", [])
    total = len(fields)
    while fields and len(_json(result)) > budget:
        fields.pop()
        result["contract"]["omittedFieldCount"] = total - len(fields)
        result["contract"]["fieldNamesTopic"] = (topic or "").rstrip("/") + "/properties"
    for key in ("summary", "units", "frame", "contextLimit"):
        if len(_json(result)) > budget:
            result[key] = result[key][:120]
    if len(_json(result)) > budget:
        result = {"schemaVersion": "sp2model.help/1", "operation": name, "topic": topic or "/",
            "detailComplete": False, "mutates": op["mutates"],
            "message": "This topic exceeds the budget. Query an individual property or condition.",
            "expand": {"operation": name, "topic": topic or "/"},
            "required": op["schema"].get("required", []), "nextActions": op["nextActions"]}
    if len(_json(result)) > budget:
        raise ModelingError("help_budget_too_small", "The required facts do not fit this budget; increase max_chars.",
                            {"max_chars": budget, "maximum": MAX_BUDGET, "operation": name})
    return result


def capabilities(*, prefix: str = "", scene: str | None = None, cursor: int = 0,
                 max_chars: int = DEFAULT_BUDGET, include_native: bool = False) -> dict:
    budget = _budget(max_chars)
    if type(cursor) is not int or cursor < 0:
        raise ModelingError("invalid_input", "cursor must be a non-negative integer.")
    rows = [deepcopy(op) for op in _OPERATIONS.values()]
    if include_native:
        from . import registry
        rows += [{"name": op["name"], "summary": op["python"], "mutates": op["mutates"], "scenes": []}
                 for op in registry.commands() if op["name"] not in _OPERATIONS]
    rows = sorted((op for op in rows if op["name"].startswith(prefix)
                   and (not scene or not op["scenes"] or scene in op["scenes"])), key=lambda op: op["name"])
    result = {"schemaVersion": "sp2model.capabilities/1", "total": len(rows), "cursor": cursor,
              "operations": [], "nextCursor": None, "help": "Query help with operation name; topics are JSON pointers."}
    for i, row in enumerate(rows[cursor:], cursor):
        entry = {"name": row["name"], "summary": row["summary"][:180], "mutates": row["mutates"]}
        result["operations"].append(entry)
        if len(_json(result)) > budget:
            result["operations"].pop()
            result["nextCursor"] = i
            break
    return result


def collect_errors(value: Any, schema: dict, *, max_errors: int = 64) -> list[dict]:
    """Collect independent structural errors, including selected action conditions.

    Supports the bundled request-contract vocabulary; domain/native validation
    remains authoritative. No coercion is performed, including booleans as numbers.
    """
    if type(max_errors) is not int or max_errors < 1:
        raise ModelingError("invalid_input", "max_errors must be a positive integer.")
    errors: list[dict] = []
    seen: set[str] = set()

    def emit(path: str, code: str, expected: Any, **extra: Any) -> None:
        row = {"path": path, "code": code, "expected": expected, **extra}
        key = _json({"path": path, "code": code})
        if key not in seen and len(errors) < max_errors:
            errors.append(row)
            seen.add(key)

    def branch_valid(item: Any, spec: dict) -> bool:
        # Carry root definitions so local refs inside alternatives remain valid.
        check = {"allOf": [spec], "$defs": schema.get("$defs", {}), "definitions": schema.get("definitions", {})}
        return not collect_errors(item, check, max_errors=1)

    def visit(item: Any, spec: Any, path: str, depth: int = 0) -> None:
        if depth > 80:
            emit(path, "schema_recursion_limit", "a finite non-recursive request schema")
            return
        if spec is False:
            emit(path, "forbidden", "value must be absent")
            return
        if spec is True or not isinstance(spec, dict):
            return
        if "$ref" in spec:
            ref = spec["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                emit(path, "unsupported_schema_reference", "local JSON pointer", reference=ref)
                return
            try:
                visit(item, _pointer(schema, ref), path, depth + 1)
            except ModelingError:
                emit(path, "unresolved_schema_reference", "existing local definition", reference=ref)
                return
        types = spec.get("type")
        if types:
            options = [types] if isinstance(types, str) else types
            actual = {"object": isinstance(item, dict), "array": isinstance(item, (list, tuple)),
                      "string": isinstance(item, str), "boolean": type(item) is bool,
                      "integer": type(item) is int, "number": type(item) in (int, float), "null": item is None}
            if not any(actual.get(t, False) for t in options):
                emit(path, "type", options, actualType=type(item).__name__)
                return
        if type(item) is float and not math.isfinite(item):
            emit(path, "non_finite", "finite number")
            return
        if "const" in spec and (item != spec["const"] or (type(item) is bool) != (type(spec["const"]) is bool)):
            emit(path, "const", spec["const"])
        if "enum" in spec and not any(item == v and (type(item) is bool) == (type(v) is bool) for v in spec["enum"]):
            emit(path, "enum", spec["enum"])
        for branch in spec.get("allOf", []):
            visit(item, branch, path, depth + 1)
        if "if" in spec:
            selected = "then" if branch_valid(item, spec["if"]) else "else"
            visit(item, spec.get(selected, {}), path, depth + 1)
        for mode in ("oneOf", "anyOf"):
            if mode in spec:
                count = sum(branch_valid(item, branch) for branch in spec[mode])
                if count == 0 or mode == "oneOf" and count != 1:
                    emit(path, mode, "exactly one alternative" if mode == "oneOf" else "at least one alternative",
                         matches=count, alternatives=len(spec[mode]))
        if "not" in spec and branch_valid(item, spec["not"]):
            emit(path, "mutually_exclusive", "must not match forbidden combination", forbidden=spec["not"])
        if isinstance(item, dict):
            fields = spec.get("properties", {})
            for name in spec.get("required", []):
                if name not in item:
                    emit(path + "." + name, "required", fields.get(name, {}).get("type", "present"))
            for name, child in item.items():
                if name in fields:
                    visit(child, fields[name], path + "." + str(name), depth + 1)
                elif spec.get("additionalProperties") is False:
                    emit(path + "." + str(name), "unknown_field", sorted(fields))
                elif isinstance(spec.get("additionalProperties"), dict):
                    visit(child, spec["additionalProperties"], path + "." + str(name), depth + 1)
            for name, required in spec.get("dependentRequired", {}).items():
                if name in item:
                    for other in required:
                        if other not in item:
                            emit(path + "." + other, "required_with", name)
            for keyword, comparison in (("minProperties", lambda n: len(item) < n), ("maxProperties", lambda n: len(item) > n)):
                if keyword in spec and comparison(spec[keyword]):
                    emit(path, keyword, spec[keyword])
        if isinstance(item, (tuple, list)):
            for keyword, comparison in (("minItems", lambda n: len(item) < n), ("maxItems", lambda n: len(item) > n)):
                if keyword in spec and comparison(spec[keyword]):
                    emit(path, keyword, spec[keyword], actual=len(item))
            if spec.get("uniqueItems"):
                encoded = [_json(v) for v in item if not (type(v) is float and not math.isfinite(v))]
                if len(set(encoded)) != len(encoded):
                    emit(path, "duplicate_items", "unique values")
            for i, child in enumerate(item):
                visit(child, spec.get("items", {}), path + "[" + str(i) + "]", depth + 1)
        if isinstance(item, str):
            for keyword, comparison in (("minLength", lambda n: len(item) < n), ("maxLength", lambda n: len(item) > n)):
                if keyword in spec and comparison(spec[keyword]):
                    emit(path, keyword, spec[keyword], actual=len(item))
            if "pattern" in spec and not re.search(spec["pattern"], item):
                emit(path, "pattern", spec["pattern"])
        if type(item) in (float, int):
            for keyword, comparison in (("minimum", lambda n: item < n), ("maximum", lambda n: item > n),
                                        ("exclusiveMinimum", lambda n: item <= n), ("exclusiveMaximum", lambda n: item >= n)):
                if keyword in spec and comparison(spec[keyword]):
                    emit(path, keyword, spec[keyword])

    visit(value, schema, "$")
    return errors


def validate_arguments(value: Any, schema: dict, *, operation: str | None = None) -> Any:
    errors = collect_errors(value, schema)
    if errors:
        raise ModelingError("invalid_input", "Request preflight failed; no dependent write was issued.",
            {"operation": operation, "errors": errors, "errorLimit": 64, "possiblyMore": len(errors) == 64,
             "writesIssued": False, "nextAction": "Correct the listed fields, then preview again."})
    try:
        _json(value)
    except (TypeError, ValueError) as error:
        raise ModelingError("invalid_input", "Request must be finite JSON data.", {"writesIssued": False}) from error
    return value


def compact_state(state: dict, *, max_chars: int = DEFAULT_BUDGET, source: str | None = None) -> dict:
    """Summarize persisted facts without accepting a conversational summary.

    The caller reads authoritative state/journals first. This function does not
    assert that an arbitrary supplied dictionary is current or authoritative.
    Omitted structures have pointers/counts and are never silently treated as pass.
    """
    budget = _budget(max_chars)
    if not isinstance(state, dict):
        raise ModelingError("invalid_input", "Task state must be an object.")
    result = {"schemaVersion": "sp2model.state-summary/1", "source": source,
              "contextAuthority": "Persisted task and execution records; conversation summaries are not execution evidence.",
              "detailComplete": True, "state": deepcopy(state)}
    if len(_json(result)) <= budget:
        return result
    # Keep all keys visible. Large values are explicitly incomplete and expandable.
    result["detailComplete"] = False
    priorities = ("taskId", "stage", "status", "intentId", "requestId", "journal", "execution", "nativeCommit",
                  "postprocess", "reference", "referenceId", "candidateId", "delivery", "failed", "nextActions", "nextAction")
    brief = {}
    for key in [key for key in priorities if key in state] + sorted(state.keys() - set(priorities)):
        value = state[key]
        if len(_json(value)) < 400:
            brief[key] = deepcopy(value)
        else:
            brief[key] = {"detailOmitted": True, "expandPointer": "/" + _escape(key),
                          "itemCount": len(value) if isinstance(value, (dict, list, str)) else None}
            if isinstance(value, dict):
                for fact in ("status", "state", "committed", "ok", "requestId", "journal", "nextAction"):
                    if fact in value and len(_json(value[fact])) < 200:
                        brief[key][fact] = deepcopy(value[fact])
    result["state"] = brief
    if len(_json(result)) > budget:
        # Return an actionable failure rather than hide critical state to fit.
        raise ModelingError("state_budget_too_small", "State summary needs a larger budget or a narrower topic.",
                            {"max_chars": budget, "source": source, "maximum": MAX_BUDGET,
                             "nextAction": "Query task.status for the execution, reference or candidate topic."})
    return result
