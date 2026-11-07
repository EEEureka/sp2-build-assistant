"""Frozen tolerances and explicit unknowns. Missing evidence is never a zero error."""
import math
from reference_storage import ReferenceError, digest


def evaluate(profile, evidence):
    if not isinstance(profile,dict) or not profile.get("frozen"):
        raise ReferenceError("profile_not_frozen","Quality evaluation needs a frozen tolerance profile")
    checksum=profile.get("contentHash")
    if checksum and digest({k:v for k,v in profile.items() if k!="contentHash"})!=checksum:
        raise ReferenceError("profile_changed","Frozen tolerance profile was modified")
    measured={m["name"]:m for m in evidence.get("metrics",[]) if "name" in m}
    results=[]
    for rule in profile.get("metrics",[]):
        item=measured.get(rule["name"])
        result={"name":rule["name"],"target":rule["target"],"unit":rule["unit"],"status":"unknown"}
        if not item or item.get("status") in ("missing","stale","partial","unknown","underconstrained"):
            result["reason"]="missing_or_unusable_evidence"
        elif item.get("unit")!=rule["unit"]:
            result["reason"]="unit_mismatch"
        elif rule.get("coverage") and item.get("coverage")!=rule["coverage"]:
            result["reason"]="coverage_mismatch"
        elif rule.get("sourceHashes") and item.get("sourceHashes")!=rule["sourceHashes"]:
            result["reason"]="reference_changed"
        else:
            value=item.get("value")
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<0:
                result["reason"]="invalid_measurement"
            else:
                interval=item.get("interval")
                if interval is not None:
                    if (not isinstance(interval,list) or len(interval)!=2 or any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in interval)
                        or interval[0]<0 or not interval[0]<=value<=interval[1] or not item.get("intervalMethod")):
                        result["reason"]="invalid_interval"
                    else:
                        result.update(value=value,interval=interval,status="pass" if interval[1]<=rule["target"] else "fail" if interval[0]>rule["target"] else "unknown",meaning="Declared uncertainty interval; method retained in evidence")
                else:
                    # Sample residuals are usable, but cannot certify a continuous/global guarantee.
                    result.update(value=value,status="pass" if value<=rule["target"] else "fail",meaning="Sample residual only; no confidence or continuous-surface bound inferred")
                if result["status"]=="pass" and (rule.get("referenceUncertainty",0)>rule["target"] or rule.get("measurementError",0)>rule["target"]):
                    result.update(status="unknown",reason="evidence_cannot_resolve_target")
        results.append(result)
    checks=evidence.get("checks",{})
    for name in profile.get("requiredChecks",[]):
        value=checks.get(name)
        results.append({"name":name,"status":"pass" if value is True else "fail" if value is False else "unknown","reason":None if isinstance(value,bool) else "missing_check"})
    if not results:raise ReferenceError("invalid_profile","A profile must contain at least one metric or required check")
    status="fail" if any(r["status"]=="fail" for r in results) else "unknown" if any(r["status"]=="unknown" for r in results) else "pass"
    return {"status":status,"profileId":profile.get("id"),"profileHash":checksum,"results":results,
            "limitations":evidence.get("limitations",[]),"identity":evidence.get("identity")}
