"""Semantic structure scope and immutable tolerance profiles."""
from copy import deepcopy
import math
from reference_storage import ReferenceError, digest


def part_ids(values, name="partIds"):
    if not isinstance(values, list) or any(isinstance(x,bool) or not isinstance(x,int) or x < 0 for x in values) or len(set(values)) != len(values):
        raise ReferenceError("invalid_input", "Expected unique nonnegative part IDs", field=name)
    return values


def validate_structure(value):
    if not isinstance(value,dict) or not isinstance(value.get("id"),str) or not value["id"].strip():
        raise ReferenceError("invalid_input", "Structure requires a nonempty id")
    ids=set(part_ids(value.get("partIds",[])))
    locked=set(part_ids(value.get("lockedPartIds",[]),"lockedPartIds"))
    if not locked <= ids:
        raise ReferenceError("invalid_scope", "Locked parts must belong to the structure")
    seen=set()
    for role in value.get("roles",[]):
        if not role.get("role") or role["role"] in seen:
            raise ReferenceError("invalid_scope", "Role names must be nonempty and unique")
        seen.add(role["role"])
        if not set(part_ids(role.get("partIds",[]))) <= ids:
            raise ReferenceError("invalid_scope", "Role parts must belong to the structure", role=role["role"])
    if set(value.get("sourceIds",[])) & set(value.get("excludedSourceIds",[])):
        raise ReferenceError("reference_conflict", "Included and excluded source IDs overlap")
    return value


def freeze_profile(profile):
    value=deepcopy(profile)
    if not value.get("id") or not isinstance(value.get("metrics"),list) or not value["metrics"]:
        raise ReferenceError("invalid_input", "Tolerance profile needs id and nonempty metrics")
    names=set()
    for metric in value["metrics"]:
        name=metric.get("name")
        if not name or name in names or metric.get("target") is None or not metric.get("unit"):
            raise ReferenceError("invalid_input", "Each tolerance needs unique name, target and unit")
        names.add(name)
        if isinstance(metric["target"],bool) or not isinstance(metric["target"],(float,int)) or not math.isfinite(metric["target"]) or metric["target"] < 0:
            raise ReferenceError("invalid_input", "Tolerance cannot be negative")
        for key in ("referenceUncertainty","measurementError"):
            if key in metric and (isinstance(metric[key],bool) or not isinstance(metric[key],(float,int)) or not math.isfinite(metric[key]) or metric[key] < 0):
                raise ReferenceError("invalid_input", "Uncertainty must be nonnegative", field=key)
    value["frozen"]=True
    value["contentHash"]=digest({k:v for k,v in value.items() if k!="contentHash"})
    return value
