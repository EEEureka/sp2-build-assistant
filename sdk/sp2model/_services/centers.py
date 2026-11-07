"""Centers request contract and data-only baseline loading (standard library)."""
from pathlib import Path
import json
import math

MAX_BASELINE_BYTES = 8 * 1024 * 1024


def schema():
    def obj(props, required=()):
        return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}
    integer = {"type": "integer", "minimum": 0}
    return obj({
        "craftSessionId": {"type": "string", "minLength": 1},
        "expectedRevision": {"type": "integer", "minimum": 1},
        "detail": {"type": "string", "enum": ["summary", "contributors"], "default": "summary", "description": "Use contributors to return per-part rows. Default summary has requested=false and empty items even when total>0. --metric only filters the metric; it does not enable rows."},
        "metric": {"type": "string", "enum": ["all", "mass", "lift", "thrust"], "default": "all", "description": "Filters contribution rows only; never changes whole-aircraft centers."},
        "focus": {"type": "string", "enum": ["all", "selected"], "default": "all"},
        "focusSelector": {"oneOf": [obj({"kind": {"const": "parts"}, "partIds": {"type": "array", "minItems": 1, "maxItems": 2048, "uniqueItems": True, "items": integer}}, ["kind", "partIds"]), obj({"kind": {"const": "assembly"}, "rootPartId": integer}, ["kind", "rootPartId"])], "description": "Explicit focus instead of focus; contributor filter and visual highlight only."},
        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
        "offset": {"type": "integer", "minimum": 0, "default": 0},
        "frame": {"oneOf": [obj({"kind": {"const": "world"}}, ["kind"]), obj({"kind": {"const": "part"}, "partId": integer}, ["kind", "partId"])], "description": "Rigid coordinate frame. +Z is a convention, not an inferred nose direction."},
        "images": {"type": "boolean", "default": False, "description": "Presence flag --images, or JSON boolean. Same-sample native mesh images with COM/COL/COT overlays; requires loaded DLL 0.4.0+."},
        "resolution": obj({k: {"type": "integer", "minimum": 384, "maximum": 1024, "default": 640} for k in ("width", "height")}),
        "baseline": {"type": "string", "description": "UTF-8 full successful craft.centers report saved by --output, up to 8 MiB. Not an XML aircraft or CLI output receipt. Same-session/basis comparison only."},
    }) | {"not": {"required": ["focus", "focusSelector"]}}


def load_baseline(path, error_type):
    def invalid(message):
        raise error_type("invalid_baseline", message)
    if not isinstance(path, str) or not path:
        invalid("baseline must be a saved centers report path")
    try:
        with Path(path).expanduser().open("rb") as stream:
            raw = stream.read(MAX_BASELINE_BYTES + 1)
        if len(raw) > MAX_BASELINE_BYTES:
            invalid("Centers baseline exceeds 8 MiB")
        def constant(value):
            raise ValueError("Nonfinite JSON number: " + value)
        report = json.loads(raw.decode("utf-8-sig"), parse_constant=constant)
    except (OSError, ValueError, UnicodeError) as exc:
        invalid("Cannot read a finite UTF-8 JSON centers report: " + str(exc))
    if not isinstance(report, dict) or report.get("success") is not True or not isinstance(report.get("data"), dict):
        invalid("Expected a full successful craft.centers result, not an output receipt, XML, or operation acceptance")
    data = report["data"]
    if not isinstance(data.get("calculationVersion"), str) or not isinstance(data.get("analysisId"), str):
        invalid("Missing centers calculationVersion or analysisId")
    for key in ("identity", "basis", "frame", "scope", "centers", "relations"):
        if not isinstance(data.get(key), dict):
            invalid("Missing centers object: " + key)
    identity = data["identity"]
    if not isinstance(identity.get("craftSessionId"), str) or not identity["craftSessionId"] or type(identity.get("revision")) is not int:
        invalid("Invalid baseline identity")
    for key in ("mode", "loadCondition", "scopePolicy"):
        if not isinstance(data["basis"].get(key), str):
            invalid("Missing calculation basis: " + key)
    def vector(value, count=3, allow_none=True):
        if value is None and allow_none:
            return
        def finite(n):
            try:
                return type(n) in (float, int) and math.isfinite(n)
            except OverflowError:
                return False
        if not isinstance(value, list) or len(value) != count or any(not finite(n) for n in value):
            invalid("Baseline vectors must contain finite numbers")
    vector(data["basis"].get("liftProjectionAxisWorld"), allow_none=False)
    vector(data["basis"].get("aircraftOrientationWorld"), 4)
    frame = data["frame"]
    if frame.get("kind") not in ("world", "part"):
        invalid("Invalid baseline frame")
    vector(frame.get("orientationWorld"), 4, False)
    if frame["kind"] == "part" and (type(frame.get("partId")) is not int or not isinstance(frame.get("referenceToken"), str) or not frame["referenceToken"]):
        invalid("Part-frame baseline requires reference identity, not just a reusable part ID")
    for key in ("com", "col", "cot"):
        center = data["centers"].get(key)
        if not isinstance(center, dict) or center.get("status") not in ("valid", "partial", "unavailable"):
            invalid("Missing or invalid center: " + key)
        vector(center.get("positionFrameMeters"), allow_none=center["status"] == "unavailable")
        vector(center.get("positionWorldMeters"), allow_none=center["status"] == "unavailable")
    for key in ("colFromCom", "cotFromCom", "cotFromCol"):
        if key not in data["relations"]:
            invalid("Missing relative center relationship: " + key)
        relation = data["relations"][key]
        if relation is not None:
            if not isinstance(relation, dict):
                invalid("Invalid center relationship")
            vector(relation.get("deltaFrameMeters"), allow_none=False)
    # Do not send images, text instructions, local paths, or potentially huge contributor rows.
    return {key: data[key] for key in ("identity", "analysisId", "calculationVersion", "basis", "frame", "scope", "centers", "relations")}
