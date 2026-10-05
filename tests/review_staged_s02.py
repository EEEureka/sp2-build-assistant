"""Offline independent review of S02 complete final readbacks and corrected rays."""
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

root = Path(__file__).parents[1]
source = Path("D:/codeSpace/sp2_craft_edit/staged-build/S02/final-rev14")
load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
checks = []
def check(name, value):
    checks.append({"name":name, "pass":bool(value)})
def near(a,b,tol=1e-5):
    return len(a)==len(b) and all(abs(x-y)<tol for x,y in zip(a,b))
spec=importlib.util.spec_from_file_location("s02_contracts",root/"cli/contracts.py")
contracts=importlib.util.module_from_spec(spec); spec.loader.exec_module(contracts)
snapshot=load(source/"snapshot.json")["data"]
identity=snapshot["identity"]
for path in source.glob("*.json"):
    j=load(path)
    if "success" not in j:
        continue
    check(path.name+" successful final revision", j["success"] and j["data"].get("identity")==identity)
    name=path.name
    command=("parts.geometry" if name.startswith("geometry-") else "shape.get" if name.startswith("shape-") else "designer.raycast" if name.startswith("ray-output-") else
             {"snapshot.json":"craft.snapshot","centers-contributors.json":"craft.centers","centers-summary.json":"craft.centers","connections-structured.json":"connections.list","designer-status.json":"designer.status","history.json":"craft.history","parts-list.json":"parts.list"}.get(name))
    if command:
        errors=list(Draft202012Validator(contracts.output_schema(command)).iter_errors(j))
        check(path.name+" output schema",not errors)
parts={p["id"]:p for p in snapshot["parts"]}
check("Seven parts with a single JWing",len(parts)==7 and [i for i,p in parts.items() if p["type"]=="JWing-1"]==[7])
connections=load(source/"connections-structured.json")["data"]["connections"]
seen={3}
while True:
    added={n for c in connections if c["partA"] in seen or c["partB"] in seen for n in (c["partA"],c["partB"])}-seen
    if not added:break
    seen.update(added)
check("All seven parts connected to flight computer through six edges",seen==set(parts) and len(connections)==6)
shape=load(source/"shape-7.json")["data"]["shape"]["configuration"]
sections=shape["sections"]
check("Four stations and NACA root/tip retained",near([s["spanPosition"] for s in sections],[0,1.5,3.5,5.7]) and near([s["chord"] for s in sections],[3.1,2.7,2.05,1.4]) and sections[0]["airfoil"]=="NACA2412" and sections[-1]["airfoil"]=="NACA0012" and sections[0]["bendDegrees"]==5)
geometries={i:load(source/f"geometry-{i}.json")["data"]["geometry"] for i in parts}
wing=geometries[7]["renderers"][0]["bounds"]
body=geometries[1]["renderers"][0]["bounds"]
check("Wing root meets fuselage positive-X side",abs(wing["min"][0]-body["max"][0])<1e-5)
bounds=[r["bounds"] for g in geometries.values() for r in g["renderers"]]
width=max(b["max"][0] for b in bounds)-min(b["min"][0] for b in bounds)
check("Current single-wing width about 7.07 m, not predicted mirrored span",7.0<width<7.15)
c=load(source/"centers-contributors.json")["data"]
mass=[r for r in c["contributors"]["items"] if r["metric"]=="mass"]
total=sum(r["massKg"] for r in mass)
weighted=[sum(r["massKg"]*r["positionWorldMeters"][i] for r in mass)/total for i in range(3)]
check("Mass/CoM arithmetic within 1 micrometre",abs(total-c["centers"]["com"]["massKg"])<1e-8 and near(weighted,c["centers"]["com"]["positionWorldMeters"],1e-6))
lift=[r for r in c["contributors"]["items"] if r["metric"]=="lift"]
check("CoL is solely the included wing source",len(lift)==1 and lift[0]["part"]["id"]==7 and lift[0]["included"] and c["centers"]["col"]["status"]=="valid" and near(lift[0]["positionWorldMeters"],c["centers"]["col"]["positionWorldMeters"]))
check("Lift weight equals exposed projected area times lift scale",abs(lift[0]["nativeWeight"]-lift[0]["projectedAreaSquareMeters"]*lift[0]["liftScale"])<1e-6)
planform=sum((a["chord"]+b["chord"])/2*(b["spanPosition"]-a["spanPosition"]) for a,b in zip(sections,sections[1:]))
check("Native lift proxy within 2 percent of independent piecewise planform area",abs(lift[0]["nativeWeight"]-planform)/planform<.02)
check("Thrust remains unavailable",c["centers"]["cot"]["status"]=="unavailable" and c["centers"]["cot"]["positionWorldMeters"] is None)
old=source.parent/"final"
oldwing=load(old/"geometry-7.json")["renderers"][0]["bounds"]
delta=[a-b for a,b in zip(wing["center"],oldwing["center"])]
for letter in ("A","D"):
    oldin=load(old/f"ray-input-{letter}.json"); newin=load(source/f"ray-input-{letter}.json")
    oldout=load(old/f"ray-output-{letter}.json")["data"]; newout=load(source/f"ray-output-{letter}.json")["data"]
    check(f"Ray {letter} correctly translated input",near(newin["origin"],[a+b for a,b in zip(oldin["origin"],delta)],1e-4))
    check(f"Ray {letter} translated hit agrees within 0.1 mm",bool(oldout["hits"]) and bool(newout["hits"]) and oldout["hits"][0]["partId"]==newout["hits"][0]["partId"] and near(newout["hits"][0]["point"],[a+b for a,b in zip(oldout["hits"][0]["point"],delta)],1e-4))
report={"stage":"S02","identity":identity,"source":str(source),"passed":sum(c["pass"] for c in checks),"total":len(checks),"checks":checks,
        "boundaries":"NACA strings and generated geometry are verified, not an independent airfoil cross-section fit or native CoL gizmo/flight comparison. Planform area check is approximate, not proof of native parity."}
out=root/"tests/artifacts/staged-build/S02-review/independent-review.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({"passed":report["passed"],"total":report["total"],"failures":[c for c in checks if not c["pass"]]}))
raise SystemExit(any(not c["pass"] for c in checks))
