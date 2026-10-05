"""Exercise the installed sp2build CLI on the open designer and restore a checkpoint.

Run only after the player has entered the intended designer and authorized testing.
Uses temporary parts, never opens or edits a saved craft file.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ARTIFACTS = Path(__file__).parent / "artifacts" / ("v02-" + uuid.uuid4().hex[:10])
ARTIFACTS.mkdir(parents=True)
if os.name == "nt":
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        os.environ["PATH"] = winreg.QueryValueEx(key, "Path")[0] + ";" + os.environ["PATH"]
CLI = shutil.which("sp2build")
if not CLI:
    raise SystemExit("Global sp2build command is unavailable")
sequence = 0
outcome_unknown = False

def call(command, args=None, require=True):
    global sequence, outcome_unknown
    sequence += 1
    argv = [CLI, *command.split("."), "--json", "--timeout", "45"]
    if args is not None:
        path = ARTIFACTS / f"{sequence:03d}-input.json"
        path.write_text(json.dumps(args), encoding="utf-8")
        argv.extend(["--input", str(path.resolve())])
    try:
        proc = subprocess.run(argv, capture_output=True, encoding="utf-8", timeout=60)
        result = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        outcome_unknown = True
        raise RuntimeError("CLI outcome unknown; inspect the submitted request and active operation before recovery.")
    (ARTIFACTS / f"{sequence:03d}-{command}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    error = result.get("error", {})
    if error.get("code") == "wait_timeout":
        outcome_unknown = True
        raise RuntimeError("Operation still active; inspect operationId in the artifact. Do not submit another write.")
    if error.get("code") == "bridge_unreachable" and command in ("batch.apply", "craft.undo", "craft.rollback"):
        outcome_unknown = True
    if require and not result.get("success"):
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result

def read(command, **args):
    return call(command, args or None)["data"]

def guarded(command, **args):
    identity = read("designer.status")["identity"]
    return call(command, {"craftSessionId": identity["craftSessionId"], "expectedRevision": identity["revision"], "requestId": uuid.uuid4().hex, **args})

def apply(*operations):
    return guarded("batch.apply", operations=list(operations))["data"]

def hits(part, x, y, z):
    return any(h["partId"] == part for h in read("designer.raycast", origin=[x,y,z], direction=[0,-1,0], distance=20)["hits"])

def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS " + label, flush=True)

def main():
    status = read("designer.status")
    check("DLL 0.2.0 loaded in designer", status["pluginVersion"] == "0.2.0" and status["designerReady"])
    before = read("craft.snapshot", includeXml=True)
    selection = read("designer.selection")["selectedPartId"]
    checkpoint = guarded("craft.checkpoint.create", name="Before 0.2 geometry verification")["data"]["id"]
    (ARTIFACTS / "recovery.json").write_text(json.dumps({"checkpointId": checkpoint, "identity": before["identity"]}), encoding="utf-8")
    original_error = None
    completed = []
    try:
        entries = read("catalog.list", limit=1000)["listing"]["items"]
        def template(type_id):
            return next(e["id"] for e in entries if e["creatable"] and e["partTypes"] == [type_id])
        data = apply({"kind":"part.add", "templateId":template("JFuselage-1"), "temporaryId":"body", "position":[20,15,0], "rotation":[0,0,0]})
        body = data["temporaryIds"]["body"]
        read("parts.geometry", id=body)
        check("Ray outside original fuselage misses", not hits(body,20,20,2))
        apply({"kind":"shape.update", "partId":body, "symmetric":False, "patch":{"length":6}})
        check("Expanded fuselage has physical hit in new volume", hits(body,20,20,2))
        read("parts.geometry", id=body)
        apply({"kind":"shape.update", "partId":body, "symmetric":False, "patch":{"length":1}})
        check("Shrinking removes old pick volume", not hits(body,20,20,2))
        guarded("craft.undo")
        check("Undo restores expanded physical shape", hits(body,20,20,2))
        check("Primary selection survives rebuild", read("designer.selection")["selectedPartId"] == selection)
        completed.append("fuselage_geometry_and_undo")

        config = read("symmetry.get")["configuration"]
        if config["mode"] == "Mirrored":
            result = apply({"kind":"symmetry.create", "partId":body})
            peer = result["actualChanges"][0]["createdPartIds"][0]
            apply({"kind":"shape.update", "partId":body, "patch":{"sections":[{"index":0,"cutting":{"right":0.2}}]}})
            target = read("shape.get", id=peer)["shape"]["configuration"]["sections"][0]
            check("Mirror maps source right cut to peer left", abs(target["cutting"]["left"] - 0.2) < 0.0001)
            completed.append("mirror_geometry")
        else:
            print("SKIP mirror check: player's designer mode is " + config["mode"], flush=True)

        rotor_type = next(t for t in ("HingeRotator-1", "SmallRotator-1", "JointRotator-1") if any(e["partTypes"] == [t] for e in entries))
        result = apply({"kind":"part.add", "templateId":template(rotor_type), "temporaryId":"rotor", "position":[30,15,0]})
        rotor = result["temporaryIds"]["rotor"]
        points = read("connections.points", part=rotor)["points"]
        check("Native joint has one rotor and housing points", sum(p["role"] == "rotor" for p in points) == 1 and any(p["role"] == "housing" for p in points))
        completed.append("joint_roles")

        result = apply({"kind":"part.add", "templateId":template("JWing-1"), "temporaryId":"wing", "position":[30,20,0]})
        wing = result["temporaryIds"]["wing"]
        apply({"kind":"shape.update", "partId":wing, "symmetric":False, "patch":{"sections":[{"index":0,"airfoil":"NACA2412"}]}})
        span = read("shape.get", id=wing)["shape"]["spanMetres"]
        result = apply({"kind":"wing.control.add", "wingPartId":wing, "style":"StandardFlap", "temporaryId":"flap", "patch":{"spanRange":[span*.25,span*.75],"chordFraction":[.2,.2],"maxDeflectionDegrees":20}})
        flap = result["temporaryIds"]["flap"]
        check("Added control belongs to target wing", read("shape.get", id=flap)["shape"]["wingPartId"] == wing)
        completed.append("wing_and_control_surface")

        identity = read("designer.status")["identity"]
        bad = call("batch.apply", {"craftSessionId":identity["craftSessionId"],"expectedRevision":identity["revision"],"requestId":uuid.uuid4().hex,
            "operations":[{"kind":"part.update","partId":body,"changes":[{"path":"","attribute":"name","value":"temporary failed edit"}]},
                          {"kind":"shape.update","partId":body,"patch":{"sections":[{"index":0,"cutting":{"top":.6,"bottom":.6}}]}}]}, require=False)
        check("Invalid complex edit restores whole transaction", not bad["success"] and bad["rollbackResult"]["restored"])
        completed.append("invalid_edit_recovery")
    except Exception as exc:
        original_error = str(exc)
    finally:
        if not outcome_unknown:
            try:
                restored = guarded("craft.rollback", checkpointId=checkpoint)["data"]
                check("Baseline restoration verified", restored["validation"]["restorationVerified"])
                check("Original part count restored", read("craft.snapshot")["partCount"] == before["partCount"])
                completed.append("restore")
            except Exception as exc:
                original_error = (original_error or "") + " Recovery failed: " + str(exc)
        summary = {"buildId": status.get("buildId"), "completed": completed, "error": original_error, "outcomeUnknown": outcome_unknown, "artifacts": str(ARTIFACTS.resolve())}
        (ARTIFACTS / "summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    return 1 if original_error else 0

if __name__ == "__main__":
    raise SystemExit(main())
