"""Shape operation schema checks, including parity with S00 native metadata."""
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

root = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("shape_cli", root / "cli/sp2build.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
checks = []


def check(name, schema, instance, valid):
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(instance))
    checks.append({"name": name, "pass": (not errors) == valid, "expectedValid": valid})


add = cli.schema("wing.control.add", operation_only=True)
update = cli.schema("shape.update", operation_only=True)
for style, patch in [
    ("StandardFlap", {"spanRange": [1, 3], "chordFraction": [.25, .3], "maxDeflectionDegrees": 20}),
    ("FowlerFlap", {"spanRange": [.5, 2], "maxDeflectionDegrees": 40}),
    ("Slat", {"spanRange": [.5, 2], "chordFraction": [.2, .4]}),
    ("BrakeFlap", {"spanRange": [.5, 2], "brakeTopDegrees": 70, "brakeBottomDegrees": 30, "flapDeflectionDegrees": 20}),
]:
    operation = {"kind": "wing.control.add", "wingPartId": 1, "style": style, "patch": patch}
    check(style, add, operation, True)
    check(style + " shortcut parity", cli.schema("wing.control.add"), {"craftSessionId": "s", "expectedRevision": 1, "operation": {k: v for k, v in operation.items() if k != "kind"}}, True)
for name, style, patch in [
    ("readonly style", "Spoiler", {}), ("unknown style", "slat", {}),
    ("Slat chord upper bound", "Slat", {"chordFraction": [.3, .41]}),
    ("wrong style fields", "BrakeFlap", {"maxDeflectionDegrees": 20}),
    ("scalar span", "StandardFlap", {"spanRange": 2}),
    ("unknown patch key", "FowlerFlap", {"span": 2}),
]:
    check(name, add, {"kind": "wing.control.add", "wingPartId": 1, "style": style, "patch": patch}, False)
for name, patch, valid in [
    ("fuselage existing slices", {"length": 7.6, "sections": [{"index": 0, "width": 1.3, "height": 1.5, "cornerRadius": {"topLeft": .3}}]}, True),
    ("wing station replacement", {"replaceSections": [{"spanPosition": 0, "chord": 2, "offset": 0, "airfoil": "NACA2412"}, {"spanPosition": 6, "chord": 1, "offset": .7}]}, True),
    ("ambiguous length offset", {"length": 2, "offset": [0, 0, 2]}, False),
    ("wrong section index type", {"sections": [{"index": True, "width": 1}]}, False),
    ("wing field not fuselage", {"length": 3, "replaceSections": [{"spanPosition": 0}, {"spanPosition": 3}]}, False),
    ("ambiguous sections replacement", {"sections": [{"index": 1, "chord": 1}], "replaceSections": [{"spanPosition": 0}, {"spanPosition": 3}]}, False),
    ("invalid radius name", {"sections": [{"index": 0, "cornerRadius": {"upperLeft": .3}}]}, False),
    ("automatic cuts", {"sections": [{"index": 0, "cutting": {"top": None, "right": .2}}]}, True),
]:
    check(name, update, {"kind": "shape.update", "partId": 1, "patch": patch}, valid)
check("family enum", cli.schema("shape.schema"), {"family": "controlSurface"}, True)
check("family wrong native typename", cli.schema("shape.schema"), {"family": "JWing"}, False)

# Compare the advertised style fields to native codec metadata captured read-only in S00.
fixture = Path("D:/codeSpace/sp2_craft_edit/staged-build/S00/catalog/shapeschema-controlSurface.json")
if fixture.is_file():
    native = json.loads(fixture.read_text(encoding="utf-8-sig"))["data"]
    # Some read commands wrap their family object under schema.
    native = native.get("schema", native)
    for style, fields in native["styles"].items():
        typed = cli.shape_contracts_module().control(style)["properties"]
        checks.append({"name": style + " native field parity", "pass": set(typed) == set(fields) | {"spanRange", "chordFraction"}})
        checks.append({"name": style + " native numeric bounds", "pass": all(typed[k].get("minimum") == v["minimum"] and typed[k].get("maximum") == v["maximum"] for k, v in fields.items())})

directory = root / "tests/artifacts/staged-build/S00-review"
directory.mkdir(parents=True, exist_ok=True)
(directory / "shape-contract-validation.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
failed = [c for c in checks if not c["pass"]]
print(json.dumps({"passed": len(checks) - len(failed), "total": len(checks), "failures": failed}, ensure_ascii=False))
raise SystemExit(bool(failed))
