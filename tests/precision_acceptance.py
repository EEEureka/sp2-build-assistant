"""Evidence harness: invoke only the globally installed sp2build command.

Read probes do not mutate aircraft. Write suites require a named native-UI test
copy and fresh guarded identity. Reports separate executed checks from planned
T/E acceptance; this harness alone does not prove native UI appearance parity.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import threading
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent / "artifacts" / "precision-0.5.0"
CLI = shutil.which("sp2build") or str(Path.home() / ".sp2build/bin/sp2build.cmd")

class Run:
    def __init__(self, name):
        self.root = ROOT / name
        self.root.mkdir(parents=True, exist_ok=True)
        self.calls = []
        self.checks = []
        self._evidence_lock = threading.RLock()

    def call(self, label, command, args=None, images=False, extra_args=()):
        payload = self.root / (label + ".input.json")
        output = self.root / (label + ".json")
        argv = [CLI, *command.split("."), "--output", str(output), "--timeout", "120"]
        if os.environ.get("SP2BUILD_TEST_INSTANCE"):
            argv += ["--instance", os.environ["SP2BUILD_TEST_INSTANCE"]]
        if args is not None:
            payload.write_text(json.dumps(args, ensure_ascii=False, indent=2), encoding="utf-8")
            argv += ["--input", str(payload)]
        if images:
            argv += ["--output-dir", str(self.root / label)]
        argv += list(extra_args)
        start = time.perf_counter()
        proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=140)
        elapsed = time.perf_counter() - start
        if proc.stderr:
            (self.root / (label + ".stderr.log")).write_text(proc.stderr, encoding="utf-8")
        if output.exists():
            result = json.loads(output.read_text(encoding="utf-8-sig"))
        else:
            try: result = json.loads(proc.stdout)
            except (ValueError, TypeError): result = {"success": False,"error":{"code":"harness_no_output","message":proc.stderr or proc.stdout}}
            # Early CLI validation intentionally does not create --output files.
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        row={"label":label,"command":command,"seconds":elapsed,"exitCode":proc.returncode,"success":result.get("success"),"error":result.get("error",{}).get("code"),"argv":argv,"async":"--async" in extra_args}
        with self._evidence_lock:
            self.calls.append(row)
            self.save()
            print(json.dumps(row, ensure_ascii=False), flush=True)
        return result

    def check(self, label, passed, detail=None):
        with self._evidence_lock:
            self.checks.append({"check":label,"status":"pass" if passed else "fail","details":detail})
            self.save()

    def save(self):
        (self.root / "checks.json").write_text(json.dumps({"calls":self.calls,"checks":self.checks,"meaning":"Executed checks only; not full release acceptance."}, ensure_ascii=False, indent=2), encoding="utf-8")

def probe(run):
    before=run.call("before", "craft.snapshot", {"includeXml":True})
    if not before.get("success"):
        return
    data=before["data"]
    run.check("test_copy_is_open",data["name"].startswith("SP2Build 050 Precision Lab"),data["name"])
    identity=data["identity"]
    run.call("history-before","craft.history")
    run.call("selection-before","designer.selection")
    xml=ET.fromstring(data["xml"])
    representatives={}
    for part in xml.findall("./Assembly/Parts/Part"):
        representatives.setdefault(part.attrib["partType"],int(part.attrib["id"]))
    for index,(kind,part_id) in enumerate(sorted(representatives.items())):
        result=run.call(f"type-{index:03}","properties.get",{"id":part_id,"limit":1000})
        run.check("live_type:"+kind,result.get("success",False),result.get("error"))
    for index,views in enumerate((["current"],[{"view":x,"projection":"orthographic"} for x in ("front","right","top")]+[{"view":"isometric","projection":"perspective"}])):
        result=run.call(f"capture-{index}","designer.capture",{"craftSessionId":identity["craftSessionId"],"expectedRevision":identity["revision"],"views":views,"resolution":{"width":1280,"height":800}},images=True)
        run.check("capture:"+str(index),result.get("success",False),result.get("error"))
    after=run.call("after","craft.snapshot",{"includeXml":True})
    run.check("read_queries_preserve_fingerprint",after.get("data",{}).get("identity",{}).get("fingerprint")==identity["fingerprint"])
    run.call("history-after","craft.history")
    run.call("selection-after","designer.selection")

def property_writes(run):
    baseline=run.call("baseline","craft.snapshot",{"includeXml":True})
    if not baseline.get("success") or not baseline["data"]["name"].startswith("SP2Build 050 Precision Lab"):
        raise RuntimeError("Write test requires the explicitly saved native-UI lab copy.")
    examples=[(76,"ProceduralWindow[0].height",0.72),(215,"TextDecal[0].FontSize",32),
              (218,"TextureDecal[0].Opacity",0.6),(129,"JetEngineShroud[0].length",1.1),
              (293,"Piston[0].speed",0.6),(180,"GearLeg[0].size",2.4)]
    for i,(pid,field,value) in enumerate(examples):
        label=f"case-{i}"
        state=run.call(label+"-before","craft.snapshot",{"includeXml":True})["data"]
        native=run.call(label+"-property-before","properties.get",{"id":pid,"fields":[field]})
        ident=state["identity"]
        result=run.call(label+"-apply","batch.apply",{"craftSessionId":ident["craftSessionId"],"expectedRevision":ident["revision"],"requestId":uuid.uuid4().hex,
            "operations":[{"kind":"properties.set","partId":pid,"patch":{field:value},"symmetric":False}]})
        run.check(label+" applies",result.get("success",False),result.get("error"))
        if result.get("success"):
            changed=run.call(label+"-property-after","properties.get",{"id":pid,"fields":[field]})
            fields=changed.get("data",{}).get("parts",[{}])[0].get("fields",[])
            run.check(label+" effective value",len(fields)==1 and abs(fields[0]["value"]-value)<1e-6,fields)
            now=run.call(label+"-status","designer.status")["data"]
            if now["identity"]["stateUncertain"] or now["sceneIntegrity"]["status"]!="healthy":
                raise RuntimeError("Unsafe state: stop write tests.")
            rid=now["identity"]
            restored=run.call(label+"-rollback","craft.rollback",{"craftSessionId":rid["craftSessionId"],"expectedRevision":rid["revision"],"requestId":uuid.uuid4().hex,"checkpointId":result["data"]["beforeCheckpointId"]})
            run.check(label+" rollback",restored.get("success",False),restored.get("error"))
            if not restored.get("success"):
                raise RuntimeError("Rollback did not pass: stop write tests.")
        elif not result.get("rollbackResult",{}).get("restored",False):
            raise RuntimeError("Failed operation did not confirm restoration: stop write tests.")
        final=run.call(label+"-property-restored","properties.get",{"id":pid,"fields":[field]})
        run.check(label+" original value restored",final.get("data",{}).get("parts")==native.get("data",{}).get("parts"))
    run.call("final","designer.status")

def precision_probe(run):
    run.call("status","designer.status")
    snapshot=run.call("baseline","craft.snapshot",{"includeXml":True})["data"]
    if not snapshot["name"].startswith("SP2Build 050 Precision Lab"):
        raise RuntimeError("Explicit native-UI lab copy required.")
    identity=snapshot["identity"]
    guard={"craftSessionId":identity["craftSessionId"],"expectedRevision":identity["revision"]}
    run.call("appearance","appearance.get",{"partIds":[4,76,129,218]})
    for category in ("textures","decals","propertyChoices"):
        run.call("resources-"+category,"resources.list",{"category":category,"partId":180,"limit":1000})
    run.call("group","groups.resolve",{**guard,"selector":{"kind":"parts","partIds":[76,218]}})
    run.call("decal-pose","decal.pose.get",{"id":218})
    run.call("distance","geometry.measure",{**guard,"partIdsA":[76],"partIdsB":[129],"export":True})
    run.call("section","geometry.section",{**guard,"partIds":[76],"frame":{"kind":"part","partId":76},"plane":{"origin":[0,0,0],"normal":[0,1,0]},"export":True})
    capture=run.call("native","designer.capture",{**guard,"focusPartIds":[76,77,78,79],"views":[{"view":"front","projection":"orthographic"},{"view":"right","projection":"orthographic"},{"view":"custom","azimuthDegrees":35,"elevationDegrees":20,"projection":"perspective"}],"resolution":{"width":1280,"height":800}},images=True)
    if capture.get("success"):
        repeat=run.call("native-repeat","designer.capture",{**guard,"views":capture["data"]["repeatableViews"],"resolution":capture["data"]["repeatableResolution"]},images=True)
        def relevant_camera(view):
            camera=dict(view["camera"])
            camera.pop("targetTextureInstanceId",None)  # Every capture owns a temporary render target.
            camera.pop("orthographicSize" if camera["projection"]=="perspective" else "fieldOfViewDegrees",None)
            return camera
        run.check("fixed view retains all active projection and pose fields",repeat.get("success") and [relevant_camera(v) for v in repeat["data"]["views"]]==[relevant_camera(v) for v in capture["data"]["views"]])
    run.call("final-read","craft.snapshot",{"includeXml":True})

def precision_writes(run):
    baseline=run.call("baseline","craft.snapshot",{"includeXml":True})["data"]
    if not baseline["name"].startswith("SP2Build 050 Precision Lab"):
        raise RuntimeError("Explicit native-UI lab copy required.")
    examples=[
        ("window",[{"kind":"properties.set","partId":76,"patch":{"ProceduralWindow[0].height":.77},"symmetric":False}]),
        ("glass",[{"kind":"properties.set","partId":76,"patch":{"Transparency[0].opacity":.35},"symmetric":False}]),
        ("rigid-delta",[{"kind":"transform.apply","partIds":[76,218],"frame":{"kind":"world"},"mode":"delta","translation":[.012,0,0],"rotationQuaternion":[0,0,0,1],"symmetric":False}]),
        ("merge",[{"kind":"part.update","partId":pid,"changes":[{"path":"Part","attribute":"name","value":"Precision temporary "+str(pid)}],"symmetric":False} for pid in (76,77,129,218)]),
    ]
    appearance=run.call("appearance-before","appearance.get",{"partIds":[4]})["data"]
    slot=next(x for x in appearance["parts"][0]["slots"] if x["assignable"])
    examples.append(("material",[{"kind":"appearance.set","mode":"clone","materialId":slot["materialId"],"partIds":[4],"slots":[slot["slot"]],"patch":{"name":"Precision local test","style":"SolidColor","colors":[{"index":0,"rgba":[1,.1,.2,1]}],"metallic":.1,"smoothness":.3}}]))
    for name,ops in examples:
        before=run.call(name+"-before","craft.snapshot",{"includeXml":True})["data"]
        ident=before["identity"];guard={"craftSessionId":ident["craftSessionId"],"expectedRevision":ident["revision"]}
        run.call(name+"-preview","batch.preview",{**guard,"operations":ops})
        result=run.call(name+"-apply","batch.apply",{**guard,"requestId":uuid.uuid4().hex,"operations":ops})
        run.check(name+" committed",result.get("success"),result.get("error"))
        after=run.call(name+"-after","craft.snapshot",{"includeXml":True})["data"]
        if after["identity"]["stateUncertain"]:raise RuntimeError("Uncertain state; stop writes.")
        if result.get("success"):
            if name=="rigid-delta":
                old={p["id"]:p for p in before["parts"]};new={p["id"]:p for p in after["parts"]}
                run.check("12 mm world delta independent check",all(abs(new[i]["position"][j]-old[i]["position"][j]-(.012 if j==0 else 0))<.0001 for i in (76,218) for j in range(3)))
            if name=="merge":run.check("four data edits one rebuild",result["data"]["rebuildCount"]==1)
            run.call(name+"-diff","craft.diff",{"checkpointId":result["data"]["beforeCheckpointId"]})
            if name=="material":run.call(name+"-appearance","appearance.get",{"partIds":[4,5,6]})
            now=after["identity"]
            restored=run.call(name+"-rollback","craft.rollback",{"craftSessionId":now["craftSessionId"],"expectedRevision":now["revision"],"requestId":uuid.uuid4().hex,"checkpointId":result["data"]["beforeCheckpointId"]})
            run.check(name+" rollback",restored.get("success"),restored.get("error"))
            if not restored.get("success"):raise RuntimeError("Rollback failed; stop writes.")
        elif not result.get("rollbackResult",{}).get("restored"):
            raise RuntimeError("No confirmed recovery; stop writes.")
    run.call("final","designer.status")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run",required=True)
    parser.add_argument("suite",choices=["probe","property-writes","precision-probe","precision-writes"])
    opts=parser.parse_args()
    {"probe":probe,"property-writes":property_writes,"precision-probe":precision_probe,"precision-writes":precision_writes}[opts.suite](Run(opts.run))
