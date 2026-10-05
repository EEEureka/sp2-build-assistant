"""Independent S01 review of coordinator readbacks, DSH evidence and actual mesh bounds."""
import json
from pathlib import Path

root = Path(__file__).parents[1]
source = root / "tests/artifacts/staged-build/S01-review"
dsh = Path("D:/codeSpace/sp2_craft_edit/staged-build/S01")
load = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))["data"]
checks = []
def check(name, value):
    checks.append({"name": name, "pass": bool(value)})
def near(a, b, tolerance=1e-5):
    return len(a) == len(b) and all(abs(x-y) <= tolerance for x,y in zip(a,b))

before, after = [load(source / n) for n in ("snapshot-before.json", "snapshot-after.json")]
check("Read-only review preserved nonempty XML and identity", bool(before["xml"]) and before["xml"] == after["xml"] and before["identity"] == after["identity"])
check("Current craft has exactly original computer and five fuselages", before["partCount"] == 6 and {p["id"] for p in before["parts"]} == {1,2,3,4,5,6})
geometries = {i: load(source / f"geometry-{i}.json") for i in range(1,7)}
check("All independent geometry samples share one revision", all(g["identity"] == before["identity"] for g in geometries.values()))
lengths = {1:6., 2:2.2, 4:1.1, 5:1.6, 6:.8}
intervals = []
for i, length in lengths.items():
    shape = load(source / f"shape-{i}.json")
    check(f"Part {i} requested length", abs(shape["shape"]["configuration"]["length"] - length) < 1e-5)
    check(f"Part {i} shape identity matches", shape["identity"] == before["identity"])
    g = geometries[i]["geometry"]
    mesh = g["renderers"][0]["bounds"]
    cols = [c for c in g["colliders"] if c["type"] == "MeshCollider"]
    check(f"Part {i} mesh/collider bounds match", bool(cols) and any(near(c["bounds"]["min"], mesh["min"]) and near(c["bounds"]["max"], mesh["max"]) for c in cols))
    check(f"Part {i} bounds match configured length", abs(mesh["size"][2] - length) < 1e-5)
    intervals.append((mesh["min"][2], mesh["max"][2]))
intervals.sort()
check("Adjacent segments meet without axial gaps", all(abs(intervals[i][1] - intervals[i+1][0]) < 1e-5 for i in range(4)))
check("Whole fuselage length 11.7 m", abs(intervals[-1][1]-intervals[0][0]-11.7) < 1e-5)
c = load(source / "centers.json")
check("All six parts included in native connected scope", c["scope"]["connectedPartCount"] == 6 and c["scope"]["disconnectedPartCount"] == 0)
rows = c["contributors"]["items"]
total = sum(r["massKg"] for r in rows)
center = [sum(r["massKg"]*r["positionWorldMeters"][i] for r in rows)/total for i in range(3)]
# Float32 native positions are serialized with shorter decimal representations than
# the double-precision aggregate; use a one-micrometre positional tolerance.
check("Whole mass and weighted CoM agree within 1 micrometre", abs(total-c["centers"]["com"]["massKg"]) < 1e-8 and near(center,c["centers"]["com"]["positionWorldMeters"],1e-6))
check("No fabricated lift/thrust center", all(c["centers"][k]["status"] == "unavailable" and c["centers"][k]["positionWorldMeters"] is None for k in ("col","cot")))
capture = load(dsh / "visual-capture.json")
manifest = json.loads(Path(capture["manifestPath"]).read_text(encoding="utf-8-sig"))
check("DSH image capture matches independently reread craft", capture["identity"] == before["identity"] and not capture["staleAtDelivery"] and manifest["identity"] == before["identity"])
early = load(dsh / "centers-after-connect.json")
early_mass = {r["part"]["id"]:r["massKg"] for r in early["contributors"]["items"]}
final_mass = {r["part"]["id"]:r["massKg"] for r in rows}
check("Cone mass changes were already present at revision 7", early["identity"]["revision"] == 7 and all(abs(early_mass[i]/final_mass[i]-2) < 1e-5 for i in (4,6)))
report = {"stage":"S01", "checks":checks, "passed":sum(c["pass"] for c in checks), "total":len(checks), "identity":before["identity"],
          "visualReview":"Coordinator opened DSH overview.png; continuous fuselage. No flight or front-view fine-detail acceptance.",
          "feedbackCorrection":"Revision 7 contributor mass already includes the larger cones. This contradicts DSH's claim that its revision 7 read matched submitted cone dimensions; it does not prove a late geometry-settle failure. Revision 8 has a separate Craft Repositioned step."}
(source / "independent-review.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"passed":report["passed"],"total":report["total"],"failures":[c for c in checks if not c["pass"]]}))
raise SystemExit(any(not c["pass"] for c in checks))
