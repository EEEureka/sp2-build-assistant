"""Small, versioned UTF-8 stores used without the game or numerical worker."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone


class ReferenceError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ReferenceError("invalid_input", "Non-finite JSON numbers are not supported")
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _finite(child)


def canonical(value):
    _finite(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_hash(path):
    checksum = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(block)
    except OSError as exc:
        raise ReferenceError("source_unavailable", "Cannot read reference source", path=str(path), reason=str(exc)) from exc
    return checksum.hexdigest()


def read_json(path, kind=None, version=1):
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            value = json.load(stream, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    except (OSError, ValueError) as exc:
        raise ReferenceError("invalid_document", "Cannot read UTF-8 JSON document", path=str(path), reason=str(exc)) from exc
    _finite(value)
    if not isinstance(value, dict):
        raise ReferenceError("invalid_document", "Document root must be an object")
    if kind and value.get("kind") != kind:
        raise ReferenceError("document_kind_mismatch", "Unexpected document kind", expected=kind, actual=value.get("kind"))
    if kind and value.get("schemaVersion") != version:
        raise ReferenceError("incompatible_schema", "Unsupported schema version", supported=[version], actual=value.get("schemaVersion"))
    return value


def write_json(path, value, expected_hash=None, overwrite=True):
    """Atomic replace, with optimistic concurrency for project/plan edits."""
    target = Path(path).resolve()
    if target.exists():
        if not overwrite:
            raise ReferenceError("document_exists", "Document already exists", path=str(target))
        if expected_hash is not None and file_hash(target) != expected_hash:
            raise ReferenceError("document_changed", "Document changed since it was read", path=str(target))
    elif expected_hash is not None:
        raise ReferenceError("document_changed", "Previously read document is missing", path=str(target))
    _finite(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, suffix=".tmp", delete=False, newline="\n") as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return {"path": str(target), "sha256": file_hash(target)}
