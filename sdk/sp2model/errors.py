"""Structured exceptions shared by the modeling SDK."""

from __future__ import annotations

from typing import Any


class ModelingError(Exception):
    """A machine-readable failure with actionable, JSON-compatible details."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}
