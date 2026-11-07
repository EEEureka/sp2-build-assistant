"""Explicit bounded batch sequences with durable partial completion evidence."""
from copy import deepcopy
import uuid

from .errors import ModelingError
from .journal import Journal
from .project import label, same_identity

SCHEMA = "sp2model.sequence/1"


def _builders(builders):
    builders = list(builders)
    if not 1 <= len(builders) <= 64 or any(not callable(builder) for builder in builders):
        raise ModelingError("invalid_input", "A sequence needs 1..64 callable plan builders.")
    return builders


def _load(session, path):
    record = Journal.read(path, schema=SCHEMA)
    if record["instance"]["instanceId"] != session.client.instance["instanceId"]:
        raise ModelingError("instance_conflict", "Sequence belongs to another game process.")
    if record["baselineIdentity"]["craftSessionId"] != session.identity["craftSessionId"]:
        raise ModelingError("session_conflict", "Sequence belongs to another craft epoch.")
    return record


def _view(record, path):
    return {**deepcopy(record), "journalPath": str(path), "atomic": False,
            "recoveryPolicy": "Completed batches are retained. Resume only observes the submitted boundary; continue is explicit and guards the last known identity."}


def execute_sequence(session, builders, *, name):
    builders = _builders(builders)
    label(name, "sequence name")
    session._fresh(session.identity)
    record = {"schemaVersion": SCHEMA, "requestId": uuid.uuid4().hex, "name": name,
              "instance": session.client.instance, "baselineIdentity": session.identity,
              "boundaryIdentity": session.identity, "stepCount": len(builders), "nextIndex": 0,
              "state": "prepared", "completed": [], "pendingJournalPath": None}
    directory = Journal(session.journal.directory / "sequences")
    path = directory.create(record)
    return _run(session, record, path, builders)


def _run(session, record, path, builders):
    for builder in builders:
        expected = deepcopy(record["boundaryIdentity"])
        try:
            session._fresh(expected)
            plan = builder(session, deepcopy(record["completed"]))
            if not hasattr(plan, "to_dict") or not same_identity(plan.to_dict()["baselineIdentity"], expected):
                raise ModelingError("revision_conflict", "Sequence builder changed or rebased the approved boundary.")
        except Exception as cause:
            error = cause if isinstance(cause, ModelingError) else ModelingError(
                "builder_failed", "Sequence plan builder failed before its native submission.", {"exceptionType": type(cause).__name__})
            record.update(state="partial" if record["completed"] else "failed", error=error.to_dict())
            Journal.update(path, record)
            error.details.update(sequenceJournalPath=str(path), completedSteps=len(record["completed"]), nextIndex=record["nextIndex"])
            raise error from None
        preview = None
        observer = getattr(session, "_on_execution_prepared", None)
        if observer is not None:
            raise ModelingError("sequence_active", "Nested execution sequences are not supported.")
        def prepared(execution_path):
            record["pendingJournalPath"] = str(execution_path)
            Journal.update(path, record)
        try:
            preview = plan.preview()
            record.update(state="executing", activeIndex=record["nextIndex"])
            Journal.update(path, record)
            session._on_execution_prepared = prepared
            receipt = plan.apply(preview.token)
        except ModelingError as error:
            pending = error.details.get("journalPath")
            if pending is None and preview is not None:
                execution = session._executions.get(preview.token)
                pending = None if execution is None else str(execution)
            record.update(state="partial" if record["completed"] else "failed", error=error.to_dict(), pendingJournalPath=pending)
            if error.details.get("outcome") == "unknown" or error.code in {"outcome_unknown", "wait_timeout", "result_expired", "operation_not_found"}:
                record["state"] = "outcome_unknown"
            Journal.update(path, record)
            error.details.update(sequenceJournalPath=str(path), completedSteps=len(record["completed"]), nextIndex=record["nextIndex"])
            raise
        finally:
            session._on_execution_prepared = observer
        record["completed"].append(receipt.to_dict())
        record.update(nextIndex=record["nextIndex"]+1, boundaryIdentity=deepcopy(receipt.identity),
                      pendingJournalPath=None, state="succeeded" if record["nextIndex"]+1 == record["stepCount"] else "partial")
        record.pop("error", None)
        Journal.update(path, record)
    return _view(record, path)


def resume_sequence(session, path):
    record = _load(session, path)
    pending = record.get("pendingJournalPath")
    if pending:
        try:
            receipt = session.resume(pending)
        except ModelingError as error:
            if error.details.get("outcome") == "unknown" or error.code in {"outcome_unknown", "wait_timeout", "result_expired", "operation_not_found"}:
                raise
            execution = Journal.read(pending)
            if execution["state"] != "failed":
                raise
            record.update(state="partial" if record["completed"] else "failed", error=error.to_dict(), pendingJournalPath=None)
            if error.details.get("rollbackResult", {}).get("restored") and error.details.get("identity"):
                record["boundaryIdentity"] = deepcopy(error.details["identity"])
            Journal.update(path, record)
            return _view(record, path)
        record["completed"].append(receipt.to_dict())
        record.update(nextIndex=record["nextIndex"]+1, boundaryIdentity=deepcopy(receipt.identity), pendingJournalPath=None,
                      state="succeeded" if record["nextIndex"]+1 == record["stepCount"] else "partial")
        record.pop("error", None)
        Journal.update(path, record)
    return _view(record, path)


def continue_sequence(session, path, builders):
    record = _load(session, path)
    if record.get("pendingJournalPath") or record["state"] in {"outcome_unknown", "executing"}:
        raise ModelingError("pending_execution", "Resolve the submitted boundary before explicitly continuing.")
    if record["state"] == "succeeded":
        return _view(record, path)
    builders = _builders(builders)
    if len(builders) != record["stepCount"] - record["nextIndex"]:
        raise ModelingError("invalid_input", "Provide exactly the remaining step builders.")
    session._fresh(record["boundaryIdentity"])
    return _run(session, record, path, builders)
