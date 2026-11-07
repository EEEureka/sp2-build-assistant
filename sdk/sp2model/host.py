"""Task-level entry point for trusted local modeling scripts.

The host does not submit plans, rewrite scopes, retry scripts, or replay journals.
Python executes with the local user's permissions; this is not a code sandbox.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

from .errors import ModelingError
from .session import PartRef, Preview, Receipt, Scene, Session
from .objects import MaterialRef, SetterRef, OutputRef, ControllerRef
from .wings import ControlHandle
from .native_state import StateAttribute, StateNode
from .mesh import MeshEvidence
from .geometry import Frame
from .transport import canonical_json, READ_COMMANDS


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise ModelingError("invalid_arguments", message)


def _parser():
    parser = _Arguments(prog="python -m sp2model", description="Run trusted local modeling code with an explicit game session. No automatic apply or replay.")
    sub = parser.add_subparsers(dest="action", required=True, parser_class=_Arguments)
    for action, description in (("run", "Execute one trusted local Python script."),
                                ("inspect", "Read the selected designer craft."),
                                ("resume", "Read an existing execution; never resubmit it.")):
        command = sub.add_parser(action, help=description)
        command.add_argument("--instance", required=True, help="Current isolated instanceId or PID; never selected implicitly.")
        command.add_argument("--craft", required=True, help="Exact currently loaded craft name or craftSessionId.")
        command.add_argument("--discovery-dir", default=None)
        command.add_argument("--journal-dir", default=None)
        command.add_argument("--project", default=None, help="Persistent SDK project JSON for logical bindings, tags and groups; reopening still requires explicit rebind.")
        command.add_argument("--timeout", type=float, default=30)
        if action == "inspect":
            command.add_argument("--detail", choices=("summary", "full"), default="summary", help="summary makes one compact native read; full explicitly loads every part.")
        if action == "run":
            command.add_argument("script", help="Trusted local .py source file.")
            inputs = command.add_mutually_exclusive_group()
            inputs.add_argument("--params", default=None, help="JSON object injected as task_parameters.")
            inputs.add_argument("--params-file", default=None, help="UTF-8 JSON object file injected as task_parameters.")
        if action == "resume":
            command.add_argument("journal", help="Existing SDK execution journal path.")
    return parser


def _json_value(value):
    """Expose public result data only; never introspect Session/client objects."""
    if isinstance(value, Receipt):
        return _json_value(value.to_dict())
    if isinstance(value, Preview):
        return {"token": value.token, "planHash": value.plan_hash,
                "writablePartIds": list(value.writable_part_ids), "report": _json_value(value.report)}
    if isinstance(value, PartRef):
        return _json_value(value.to_dict())
    if isinstance(value, MaterialRef):
        return _json_value(value.to_dict())
    if isinstance(value, (SetterRef, OutputRef, ControllerRef, StateAttribute, StateNode, MeshEvidence, ControlHandle, Frame)):
        return _json_value(value.to_dict())
    if isinstance(value, Scene):
        return _json_value(value.to_dict())
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ModelingError("invalid_task_result", "Result object keys must be strings.")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ModelingError("invalid_task_result", "Assign JSON-compatible data, Scene, PartRef, MaterialRef, Preview or Receipt to result.", {"type": type(value).__name__})


def to_jsonable(value):
    """Convert documented SDK data/handles for JSON files, with no native I/O.

    Nested rebind maps and native state handles are supported. Sessions and
    clients are never introspected. Exported data is not a writable reference
    or evidence that its captured identity is still current.
    """
    try:
        result=_json_value(value);canonical_json(result)
    except RecursionError:
        raise ModelingError('invalid_task_result','JSON export cannot contain cyclic or excessively nested data') from None
    except ModelingError as error:
        if error.code!='invalid_input':raise
        raise ModelingError('invalid_task_result','JSON export requires finite values and string dictionary keys') from None
    return result


def _parameters(args):
    try:
        raw = Path(args.params_file).read_text(encoding="utf-8-sig") if args.params_file else args.params or "{}"
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        canonical_json(value)
        return value
    except (OSError, UnicodeError, ValueError, ModelingError) as error:
        raise ModelingError("invalid_parameters", "Task parameters must be a readable, finite JSON object.", {"reason": str(error)}) from None


def _script(args):
    path = Path(args.script).expanduser().resolve()
    if path.suffix.lower() != ".py" or not path.is_file():
        raise ModelingError("invalid_script", "Choose an existing trusted local .py file.", {"path": str(path)})
    try:
        raw = path.read_bytes()
        # compile(bytes) respects the Python source's encoding declaration.
        code = compile(raw, str(path), "exec")
    except (OSError, UnicodeError, SyntaxError) as error:
        details = {"path": str(path), "type": type(error).__name__}
        if isinstance(error, SyntaxError):
            details.update(line=error.lineno, column=error.offset)
        raise ModelingError("invalid_script", str(error), details) from None
    return path, code, hashlib.sha256(raw).hexdigest()


def _journals(session):
    # List matching durable records after either success or error. Do not query
    # or execute them here, and do not return bearer tokens from their contents.
    directory = getattr(getattr(session, "journal", None), "directory", None)
    if directory is None:
        return []
    rows = []
    for path in sorted(Path(directory).rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("schemaVersion") not in ("sp2model.execution/1", "sp2model.runtime/1"):
                continue
            instance, baseline = record.get("instance"), record.get("baselineIdentity") or record.get('args')
            if not isinstance(instance, dict) or not isinstance(baseline, dict):
                continue
            if instance.get("instanceId") != session.client.instance["instanceId"]:
                continue
            if baseline.get("craftSessionId") not in (session.identity["craftSessionId"], getattr(session, '_host_initial_craft', None)):
                continue
            rows.append({"path": str(path.resolve()), "state": record.get("state"),
                         "requestId": record.get("requestId"), "operationId": record.get("operationId"),
                         "command": record.get('command'),
                         "readOnly": record.get('command') in READ_COMMANDS,
                         "resumeKind": 'runtime' if record['schemaVersion'] == 'sp2model.runtime/1' else 'session'})
        except (OSError, ValueError, KeyError, TypeError):
            # A damaged/unrelated journal must not hide the original task result.
            continue
    return rows


def _phases(session, before, *, script_ok):
    """Separate native facts from Python completion; never resume or expose tokens."""
    rows = [row for row in _journals(session) if row['path'] not in before and not row.get('readOnly', False)] if session is not None else []
    committed = [row for row in rows if row['state'] == 'succeeded']
    pending = [row for row in rows if row['state'] in ('prepared', 'submitted', 'outcome_unknown')]
    state = 'outcome_unknown' if pending else 'committed' if committed else 'failed_or_not_submitted' if rows else 'no_new_submission'
    return {'nativeState': state, 'postprocessingState': 'completed' if script_ok else 'failed',
            'confirmedExecutions': committed, 'pendingExecutions': pending,
            'replaySafe': False,
            'nextAction': ('query_original_execution_then_finish_postprocessing' if committed or pending
                           else 'continue_from_reported_state' if script_ok else 'inspect_error_and_plan_explicitly')}


def execute(argv=None, *, session_factory=None, script_stderr=None):
    """Return (exit_code, envelope); deliberately never print or rerun a script."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'model':
        from .model_host import execute as execute_model
        return execute_model(argv[1:], session_factory=session_factory)
    if not argv or argv[0] not in ('run', 'inspect', 'resume'):
        from .command_host import execute as execute_command
        return execute_command(argv)
    action, session, script_identity = None, None, None
    before_journals = set()
    try:
        args = _parser().parse_args(argv)
        action = args.action
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ModelingError("invalid_arguments", "timeout must be a finite positive number of seconds.")
        if action == "run":
            path, code, digest = _script(args)
            parameters = _parameters(args)
            script_identity = {"path": str(path), "sha256": digest}
        factory = session_factory or Session.attach
        options = dict(instance=args.instance, craft=args.craft, discovery_dir=args.discovery_dir,
                       journal_dir=args.journal_dir, timeout=args.timeout,
                       project_path=None if args.project is None else str(Path(args.project).expanduser().resolve()))
        if action == "inspect" and args.detail == "summary": options["summary_only"] = True
        session = factory(**options)
        try:
            from .updates import Updates
            Updates().schedule()
        except Exception:
            pass
        session._host_initial_craft = session.identity['craftSessionId']
        before_journals = {row['path'] for row in _journals(session)}
        if action == "inspect":
            result = session.status(refresh=False) if args.detail == "summary" else session.inspect()
        elif action == "resume":
            result = session.resume(str(Path(args.journal).expanduser().resolve()))
        else:
            globals_ = {"__name__": "__main__", "__file__": str(path), "session": session,
                        "task_parameters": deepcopy(parameters), "result": None}
            original_argv, original_path = sys.argv[:], sys.path[:]
            try:
                sys.argv = [str(path)]
                sys.path.insert(0, str(path.parent))
                with redirect_stdout(script_stderr or sys.stderr):
                    exec(code, globals_, globals_)
                result = globals_["result"]
            finally:
                sys.argv[:] = original_argv
                sys.path[:] = original_path
        data = _json_value(result)
        try:
            canonical_json(data)
        except ModelingError:
            raise ModelingError("invalid_task_result", "Task result contains non-finite or invalid JSON values.") from None
        envelope = {"schemaVersion": "sp2model.host/1", "ok": True, "action": action,
                    "identity": session.identity, "result": data, "journals": _journals(session)}
        envelope['transport']=getattr(session.client,'statistics',{'status':'unavailable'})
        envelope['execution'] = _phases(session, before_journals, script_ok=True)
        if script_identity:
            envelope["script"] = script_identity
        from .updates import decorate as update_notices
        return 0, update_notices(envelope, session.client)
    except SystemExit as error:
        # argparse help is the sole intentional text/zero-exit path. A script's
        # sys.exit never silently turns an interrupted modeling task into success.
        if session is None and error.code == 0:
            return 0, None
        failure = ModelingError("script_exit", "Script exited before returning a result; inspect execution journals before continuing.", {"exitCode": error.code if type(error.code) in (int, str) else None})
    except KeyboardInterrupt:
        failure = ModelingError("interrupted", "Task interrupted. Inspect journals and resume known executions; do not rerun writes automatically.")
    except ModelingError as error:
        failure = error
    except Exception as error:
        frames = traceback.extract_tb(error.__traceback__)
        location = next((frame for frame in reversed(frames) if script_identity and frame.filename == script_identity["path"]), None)
        details = {"type": type(error).__name__}
        if location:
            details.update(path=location.filename, line=location.lineno)
        failure = ModelingError("script_error" if session is not None and action == "run" else "host_error", str(error), details)
    try:
        error_data = _json_value(failure.to_dict())
        canonical_json(error_data)
    except Exception:
        # A trusted script can raise ModelingError with arbitrary Python details.
        # Keep the original public code/message without leaking object internals
        # or letting a second serialization failure hide its execution journal.
        error_data = {"code": str(failure.code), "message": str(failure.message),
                      "details": {"unavailable": "Error details were not JSON-compatible."}}
    envelope = {"schemaVersion": "sp2model.host/1", "ok": False, "action": action,
                "error": error_data, "journals": _journals(session) if session is not None else [],
                "recovery": "No script or write was automatically retried. Use resume for a known execution; reconcile unknown outcomes before new writes."}
    envelope['transport']=getattr(session.client,'statistics',{'status':'unavailable'}) if session is not None else {'status':'unavailable'}
    envelope['execution'] = _phases(session, before_journals, script_ok=False)
    if script_identity:
        envelope["script"] = script_identity
    from .updates import decorate as update_notices
    return 1, update_notices(envelope, session.client if session is not None else None)


def main(argv=None):
    code, envelope = execute(argv)
    if envelope is not None:
        print(json.dumps(envelope, ensure_ascii=False, allow_nan=False))
    return code
