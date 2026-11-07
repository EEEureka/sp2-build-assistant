"""Direct authenticated local bridge client; no CLI process or CLI imports.

Submission and completion are distinct. An uncertain POST is never repeated by
this module. Its request ID belongs in the caller's durable execution journal.
"""

from __future__ import annotations

import ipaddress
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import socket
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

from .errors import ModelingError


# Unknown future commands are treated as writes. A naming suffix such as .get
# is not sufficient evidence that a command is safe to submit without a key.
READ_COMMANDS = frozenset({
    "capabilities", "designer.status", "designer.selection", "designer.crafts", "craft.status", "parts.query", "native.state", "model.dependencies", "mechanical.get", "wing.stations", "airfoils.describe",
    "designer.raycast", "designer.capture", "scope.get", "appearance.get",
    "resources.list", "groups.resolve", "decal.pose.get", "geometry.measure",
    "geometry.section", "geometry.seam", "geometry.symmetry", "craft.diff",
    "properties.describe", "properties.get", "craft.centers", "visual.resolve",
    "visual.capture", "visual.pick", "parts.geometry", "shape.get", "shape.schema",
    "symmetry.get", "craft.snapshot", "parts.list", "parts.get", "parts.assembly",
    "connections.list", "connections.points", "spatial.query", "catalog.categories",
    "catalog.subcategories", "catalog.list", "catalog.search", "catalog.get",
    "catalog.schema", "catalog.export", "outputs.list", "variables.list",
    "funky.list", "funky.describe", "funky.validate", "logic.dependencies", "craft.history",
    "craft.checkpoint.list", "craft.checkpoint.get", "batch.preview",
})
_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "result_expired"})
_STATES = _TERMINAL | {"queued", "running"}
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.-]{1,256}\Z")
_COMMAND = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*\Z")
_ARTIFACT_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.(?:png|json)\Z")
_SECRET_KEYS = {"token", "authorization", "x-sp2build-token", "access_token"}
_MAX_RESPONSE = 64 * 1024 * 1024
_MAX_REQUEST = 4 * 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # In particular, never forward the instance token to a Location URL.
        return None


def _seconds(value: Any, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelingError("invalid_input", "Timeout must be a finite number of seconds.")
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ModelingError("invalid_input", "Timeout must be finite and positive.")
    return float(value)


def _strict_loads(raw: bytes) -> Any:
    def reject_constant(value):
        raise ValueError("Non-finite JSON number")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    return json.loads(raw.decode("utf-8-sig"), parse_constant=reject_constant,
                      object_pairs_hook=unique_keys)


def canonical_json(value: Any) -> bytes:
    """Stable bytes are required by the bridge's request-ID content signature."""
    def check_keys(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings")
            for child in item.values():
                check_keys(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check_keys(child)

    try:
        check_keys(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        raise ModelingError("invalid_input", "Request must contain finite, valid JSON values.") from None


class BridgeClient:
    """A client bound to one authenticated local game instance descriptor.

    ``descriptor`` is a discovery JSON object, not a URL or bearer token string.
    Construction validates it without performing network I/O; ``discover`` also
    authenticates it against the live bridge. URLs must use literal loopback IPs.
    """

    def __init__(self, descriptor: Mapping[str, Any], timeout: float = 30):
        self.timeout = _seconds(timeout)
        if not isinstance(descriptor, Mapping):
            raise ModelingError("invalid_descriptor", "Expected an instance descriptor object.")
        try:
            url = descriptor["baseUrl"]
            if not isinstance(url, str) or any(ord(c) <= 32 for c in url):
                raise ValueError()
            parsed = urlsplit(url)
            host = parsed.hostname
            address = ipaddress.ip_address(host or "")
            if (parsed.scheme != "http" or not address.is_loopback or parsed.username is not None
                    or parsed.password is not None or parsed.path not in ("", "/")
                    or parsed.query or parsed.fragment or parsed.port is None
                    or not 1 <= parsed.port <= 65535 or "%" in (host or "")):
                raise ValueError()
            token = descriptor["token"]
            if (not isinstance(token, str) or not 1 <= len(token) <= 512
                    or any(not 33 <= ord(c) <= 126 for c in token)):
                raise ValueError()
            pid = descriptor["pid"]
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                raise ValueError()
            instance_id = descriptor["instanceId"]
            if not isinstance(instance_id, str) or not _IDENTIFIER.fullmatch(instance_id):
                raise ValueError()
            version = descriptor["pluginVersion"]
            if not isinstance(version, str) or not version or len(version) > 128:
                raise ValueError()
            protocol = str(descriptor["protocolVersion"])
            if protocol != "1":
                raise ModelingError("protocol_mismatch", "This SDK requires bridge protocol version 1.")
        except (KeyError, TypeError, ValueError):
            raise ModelingError("invalid_descriptor", "Invalid local bridge descriptor; expected a literal loopback HTTP URL and complete instance identity.") from None
        host_text = f"[{address}]" if address.version == 6 else str(address)
        self._base_url = f"http://{host_text}:{parsed.port}/"
        self._token = token
        self._instance = {"instanceId": instance_id, "pid": pid, "pluginVersion": version,
                          "protocolVersion": protocol, "baseUrl": self._base_url}
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())
        self._request_ids: dict[str, str] = {}
        self._command_posts = {}

    @property
    def statistics(self):
        """Local command POST attempts for this client, without another request."""
        return {'commandPostAttempts':sum(self._command_posts.values()),'commands':dict(self._command_posts),
                'meaning':'This Python invocation/client only; includes attempted submissions with unknown outcomes, excludes GET polls/artifacts. Aggregate invocations for a task budget.'}

    @property
    def instance(self) -> dict[str, Any]:
        """Public identity only; the authentication token is never returned."""
        return self._redact(dict(self._instance))

    def __repr__(self) -> str:
        return f"BridgeClient(instanceId={self.instance['instanceId']!r}, pid={self.instance['pid']!r})"

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key).replace(self._token, "[REDACTED]"):
                    "[REDACTED]" if str(key).lower() in _SECRET_KEYS else self._redact(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, str):
            return value.replace(self._token, "[REDACTED]")
        return value

    @classmethod
    def discover(cls, instance=None, discovery_dir=None, timeout=30) -> "BridgeClient":
        """Authenticate discovery records and require exactly one matching game.

        Authentication uses a nonexistent operation lookup, which cannot enqueue
        a command or read/edit the current craft. Stale tokens are ignored.
        """
        timeout = _seconds(timeout)
        directory = (Path(discovery_dir) if discovery_dir is not None else
                     Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) /
                     "SP2BuildAssistant" / "instances")
        selected = None if instance is None else str(instance)
        candidates = {}
        try:
            paths = sorted(directory.glob("*.json"))
        except OSError:
            paths = []
        for path in paths:
            try:
                if path.stat().st_size > 64 * 1024:
                    continue
                descriptor = _strict_loads(path.read_bytes())
                client = cls(descriptor, timeout=timeout)
                if selected is not None and selected not in (
                        str(client._instance["pid"]), client._instance["instanceId"]):
                    continue
                client._http("GET", "v1/operations/discovery-" + uuid.uuid4().hex,
                             timeout=min(timeout, 1.0))
            except ModelingError as exc:
                if exc.code == "operation_not_found":
                    identity = (client._instance["instanceId"], client._base_url, client._token)
                    candidates[identity] = client
            except (OSError, TypeError, ValueError, UnicodeError):
                continue
        if not candidates:
            raise ModelingError("bridge_not_running", "No authenticated matching SP2 bridge was found.")
        if len(candidates) != 1:
            raise ModelingError("multiple_instances", "Select a game by PID or instanceId before attaching.",
                                {"instances": [client.instance for client in candidates.values()]})
        return next(iter(candidates.values()))

    def _error(self, error: Any, extra=None, envelope=None) -> ModelingError:
        if not isinstance(error, dict):
            return ModelingError("bridge_protocol_error", "Bridge returned an invalid error envelope.", extra)
        details = error.get("details", {})
        if not isinstance(details, dict):
            details = {"bridgeDetails": details}
        # Native mutation failures place identity and rollbackResult beside
        # error, not inside error.details. They are recovery evidence, not noise.
        evidence = ({key: value for key, value in envelope.items()
                     if key not in {"success", "schemaVersion", "error"}}
                    if isinstance(envelope, dict) else {})
        details = {**details, **evidence, **(extra or {})}
        code = error.get("code", "execution_failed")
        message = error.get("message", "Bridge operation failed.")
        return ModelingError(self._redact(str(code)), self._redact(str(message)), self._redact(details))

    def _http(self, method: str, route: str, payload=None, timeout=None) -> dict[str, Any]:
        raw = None if payload is None else canonical_json(payload)
        if raw is not None and len(raw) > _MAX_REQUEST:
            raise ModelingError("input_too_large", "Bridge requests are limited to 4 MiB.")
        request_id = payload.get("requestId") if isinstance(payload, dict) else None
        uncertain = {"outcome": "unknown", "requestId": request_id,
                     "instance": self.instance, "retrySafe": False}
        request = Request(self._base_url + route, data=raw, method=method,
                          headers={"Content-Type": "application/json; charset=utf-8",
                                   "X-SP2Build-Token": self._token})
        if method=='POST' and route=='v1/operations':
            command=payload['command'];self._command_posts[command]=self._command_posts.get(command,0)+1
        try:
            try:
                response = self._opener.open(request, timeout=self.timeout if timeout is None else timeout)
            except HTTPError as exc:
                response = exc
            with response:
                status = response.code
                if 300 <= status < 400:
                    raise ModelingError("redirect_rejected", "Bridge redirects are forbidden; no redirect target was contacted.",
                                        self._redact(uncertain) if method == "POST" else {})
                body = response.read(_MAX_RESPONSE + 1)
                if len(body) > _MAX_RESPONSE:
                    raise ValueError("Response size limit")
                envelope = _strict_loads(body)
        except ModelingError:
            raise
        except (URLError, OSError, socket.timeout, TimeoutError, HTTPException):
            if method == "POST":
                raise ModelingError("outcome_unknown", "Submission response was lost. Inspect the saved request and current state; do not submit a new request ID.",
                                    self._redact(uncertain)) from None
            raise ModelingError("bridge_unreachable", "The bound local bridge could not be reached.",
                                {"instance": self.instance}) from None
        except (ValueError, UnicodeError):
            if method == "POST":
                raise ModelingError("outcome_unknown", "Submission returned an unreadable response; execution status is unknown.",
                                    self._redact(uncertain)) from None
            raise ModelingError("bridge_protocol_error", "Bridge returned invalid or oversized JSON.") from None
        if not isinstance(envelope, dict) or not isinstance(envelope.get("success"), bool):
            code = "outcome_unknown" if method == "POST" else "bridge_protocol_error"
            raise ModelingError(code, "Bridge returned an invalid response envelope.",
                                self._redact(uncertain) if method == "POST" else {})
        if not envelope["success"]:
            raise self._error(envelope.get("error"), envelope=envelope)
        if not isinstance(envelope.get("data"), dict) or not 200 <= status < 300:
            code = "outcome_unknown" if method == "POST" else "bridge_protocol_error"
            raise ModelingError(code, "Bridge returned invalid success data.",
                                self._redact(uncertain) if method == "POST" else {})
        return self._redact(envelope["data"])

    def _submit(self, command, args, request_id, timeout) -> str:
        if not isinstance(command, str) or not _COMMAND.fullmatch(command):
            raise ModelingError("invalid_input", "Command must be a bridge command name.")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ModelingError("invalid_input", "Command arguments must be a JSON object.")
        if request_id is None:
            if command not in READ_COMMANDS:
                raise ModelingError("request_id_required", "Writes require a durable request_id before submission.")
            request_id = uuid.uuid4().hex
        if (not isinstance(request_id, str) or not request_id.strip()
                or len(request_id) > 256 or any(ord(c) < 32 for c in request_id)):
            raise ModelingError("invalid_input", "request_id must be a nonempty string of at most 256 characters.")
        payload = {"command": command, "args": args, "requestId": request_id}
        job = self._http("POST", "v1/operations", payload, timeout=timeout)
        operation_id = job.get("operationId")
        if not isinstance(operation_id, str) or not _IDENTIFIER.fullmatch(operation_id):
            raise ModelingError("outcome_unknown", "Bridge accepted the request without a usable operation ID.",
                                self._redact({"requestId": request_id, "outcome": "unknown", "retrySafe": False,
                                              "instance": self.instance}))
        self._request_ids[operation_id] = request_id
        return operation_id

    def submit(self, command, args=None, request_id=None) -> str:
        """Submit once and return the operation ID, regardless of current state."""
        return self._submit(command, args, request_id, self.timeout)

    def call(self, command, args=None, request_id=None, timeout=None) -> dict[str, Any]:
        """Submit once, then return unwrapped successful result data."""
        duration = self.timeout if timeout is None else _seconds(timeout)
        started = time.monotonic()
        operation_id = self._submit(command, args, request_id, min(self.timeout, duration))
        return self.wait(operation_id, timeout=max(0, duration - (time.monotonic() - started)))

    def _operation_id(self, operation_id):
        if not isinstance(operation_id, str) or not _IDENTIFIER.fullmatch(operation_id):
            raise ModelingError("invalid_input", "operation_id must be a bridge operation identifier.")

    def _context(self, operation_id):
        context = {"operationId": operation_id, "instance": self.instance}
        if operation_id in self._request_ids:
            context["requestId"] = self._request_ids[operation_id]
        return self._redact(context)

    def _status(self, operation_id, timeout):
        self._operation_id(operation_id)
        context = self._context(operation_id)
        try:
            job = self._http("GET", "v1/operations/" + operation_id, timeout=timeout)
        except ModelingError as exc:
            exc.details.update(context)
            exc.details.update({"outcome": "unknown", "retrySafe": False})
            raise
        if (job.get("operationId") != operation_id or not isinstance(job.get("state"), str)
                or job["state"] not in _STATES):
            raise ModelingError("bridge_protocol_error", "Bridge returned a mismatched operation or unknown state.",
                                {**context, "outcome": "unknown", "retrySafe": False})
        return job

    def status(self, operation_id: str) -> dict[str, Any]:
        """Return the job envelope. An expired result does not replay its request."""
        return self._status(operation_id, self.timeout)

    def cancel(self, operation_id: str) -> dict[str, Any]:
        """Request cancellation; the returned state determines its effect."""
        self._operation_id(operation_id)
        try:
            result = self._http('DELETE', 'v1/operations/' + operation_id)
        except ModelingError as error:
            error.details.update(self._context(operation_id), cancellationOutcome='unknown', retrySafe=False)
            raise
        return {**result, 'cancellationRequested': True,
                'meaning': 'Cancellation request received; only terminal native status proves completion/cancellation. Completed chunks may remain.'}

    def lookup_request(self, request_id: str) -> dict[str, Any]:
        """Read an existing request mapping; absence never permits resubmission."""
        if (not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id)
                or ".." in request_id):
            raise ModelingError("invalid_input", "request_id lookup requires a simple bridge request identifier.")
        context = self._redact({"requestId": request_id, "instance": self.instance,
                                "outcome": "unknown", "retrySafe": False})
        try:
            job = self._http("GET", "v1/requests/" + request_id)
        except ModelingError as error:
            error.details.update(context)
            raise
        operation_id = job.get("operationId")
        if (not isinstance(operation_id, str) or not _IDENTIFIER.fullmatch(operation_id)
                or not isinstance(job.get("state"), str) or job["state"] not in _STATES
                or ("requestId" in job and job["requestId"] != request_id)):
            raise ModelingError("bridge_protocol_error", "Bridge returned an invalid or mismatched request lookup.", context)
        self._request_ids[operation_id] = request_id
        return job

    def artifact(self, capture_id: str, filename: str) -> bytes:
        """Download a retained PNG/JSON artifact, without writing a local file.

        Use the capture ID and exact filename returned by the bridge. Downloads
        are authenticated, limited to 64 MiB, and cannot follow redirects.
        """
        self._operation_id(capture_id)
        if (".." in capture_id or not isinstance(filename, str)
                or not _ARTIFACT_FILE.fullmatch(filename) or ".." in filename):
            raise ModelingError("invalid_input", "Artifacts require a capture ID and a simple PNG or JSON filename.")
        context = self._redact({"captureId": capture_id, "filename": filename, "instance": self.instance})
        request = Request(self._base_url + "v1/visual/" + capture_id + "/" + filename,
                          method="GET", headers={"X-SP2Build-Token": self._token})
        try:
            try:
                response = self._opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                response = exc
            with response:
                status = response.code
                if 300 <= status < 400:
                    raise ModelingError("redirect_rejected", "Artifact redirects are forbidden; no redirect target was contacted.", context)
                body = response.read(_MAX_RESPONSE + 1)
                if len(body) > _MAX_RESPONSE:
                    raise ModelingError("artifact_too_large", "Artifact exceeds the 64 MiB download limit.", context)
        except ModelingError:
            raise
        except (URLError, OSError, socket.timeout, TimeoutError, HTTPException):
            raise ModelingError("bridge_unreachable", "The bound local bridge could not deliver the artifact.", context) from None
        if not 200 <= status < 300:
            try:
                envelope = _strict_loads(body)
            except (ValueError, UnicodeError):
                raise ModelingError("bridge_protocol_error", "Artifact request failed without a structured bridge error.", context) from None
            if isinstance(envelope, dict) and envelope.get("success") is False:
                raise self._error(envelope.get("error"), context, envelope=envelope)
            raise ModelingError("bridge_protocol_error", "Artifact request returned an invalid error envelope.", context)
        return body

    def wait(self, operation_id: str, timeout=None) -> dict[str, Any]:
        """Poll only the existing operation; all failure details retain its ID."""
        self._operation_id(operation_id)
        duration = self.timeout if timeout is None else _seconds(timeout, allow_zero=True)
        deadline = time.monotonic() + duration
        context = self._context(operation_id)
        last_state=None
        def expired(poll_error=None):
            details={**context,'state':last_state,'outcome':'unknown','retrySafe':False,'stateMeaning':'Last observed state; completion at the expired wait deadline is unknown.'}
            if poll_error is not None:details['lastPollError']=poll_error.to_dict()
            return ModelingError('wait_timeout','Wait budget expired. Query this original operation again; do not submit another write.',details)
        while True:
            if last_state is not None and time.monotonic()>=deadline:raise expired()
            try:job = self._status(operation_id, max(0.001, min(self.timeout, deadline - time.monotonic())))
            except ModelingError as error:
                if last_state is not None and error.code=='bridge_unreachable' and time.monotonic()>=deadline:raise expired(error) from None
                raise
            state = job["state"]
            last_state=state
            if state in _TERMINAL:
                result = job.get("result")
                if state == "result_expired" or result is None:
                    raise ModelingError("result_expired", "Completed result is unavailable. Inspect current state; do not replay the write with a new request ID.",
                                        {**context, "completionState": job.get("completionState"),
                                         "resultRetention": job.get("resultRetention"),
                                         "outcome": "unknown", "retrySafe": False})
                if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
                    raise ModelingError("bridge_protocol_error", "Operation returned an invalid result envelope.",
                                        {**context, "outcome": "unknown", "retrySafe": False})
                if not result["success"]:
                    raise self._error(result.get("error"), context, envelope=result)
                if state != "succeeded" or not isinstance(result.get("data"), dict):
                    raise ModelingError("bridge_protocol_error", "Operation state and result data are inconsistent.",
                                        {**context, "outcome": "unknown", "retrySafe": False})
                return {**self._redact(result["data"]), "operationId": operation_id}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise expired()
            time.sleep(min(0.05, remaining))
