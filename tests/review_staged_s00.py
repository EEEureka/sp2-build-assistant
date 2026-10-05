"""Independent review of the DSH S00 evidence; never contacts or writes the game."""
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

root = Path(__file__).parents[1]
source = Path("D:/codeSpace/sp2_craft_edit/staged-build/S00")
spec = importlib.util.spec_from_file_location("s00_contracts", root / "cli/contracts.py")
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)
load = lambda name: json.loads((source / name).read_text(encoding="utf-8-sig"))
checks = []
for path, command in {
    "designer-status.json": "designer.status", "capabilities.json": "capabilities",
    "snapshot.json": "craft.snapshot", "snapshot-final.json": "craft.snapshot",
    "selection.json": "designer.selection", "selection-final.json": "designer.selection",
    "structured-connections-list.json": "connections.list", "structured-variables-list.json": "variables.list", "structured-outputs-list.json": "outputs.list",
    "centers/summary.json": "craft.centers", "centers/contributors-mass.json": "craft.centers",
    "centers/after-noedit.json": "craft.centers", "centers/with-images.json": "craft.centers",
}.items():
    errors = list(Draft202012Validator(contracts.output_schema(command)).iter_errors(load(path)))
    checks.append({"name": path + " output schema", "pass": not errors, "errors": [e.message for e in errors]})
before, after = load("snapshot.json")["data"], load("snapshot-final.json")["data"]
checks.append({"name": "Actual nonempty XML unchanged", "pass": len(before["xml"]) > 0 and before["xml"] == after["xml"]})
checks.append({"name": "Identity unchanged", "pass": before["identity"] == after["identity"]})
checks.append({"name": "Selection unchanged", "pass": load("selection.json")["data"] == load("selection-final.json")["data"]})
centers = load("centers/contributors-mass.json")["data"]
rows = centers["contributors"]["items"]
total = sum(r["massKg"] for r in rows)
weighted = [sum(r["massKg"] * r["positionWorldMeters"][axis] for r in rows) / total for axis in range(3)]
checks.append({"name": "Mass contributor arithmetic", "pass": abs(total - centers["centers"]["com"]["massKg"]) < 1e-8 and all(abs(a-b) < 1e-8 for a,b in zip(weighted, centers["centers"]["com"]["positionWorldMeters"]))})
checks.append({"name": "Absent lift and thrust sources unavailable", "pass": all(centers["centers"][k]["status"] == "unavailable" and centers["centers"][k]["positionWorldMeters"] is None for k in ("col", "cot"))})
comparison = load("centers/after-noedit.json")["data"]["comparison"]
checks.append({"name": "Unedited comparison", "pass": comparison["status"] == "comparable" and comparison["centerChanges"]["com"]["deltaMeters"] == [0,0,0]})
images = load("centers/with-images.json")["data"]
manifest = json.loads(Path(images["visual"]["manifestPath"]).read_text(encoding="utf-8-sig"))
checks.append({"name": "Same-sample image report", "pass": images["analysisId"] == manifest["centersReport"]["analysisId"] and images["geometryStamp"] == images["visual"]["geometryStamp"] == manifest["geometryStamp"] and images["identity"] == manifest["identity"]})
checks.append({"name": "No invalid lift/thrust marker", "pass": all([m["center"] for m in v["centersOverlay"]["markers"]] == ["com"] for v in manifest["views"])})
record = {"stage": "S00", "checks": checks, "passed": sum(c["pass"] for c in checks), "total": len(checks), "source": str(source), "visualReview": "Coordinator opened overview.png separately; no native gizmo comparison or flight test performed."}
out = root / "tests/artifacts/staged-build/S00-review/independent-review.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
failed = [c for c in checks if not c["pass"]]
print(json.dumps({"passed": record["passed"], "total": record["total"], "failures": failed}, ensure_ascii=False))
raise SystemExit(bool(failed))
