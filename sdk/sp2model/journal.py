"""Durable execution records. A journal is evidence, never a replay queue."""
from __future__ import annotations
import json
import os
from pathlib import Path
import uuid
from .transport import canonical_json
from .errors import ModelingError


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def create(self, record):
        path = self.directory / (record["requestId"] + ".json")
        with path.open("xb") as stream:
            stream.write(canonical_json(record))
            stream.flush()
            os.fsync(stream.fileno())
        return path

    @staticmethod
    def read(path, *, schema="sp2model.execution/1"):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schemaVersion") != schema:
            raise ModelingError("invalid_journal", "Unsupported execution journal.")
        return data

    @staticmethod
    def update(path, record):
        path = Path(path)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("xb") as stream:
            stream.write(canonical_json(record))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def pending(self, instance_id, craft_session):
        result = []
        for path in self.directory.rglob("*.json"):
            record = json.loads(path.read_text(encoding='utf-8'))
            schema = record.get('schemaVersion')
            if schema not in ('sp2model.execution/1', 'sp2model.runtime/1'):
                if record.get('requestId') and record.get('instance') and record.get('state') in ('prepared', 'submitted', 'outcome_unknown') and schema != 'sp2model.cancel/1':
                    raise ModelingError('invalid_journal', 'Unsupported pending execution; inspect it before new writes.', {'path': str(path)})
                continue
            from .transport import READ_COMMANDS
            if record.get('command') in READ_COMMANDS: continue
            baseline = record.get('baselineIdentity') or record.get('args', {})
            if (record["instance"]["instanceId"] == instance_id
                    and baseline.get("craftSessionId") == craft_session
                    and record["state"] in ("prepared", "submitted", "outcome_unknown")):
                result.append(str(path))
        return result
