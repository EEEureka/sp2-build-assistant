"""Bounded parameter domains and explicitly typed native operation bindings."""
import hashlib
import json
import math


def validate_parameters(parameters):
    if not isinstance(parameters, list) or not 1 <= len(parameters) <= 32:
        raise ValueError("fit needs 1..32 scalar parameters")
    seen, normalized = set(), []
    for parameter in parameters:
        name = parameter.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("fit parameter names must be unique")
        seen.add(name)
        value, lower, upper = (parameter.get(k) for k in ("value", "min", "max"))
        if not all(type(x) in (int, float) and math.isfinite(x) for x in (value, lower, upper)) or not lower <= value <= upper or lower > upper:
            raise ValueError("fit parameters need finite min <= value <= max")
        frozen = bool(parameter.get("frozen", False)) or lower == upper
        normalized.append({**parameter, "frozen": frozen})
    return normalized


def validate_proxy(calibration, parameters, game_version=None, shape_family=None):
    if not calibration:
        return {"valid": False, "reason": "proxy_calibration_missing"}
    if not calibration.get("validated") or not calibration.get("nativeEvidence"):
        return {"valid": False, "reason": "native_calibration_evidence_missing"}
    if game_version is not None and calibration.get("gameVersion") != game_version:
        return {"valid": False, "reason": "proxy_game_version_mismatch"}
    if shape_family is not None and calibration.get("shapeFamily") != shape_family:
        return {"valid": False, "reason": "proxy_shape_family_mismatch"}
    error, budget = calibration.get("maxError"), calibration.get("errorBudget")
    if type(error) not in (int, float) or type(budget) not in (int, float) or not 0 <= error <= budget or not math.isfinite(error) or not math.isfinite(budget):
        return {"valid": False, "reason": "proxy_error_exceeds_budget"}
    domains = calibration.get("domains", {})
    for p in parameters:
        domain = domains.get(p["name"])
        if not isinstance(domain, list) or len(domain) != 2 or not domain[0] <= p["min"] <= p["max"] <= domain[1]:
            return {"valid": False, "reason": "proxy_parameter_outside_validated_domain", "parameter": p["name"]}
    return {"valid": True, "reason": "native_calibration_within_declared_domain", "error": error, "budget": budget}


def native_operations(parameters, values):
    """No arbitrary JSON templating: only known numeric property/shape/translation fields."""
    translations, properties, shapes = {}, {}, {}
    for p in parameters:
        if p["frozen"]:
            continue
        binding = p.get("binding")
        if not binding:
            continue
        value = float(values[p["name"]])
        kind = binding.get("kind")
        if kind == "translation":
            parts = binding.get("partIds")
            axis = binding.get("axis")
            if not isinstance(parts, list) or not parts or any(type(i) is not int or i < 0 for i in parts) or axis not in ("x", "y", "z"):
                raise ValueError("translation binding needs native partIds and axis x/y/z")
            key = tuple(sorted(set(parts)))
            vector = translations.setdefault(key, [0., 0., 0.])
            vector["xyz".index(axis)] += value - p["value"]
        elif kind == "property":
            part, field = binding.get("partId"), binding.get("propertyId")
            if type(part) is not int or part < 0 or not isinstance(field, str) or not field:
                raise ValueError("property binding needs partId and discovered propertyId")
            patch = properties.setdefault(part, {})
            if field in patch:
                raise ValueError("multiple fit parameters bind the same property")
            patch[field] = value
        elif kind == "fuselageSection":
            part, index, field = binding.get("partId"), binding.get("sectionIndex"), binding.get("field")
            if type(part) is not int or part < 0 or type(index) is not int or index < 0 or field not in ("width", "height", "trapezium"):
                raise ValueError("fuselageSection binding requires partId/sectionIndex and width/height/trapezium")
            sections = shapes.setdefault(part, {})
            patch = sections.setdefault(index, {"index": index})
            if field in patch:
                raise ValueError("multiple fit parameters bind the same shape field")
            patch[field] = value
        else:
            raise ValueError("unsupported native fit parameter binding")
    operations = [{"kind": "transform.apply", "partIds": list(key), "mode": "delta", "translation": vector, "symmetric": False}
                  for key, vector in translations.items() if any(abs(v) > 1e-12 for v in vector)]
    operations.extend({"kind": "properties.set", "partId": part, "patch": patch, "symmetric": False} for part, patch in properties.items())
    operations.extend({"kind": "shape.update", "partId": part, "patch": {"sections": list(sections.values())}, "symmetric": False} for part, sections in shapes.items())
    return operations


def freeze_plan(payload):
    parameters = validate_parameters(payload["parameters"])
    frozen = {"planSchemaVersion": 1, "parameters": parameters, "model": payload["model"],
              "identity": payload.get("identity"), "geometryStamp": payload.get("geometryStamp"),
              "tolerances": payload.get("tolerances", {}), "proxyCalibration": payload.get("proxyCalibration"),
              "gameVersion": payload.get("gameVersion"), "shapeFamily": payload.get("shapeFamily"),
              "requireNativePrecision": bool(payload.get("requireNativePrecision", False)),
              "budget": payload.get("budget", {"maxEvaluations": 100}), "frozenPartIds": payload.get("frozenPartIds", []),
              "validation": payload.get("validation")}
    frozen["planHash"] = hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return frozen


def check_plan(plan):
    digest = plan.get("planHash")
    canonical = {k: v for k, v in plan.items() if k != "planHash"}
    actual = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if not isinstance(digest, str) or digest != actual:
        raise ValueError("immutable fit plan hash mismatch")
    return plan
