"""Offline positive/negative contract fixtures, not DLL runtime acceptance.

Uses retained native variable outputs to exercise nonempty bindings. Requires
the developer-only jsonschema dependency, as does validate_contracts.py.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "cli"))
import contracts


def main():
    previous = json.loads((ROOT / "tests/artifacts/live-0.3.1-20261002/dsh-variable-bindings.json").read_text(encoding="utf-8-sig"))["data"]
    native = next(s for s in previous["sources"] if s["outputs"] and any(m["bindings"] for m in s["outputs"]))
    source = {"partId": native["partId"], "type": "FixtureType", "typeName": "Fixture type", "name": "Schema fixture", "modifiers": native["outputs"]}
    common = {"identity": previous["identity"], "view": "structured", "meaning": "Offline schema fixture; not a live response."}
    connection = {"partA": 1, "partB": 2, "attachPointsA": [0, 1], "attachPointsB": [2]}
    setter = {"index": 0, "variable": "Test", "function": "clamp(Throttle,0,1)", "priority": 0, "activator": None}
    cases = {
        "connections.list": {**common, "connections": [connection], "count": 1},
        "variables.list": {**common, "setters": [setter], "setterCount": 1, "sources": [source], "sourceCount": 1},
        "outputs.list": {**common, "sources": [source], "sourceCount": 1},
    }
    results = []

    def check(command, label, data, expected):
        envelope = {"success": True, "schemaVersion": "1", "data": data}
        validator = Draft202012Validator(contracts.output_schema(command))
        accepted = validator.is_valid(envelope)
        results.append({"name": label, "pass": accepted == expected, "accepted": accepted, "expected": expected})

    for command, data in cases.items():
        check(command, command + " accepts nonempty typed view", data, True)
        changed = deepcopy(data)
        changed["view"] = "legacy"
        check(command, command + " rejects false mode tag", changed, False)
    invalid = deepcopy(cases["connections.list"])
    invalid["connections"][0]["attachPointsA"][0] = "0"
    check("connections.list", "rejects string attach-point IDs", invalid, False)
    invalid = deepcopy(cases["variables.list"])
    invalid["setters"][0]["index"] = "0"
    check("variables.list", "rejects string setter index", invalid, False)
    invalid = deepcopy(cases["outputs.list"])
    invalid["sources"][0]["outputs"] = invalid["sources"][0].pop("modifiers")
    check("outputs.list", "rejects legacy output-source path in structured mode", invalid, False)
    invalid = deepcopy(cases["outputs.list"])
    modifier = next(m for m in invalid["sources"][0]["modifiers"] if m["bindings"])
    modifier["bindings"][0]["priority"] = "0"
    check("outputs.list", "rejects untyped output-binding priority", invalid, False)
    output = ROOT / "tests/artifacts/contracts-0.3.2"
    output.mkdir(parents=True, exist_ok=True)
    (output / "structured-offline.json").write_text(json.dumps({"runtimeAcceptance": False, "cases": cases, "checks": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [r for r in results if not r["pass"]]
    print(json.dumps({"passed": len(results) - len(failures), "total": len(results), "failures": failures}))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
