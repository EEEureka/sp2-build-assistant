"""Download immutable visual artifacts. No imaging dependency or game-file access."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def download(instance, result, directory, error_type):
    if not result.get("success") or "artifactBase" not in result.get("data", {}):
        return result
    data = result["data"]
    capture = data.get("captureId", "")
    if not re.fullmatch(r"[a-f0-9]{32}", capture) or data["artifactBase"] != f"v1/visual/{capture}/":
        raise error_type("invalid_artifact", "Invalid capture artifact identity")
    root = (Path(directory) if directory else Path.home() / ".sp2build" / "captures").expanduser().resolve()
    destination = root / capture
    if destination.is_symlink() or (destination.exists() and destination.resolve().parent != root):
        raise error_type("invalid_artifact", "Capture directory must stay under output-dir")
    destination.mkdir(parents=True, exist_ok=True)
    files = data.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 220:
        raise error_type("invalid_artifact", "Invalid file count")
    seen, total = set(), 0
    for item in files:
        name, size, digest = item.get("name", ""), item.get("bytes"), item.get("sha256", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.(png|json)", name) or name in seen:
            raise error_type("invalid_artifact", "Invalid or duplicate artifact name")
        if type(size) is not int or not 0 < size <= 80 * 1024 * 1024 or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise error_type("invalid_artifact", "Invalid artifact size or digest")
        seen.add(name)
        total += size
    payload = "measurement.json" if data.get("artifactType") == "geometry_measurement" else "overview.png"
    if "manifest.json" not in seen or payload not in seen or total > 192 * 1024 * 1024:
        raise error_type("invalid_artifact", "Capture incomplete or exceeds download budget")
    opener = build_opener(ProxyHandler({}))
    try:
        for item in files:
            path = destination / item["name"]
            if path.is_symlink():
                raise error_type("invalid_artifact", "Refusing symlink output")
            if path.is_file() and path.stat().st_size == item["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]:
                continue
            request = Request(instance["baseUrl"] + data["artifactBase"] + item["name"], headers={"X-SP2Build-Token": instance["token"]})
            try:
                with opener.open(request, timeout=30) as response:
                    blob = response.read(item["bytes"] + 1)
            except HTTPError as exc:
                try:
                    detail = json.loads(exc.read().decode("utf-8"))["error"]
                except (ValueError, KeyError):
                    detail = {"code": "artifact_download_failed", "message": f"HTTP {exc.code}"}
                raise error_type(detail["code"], detail["message"], operationId=result.get("operationId"), captureId=capture) from exc
            if len(blob) != item["bytes"] or hashlib.sha256(blob).hexdigest() != item["sha256"]:
                raise error_type("artifact_integrity", "Artifact length/hash mismatch", captureId=capture)
            temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
            try:
                temporary.write_bytes(blob)
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
    except (OSError, URLError) as exc:
        raise error_type("artifact_download_failed", str(exc), operationId=result.get("operationId"), captureId=capture) from exc
    data["outputDirectory"] = str(destination)
    data["manifestPath"] = str(destination / "manifest.json")
    images = data.get("recommendedImages", [])
    if any(name not in seen or not name.endswith(".png") for name in images):
        raise error_type("invalid_artifact", "Invalid recommended image")
    data["recommendedImages"] = [str(destination / name) for name in images]
    for recommendation in data.get("imageRecommendations", []):
        name = recommendation.get("file")
        if name not in seen or not name.endswith(".png"):
            raise error_type("invalid_artifact", "Invalid image recommendation")
        recommendation["path"] = str(destination / name)
    return result


def schema(command):
    integer = {"type": "integer"}
    def obj(properties, required):
        return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
    if command == "visual.pick":
        return obj({"captureId": {"type": "string"}, "view": {"type": "string"}, "x": {"type": "integer", "minimum": 0}, "y": {"type": "integer", "minimum": 0}}, ["captureId", "view", "x", "y"])
    selectors = []
    for kind, fields in {
        "parts": {"partIds": {"type": "array", "minItems": 1, "items": integer}},
        "selected": {}, "craft": {}, "assembly": {"rootPartId": integer},
        "branch": {"rootPartId": integer, "stopConnectionKeys": {"type": "array", "minItems": 1, "items": {"type": "string"}}},
        "neighborhood": {"rootPartId": integer, "hops": {"type": "integer", "minimum": 0, "maximum": 10}},
    }.items():
        selectors.append(obj({"kind": {"const": kind}, **fields}, ["kind", *fields]))
    props = {"craftSessionId": {"type": "string", "minLength": 1}, "expectedRevision": {"type": "integer", "minimum": 1},
             "groups": {"type": "array", "minItems": 1, "maxItems": 8, "description": "Optional: omission inspects the player's current selection and returns selection_empty if none is selected. It does not mean the whole aircraft. For the whole craft use [{\"name\":\"craft\",\"selector\":{\"kind\":\"craft\"}}]. An explicitly supplied array must contain 1..8 disjoint named groups.", "items": obj({"name": {"type": "string", "minLength": 1, "maxLength": 80}, "selector": {"oneOf": selectors}}, ["name", "selector"])},
             "maxParts": {"type": "integer", "minimum": 1, "maximum": 2048}}
    if command == "visual.capture":
        vector = {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number"}}
        props.update({"views": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"oneOf": [
            {"enum": ["front", "right", "top", "isometric", "back", "left", "bottom"]},
            obj({"name": {"type": "string", "pattern": "^(?!g)(?!(?:overview|con|prn|aux|nul|com[0-9]|lpt[0-9])$)[a-z][a-z0-9-]{0,31}$"}, "direction": vector, "up": vector}, ["name", "direction", "up"])]}},
            "resolution": obj({k: {"type": "integer", "minimum": 128, "maximum": 1024} for k in ("width", "height")}, []),
            "frame": {"oneOf": [obj({"kind": {"const": "world"}}, ["kind"]), obj({"kind": {"const": "part"}, "partId": integer}, ["kind", "partId"])]},
            "details": {"enum": ["auto", "none", "perGroup"], "default": "auto", "description": "auto adds a detail view for groups too small or occluded in joint views; inspect detailStatus for budget skips."}, "includeHidden": {"type": "boolean"},
            "overlays": obj({"centers": {"type": "boolean", "description": "DLL 0.4.0+: whole-aircraft native designer centers in this capture frame, irrespective of visual groups; minimum resolution 384x384."}}, [])})
    return obj(props, ["craftSessionId"])


def designer_schema():
    """Native camera screenshots, distinct from isolated CPU mesh analysis."""
    def obj(props, required=()):
        return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}
    def number(low, high, description=""):
        return {"type": "number", "minimum": low, "maximum": high, "description": description}
    presets = ["current", "front", "back", "right", "left", "top", "bottom", "isometric"]
    view = obj({
        "name": {"type": "string", "pattern": "^(?!g)(?!(?:overview|con|prn|aux|nul|com[0-9]|lpt[0-9])$)[a-z][a-z0-9-]{0,31}$"},
        "view": {"enum": [*presets, "custom", "fixed"], "default": "current"},
        "position":{"type":"array","minItems":3,"maxItems":3,"items":number(-100000,100000)},
        "direction":{"type":"array","minItems":3,"maxItems":3,"items":number(-100000,100000)},
        "up":{"type":"array","minItems":3,"maxItems":3,"items":number(-100000,100000)},
        "nearClipMetres":number(-100000,10000),"farClipMetres":number(.01,100000),
        "projection": {"enum": ["current", "perspective", "orthographic"], "default": "current"},
        "target": {"type": "array", "minItems": 3, "maxItems": 3, "items": number(-100000, 100000), "description": "World metres. Named/custom views default to focus bounds centre; current view preserves the player's target."},
        "azimuthDegrees": number(-360, 360, "custom: 0 places camera on +Z, +90 on +X, looking at target."),
        "elevationDegrees": number(-89.9, 89.9, "custom: positive places camera above target. For exact vertical use top/bottom."),
        "rollDegrees": number(-180, 180, "Rotation about the camera forward axis."),
        "distance": number(.05, 10000, "Metres from target. Omission auto-fits focus bounds for named/custom views."),
        "fieldOfViewDegrees": number(5, 140, "Vertical perspective field of view; defaults to player camera."),
        "orthographicSize": number(.01, 10000, "Orthographic half-height in metres. Only valid for orthographic projection; omission auto-fits named/custom views."),
    })
    view["allOf"] = [
        {"if":{"properties":{"view":{"const":"fixed"}},"required":["view"]},"then":{"required":["position","direction","up","target","projection","fieldOfViewDegrees","nearClipMetres","farClipMetres"]},"else":{"not":{"anyOf":[{"required":[k]} for k in ("position","direction","up","nearClipMetres","farClipMetres")]}}},
        {"if": {"properties": {"view": {"const": "custom"}}, "required": ["view"]}, "then": {"required": ["azimuthDegrees", "elevationDegrees"]},
         "else": {"not": {"anyOf": [{"required": ["azimuthDegrees"]}, {"required": ["elevationDegrees"]}]}}},
        {"if": {"anyOf": [{"not": {"required": ["view"]}}, {"properties": {"view": {"const": "current"}}}]},
         "then": {"not": {"anyOf": [{"required": [k]} for k in ("target", "distance", "rollDegrees")]}}},
        {"if": {"properties": {"projection": {"const": "perspective"}}, "required": ["projection"]}, "then": {"not": {"required": ["orthographicSize"]}}},
    ]
    return obj({
        "craftSessionId": {"type": "string", "minLength": 1},
        "expectedRevision": {"type": "integer", "minimum": 1},
        "views": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"oneOf": [{"enum": presets}, view]}, "description": "Default [current]. Named views use Unity world axes. Distinct names required. Every requested view is recommended, overview duplicates the first."},
        "focusPartIds": {"type": "array", "minItems": 1, "maxItems": 2048, "uniqueItems": True, "items": {"type": "integer", "minimum": 0}, "description": "Framing only: all visible scene objects remain rendered. Default all current craft parts. Current view does not auto-fit."},
        "resolution": {**obj({"width": {"type": "integer", "minimum": 128, "maximum": 2048}, "height": {"type": "integer", "minimum": 128, "maximum": 2048}}, ["width", "height"]), "description": "Omit to preserve native viewport aspect, longest edge up to 1280 pixels. Explicit size requires both dimensions; 16 million total pixels including the first-view overview copy."},
    }, ["craftSessionId"])
