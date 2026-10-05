"""Validate schemas and captured/live READ-ONLY outputs. Dev dependency: jsonschema.

Run with --live to collect through the installed global CLI. No captures,
checkpoints, writes or recovery operations are submitted.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from copy import deepcopy
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("cli", ROOT / "cli/sp2build.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
contracts = cli.contracts_module()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fixtures-dir", type=Path, default=ROOT / "tests/artifacts/contracts-0.3.1")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ("tests/artifacts/contracts-" + cli.VERSION))
    args = parser.parse_args()
    artifact = args.output_dir
    fixtures = artifact if args.live else args.fixtures_dir
    artifact.mkdir(parents=True, exist_ok=True)
    reports = []

    def validate(name, schema, result):
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(result))
        reports.append({"name": name, "pass": not errors, "errors": [f"{list(e.absolute_path)}: {e.message}" for e in errors[:5]]})

    for name in cli.command_names():
        schema = contracts.output_schema("batch.apply" if name in cli.ALIASES else name)
        if schema is not None:
            Draft202012Validator.check_schema(schema)
            validate(name + " failure", schema, {"success": False, "schemaVersion": "1", "error": {"code": "example", "message": "test"}})
        Draft202012Validator.check_schema(cli.schema(name))
    for name in cli.OP_SCHEMAS:
        Draft202012Validator.check_schema(cli.schema(name, operation_only=True))
    for mode, schema in contracts.auxiliary_schemas().items():
        if mode.endswith("Schema"):
            Draft202012Validator.check_schema(schema)
    validate("async acknowledgement", contracts.auxiliary_schemas()["asyncOutputSchema"], cli.ok({"operationId": "test", "state": "queued", "createdAt": "2026-10-02T00:00:00Z", "result": None, "instancePid": 1}))
    validate("saved output receipt", contracts.auxiliary_schemas()["savedOutputSchema"], cli.ok({"path": "test.json", "sha256": "abc", "resultSuccess": False}))
    for argv in (["commands", "list"], ["commands", "schema", "--command", "parts.get"],
                 ["commands", "schema", "--operation", "connection.connect"], ["version"], ["skill", "path"]):
        result, _ = cli.execute(argv)
        command = ".".join(argv[:2]) if len(argv) > 1 else argv[0]
        validate("local " + command, contracts.output_schema(command), result)

    if args.live:
        executable = shutil.which("sp2build")
        if not executable:
            raise SystemExit("Global sp2build is required; refresh User PATH first")

        def call(name, extra=()):
            process = subprocess.run([executable, *name.split("."), *extra, "--json"], capture_output=True, timeout=45)
            result = json.loads(process.stdout.decode("utf-8-sig"))
            (artifact / (name + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            validate("live " + name, contracts.output_schema(name), result)
            if not result["success"]:
                reports.append({"name": name + " live success", "pass": False, "errors": [result.get("error")]})
            return result.get("data", {})

        snapshot = call("craft.snapshot")
        part = snapshot["parts"][0]
        for name, extra in [
            ("designer.status", ()), ("capabilities", ()), ("designer.selection", ()),
            ("parts.get", ("--id", str(part["id"]))), ("parts.list", ("--limit", "3")),
            ("parts.geometry", ("--id", str(part["id"]))), ("connections.points", ("--part", str(part["id"]))),
            ("connections.list", ()), ("designer.raycast", ("--origin", "[-2.252139,3,-1.233502]", "--direction", "[0,1,0]", "--distance", "4")),
            ("spatial.query", ("--part-a", str(part["id"]), "--part-b", str(snapshot["parts"][1]["id"]))),
            ("variables.list", ()), ("outputs.list", ("--part", str(part["id"]))),
            ("shape.get", ("--id", str(part["id"]))), ("shape.schema", ("--family", "fuselage")),
            ("symmetry.get", ()), ("craft.history", ()), ("craft.checkpoint.list", ()),
            ("catalog.categories", ()), ("catalog.list", ("--limit", "2")),
            ("catalog.schema", ("--type", part["type"])), ("funky.describe", ("--name", "clamp")),
            ("funky.validate", ("--expression", "clamp(Throttle,0,1)")),
        ]:
            call(name, extra)
    else:
        for path in sorted(fixtures.glob("*.json")):
            if path.stem in contracts.OUTPUTS:
                validate("fixture " + path.stem, contracts.output_schema(path.stem), json.loads(path.read_text(encoding="utf-8-sig")))

    # A real prior capture exercises the completed visual envelope without
    # creating a new capture that could evict another agent's retained images.
    old = ROOT / "tests/artifacts/visual-whole-result.json"
    if old.exists():
        validate("retained visual capture", contracts.output_schema("visual.capture"), json.loads(old.read_text(encoding="utf-8-sig")))
    part_fixture = fixtures / "parts.get.json"
    if part_fixture.exists():
        correct = json.loads(part_fixture.read_text(encoding="utf-8"))
        wrong_path = deepcopy(correct)
        wrong_path["data"]["partInfo"] = wrong_path["data"].pop("part")
        wrong_type = deepcopy(correct)
        wrong_type["data"]["part"]["id"] = "not-an-integer"
        missing_error = {"success": False, "schemaVersion": "1"}
        for name, data in [("reject incorrect part path", wrong_path), ("reject incorrect ID type", wrong_type), ("reject error without details", missing_error)]:
            errors = list(Draft202012Validator(contracts.output_schema("parts.get")).iter_errors(data))
            reports.append({"name": name, "pass": bool(errors), "errors": []})
    (artifact / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [r for r in reports if not r["pass"]]
    print(json.dumps({"passed": len(reports)-len(failures), "total": len(reports), "failures": failures}, ensure_ascii=False, indent=2))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
