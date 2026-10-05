"""Reversible live CLI checks against ONLY the currently open designer aircraft.

Run stages explicitly; the persisted checkpoint targets the original open session.
No saved-aircraft file is read, opened, or written by the CLI under test.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)
CLI = Path(os.environ["LOCALAPPDATA"]) / "SP2BuildAssistant" / "bin" / "sp2build.cmd"
STATE = ART / "verification-state.json"
REPORT = ART / "verification-results.json"


def call(command, args=None, expect=True, request=None, options=()):
    words = command.split(".")
    if args is not None:
        source = ART / ("request-" + uuid.uuid4().hex + ".json")
        source.write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")
        words += ["--input", str(source)]
    words += list(options)
    proc = subprocess.run([str(CLI), *words, "--json"], capture_output=True, encoding="utf-8", timeout=45)
    result = json.loads(proc.stdout)
    response_path = ART / ("response-" + command + "-" + (result.get("operationId") or uuid.uuid4().hex) + ".json")
    response_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    entry = {"command": command, "exitCode": proc.returncode, "success": result["success"], "operationId": result.get("operationId")}
    if not result["success"]:
        entry["error"] = result.get("error")
        entry["rollbackResult"] = result.get("rollbackResult")
    reports = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else []
    reports.append(entry)
    REPORT.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(entry, ensure_ascii=False), flush=True)
    if expect is not None:
        assert result["success"] == expect, json.dumps(result, ensure_ascii=False)
        assert (proc.returncode == 0) == expect
    return result


def snapshot():
    return call("craft.snapshot", {"includeXml": True})["data"]


def assert_restored(current, baseline, require_same_session=True):
    """Native reload/undo converts Euler angles through float quaternions."""
    if require_same_session:
        assert current["identity"]["craftSessionId"] == baseline["identity"]["craftSessionId"]
    a, b = ET.fromstring(current["xml"]), ET.fromstring(baseline["xml"])
    def equivalent(x, y):
        assert x.tag == y.tag and len(x) == len(y)
        assert set(x.attrib) == set(y.attrib)
        for key in x.attrib:
            av, bv = x.get(key), y.get(key)
            if av == bv:
                continue
            if x.tag == "PartTargeting.State" and key == "partIds" and x.get("targetMode") != "Custom":
                assert set(av.split(",")) == set(bv.split(","))
            elif x.tag == "Part" and key == "rotation":
                assert all(abs((float(v) - float(w) + 180) % 360 - 180) <= 0.0001 for v, w in zip(av.split(","), bv.split(","))), (x.tag, key, av, bv)
            else:
                raise AssertionError((x.tag, key, av, bv))
        for xc, yc in zip(x, y): equivalent(xc, yc)
    equivalent(a, b)


def write(command, extra, identity=None, key=None, expect=True):
    identity = identity or snapshot()["identity"]
    payload = {"craftSessionId": identity["craftSessionId"], "expectedRevision": identity["revision"],
               "requestId": key or uuid.uuid4().hex, **extra}
    return call(command, payload, expect=expect), payload


def read_checks():
    start = snapshot()
    (ART / "readonly-start.json").write_text(json.dumps(start, ensure_ascii=False, indent=2), encoding="utf-8")
    call("parts.list", {"offset": 0, "limit": 5})
    first, second = start["parts"][:2]
    detail = call("parts.get", {"id": first["id"]})["data"]["part"]
    assert detail["state"]["attributes"]["id"] == str(first["id"])
    call("connections.list")
    call("connections.points", {"part": first["id"]})
    spatial = call("spatial.query", {"partA": first["id"], "partB": second["id"]})["data"]
    assert spatial["distanceMetres"] > 0
    categories = call("catalog.categories")["data"]
    call("catalog.subcategories", {"category": "Structure"})
    listing = call("catalog.list", {"category": "Structure", "subcategory": "Blocks"})["data"]["listing"]
    block = next(item for item in listing["items"] if item["name"] == "Block")
    call("catalog.search", {"query": "Flight Computer"})
    call("catalog.get", {"id": block["id"]})
    call("catalog.schema", {"id": block["id"]})
    catalog = call("catalog.export")["data"]
    (ART / "live-catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    call("outputs.list")
    call("variables.list")
    call("funky.list")
    call("funky.describe", {"name": "clamp"})
    call("funky.validate", {"expression": "clamp(Throttle,0,1)"})
    bad = call("funky.validate", {"expression": "clamp("}, expect=False)
    assert bad["error"]["code"] == "execution_failed"
    end = snapshot()
    (ART / "readonly-end.json").write_text(json.dumps(end, ensure_ascii=False, indent=2), encoding="utf-8")
    assert start["identity"]["craftSessionId"] == end["identity"]["craftSessionId"]
    assert start["identity"]["fingerprint"] == end["identity"]["fingerprint"], "Read-only checks changed the aircraft"
    checkpoint, _ = write("craft.checkpoint.create", {"name": "CLI verification starting state"}, end["identity"])
    state = {"original": start, "checkpointId": checkpoint["data"]["id"], "blockTemplateId": block["id"]}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    call("craft.checkpoint.list")
    call("craft.checkpoint.get", {"id": state["checkpointId"]})
    print(json.dumps({"checked": "read_commands_and_checkpoint", "name": start["name"], "partCount": start["partCount"],
                      "catalogKeys": list(catalog), "categoryKeys": list(categories), "unchanged": True}), flush=True)


def add_checks():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    before = snapshot()
    ops = [{"kind": "part.add", "templateId": state["blockTemplateId"], "temporaryId": "testA", "position": [20, 5, 0]},
           {"kind": "part.add", "templateId": state["blockTemplateId"], "temporaryId": "testB", "position": [20, 5, 1]}]
    preview = call("batch.preview", {"craftSessionId": before["identity"]["craftSessionId"], "expectedRevision": before["identity"]["revision"], "operations": ops})
    assert preview["data"]["operationCount"] == 2
    assert snapshot()["identity"] == before["identity"]
    added, payload = write("batch.apply", {"operations": ops}, before["identity"])
    ids = added["data"]["temporaryIds"]
    state["testParts"] = ids
    state["addPayload"] = payload
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    after = snapshot()
    assert after["partCount"] == before["partCount"] + 2
    assert after["identity"]["craftSessionId"] == before["identity"]["craftSessionId"]
    duplicate = call("batch.apply", payload)
    assert duplicate["operationId"] == added["operationId"]
    assert snapshot()["identity"] == after["identity"]
    conflict = call("batch.apply", {**payload, "operations": ops[:1]}, expect=False)
    assert conflict["error"]["code"] == "request_id_conflict"
    stale, _ = write("batch.apply", {"operations": ops[:1]}, before["identity"], expect=False)
    assert stale["error"]["code"] == "revision_conflict"
    assert snapshot()["identity"] == after["identity"]
    for part in ids.values():
        call("parts.get", {"id": part})
        call("connections.points", {"part": part})
    print(json.dumps({"checked": "add_idempotence_revision_guard", "testParts": ids}), flush=True)


def restore():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    now = snapshot()
    assert now["identity"]["craftSessionId"] == state["original"]["identity"]["craftSessionId"], "Player changed craft; do not restore it"
    if now["identity"]["fingerprint"] != state["original"]["identity"]["fingerprint"]:
        write("craft.rollback", {"checkpointId": state["checkpointId"]}, now["identity"])
    after = snapshot()
    (ART / "after.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    assert_restored(after, state["original"])
    print(json.dumps({"checked": "restore", "nativeStateEquivalent": True, "rotationToleranceDegrees": 0.0001,
                      "fingerprintIdentical": after["identity"]["fingerprint"] == state["original"]["identity"]["fingerprint"], "partCount": after["partCount"]}), flush=True)


def edit_checks():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    pa, pb = state["testParts"]["testA"], state["testParts"]["testB"]
    before = snapshot()
    write("batch.apply", {"operations": [{"kind": "part.update", "partId": pa, "changes": [
        {"path": "", "attribute": "name", "value": "CLI临时验证零件"},
        {"path": "", "attribute": "massScale", "value": 1.25},
        {"path": "", "attribute": "position", "value": [22, 5, 0]}]}]}, before["identity"])
    detail = call("parts.get", {"id": pa})["data"]["part"]
    assert detail["name"] == "CLI临时验证零件"
    assert float(detail["state"]["attributes"]["massScale"]) == 1.25
    assert all(abs(a - b) < 1e-5 for a, b in zip(detail["position"], [22, 5, 0]))
    history = call("craft.history")["data"]
    assert history["canUndo"]
    write("craft.undo", {})
    undone = snapshot()
    assert_restored(undone, before)
    write("batch.apply", {"operations": [{"kind": "connection.connect", "partA": pa, "partB": pb, "attachPointA": 0, "attachPointB": 1}]})
    assert pb in call("parts.get", {"id": pa})["data"]["part"]["connectedPartIds"]
    call("connections.list")
    write("batch.apply", {"operations": [{"kind": "connection.disconnect", "partA": pa, "partB": pb}]})
    assert pb not in call("parts.get", {"id": pa})["data"]["part"]["connectedPartIds"]
    before_delete = snapshot()
    write("batch.apply", {"operations": [{"kind": "part.delete", "partId": pa}, {"kind": "part.delete", "partId": pb}]}, before_delete["identity"])
    assert snapshot()["partCount"] == before_delete["partCount"] - 2
    write("craft.undo", {})
    assert_restored(snapshot(), before_delete)
    print(json.dumps({"checked": "property_edit_connect_disconnect_delete_and_native_undo", "passed": True}), flush=True)


def variable_checks():
    baseline = snapshot()
    setters = baseline["variables"]["children"]
    index = len(setters)
    write("batch.apply", {"operations": [
        {"kind": "variable.add", "variable": "BuildAssistantSmokeA", "function": "clamp(Throttle,0,1)", "priority": 3},
        {"kind": "variable.add", "variable": "BuildAssistantSmokeB", "function": "0.25", "priority": 1}]})
    variables = call("variables.list")["data"]["setters"]["children"]
    assert len(variables) == index + 2
    assert variables[index]["attributes"]["variable"] == "BuildAssistantSmokeA"
    call("funky.validate", {"expression": "BuildAssistantSmokeA + BuildAssistantSmokeB"})
    write("batch.apply", {"operations": [{"kind": "variable.update", "index": index, "function": "0.75", "priority": 5}]})
    current = call("variables.list")["data"]["setters"]["children"]
    assert current[index]["attributes"]["function"] == "0.75"
    assert current[index]["attributes"]["priority"] == "5"
    write("batch.apply", {"operations": [{"kind": "variable.reorder", "order": list(range(index)) + [index + 1, index]}]})
    reordered = call("variables.list")["data"]["setters"]["children"]
    assert reordered[index]["attributes"]["variable"] == "BuildAssistantSmokeB"
    write("batch.apply", {"operations": [{"kind": "variable.delete", "index": index + 1}, {"kind": "variable.delete", "index": index}]})
    assert call("variables.list")["data"]["setters"]["children"] == setters
    outputs = call("outputs.list")["data"]["parts"]
    candidates = [(p["partId"], m, definition) for p in outputs for m in p["modifiers"] for definition in m["definitions"]
                  if not any(b["outputId"] == definition["id"] for b in m["bindings"])]
    assert candidates, "No currently unused native output for a reversible binding test"
    part_id, modifier, definition = candidates[0]
    binding = {"partId": part_id, "modifier": modifier["modifier"], "outputId": definition["id"]}
    write("batch.apply", {"operations": [{"kind": "output.bind", **binding, "variable": "BuildAssistantSmokeOutput", "priority": 2}]})
    def bindings():
        out = call("outputs.list", {"part": part_id})["data"]["parts"][0]["modifiers"]
        return next(m for m in out if m["modifier"] == modifier["modifier"])["bindings"]
    assert any(b["variable"] == "BuildAssistantSmokeOutput" for b in bindings())
    call("funky.validate", {"expression": "BuildAssistantSmokeOutput + 1"})
    write("batch.apply", {"operations": [{"kind": "output.update", **binding, "variable": "BuildAssistantSmokeRenamed", "priority": 4, "activator": "true"}]})
    assert any(b["variable"] == "BuildAssistantSmokeRenamed" and b["priority"] == 4 for b in bindings())
    write("batch.apply", {"operations": [{"kind": "output.unbind", **binding}]})
    assert not any(b["outputId"] == definition["id"] for b in bindings())
    print(json.dumps({"checked": "global_variable_add_update_reorder_delete_and_output_bind_update_unbind", "partId": part_id,
                      "modifier": modifier["modifier"], "outputId": definition["id"], "passed": True}), flush=True)


def async_checks():
    baseline = snapshot()
    submitted = call("parts.list", {"limit": 1}, options=["--async"])
    operation = submitted["data"]["operationId"]
    call("operation.status", options=["--id", operation])
    waited = call("operation.wait", options=["--id", operation])
    assert len(waited["data"]["listing"]["items"]) == 1
    again = call("operation.result", options=["--id", operation])
    assert again["operationId"] == operation
    assert snapshot()["identity"] == baseline["identity"]
    print(json.dumps({"checked": "async_operation_status_wait_result", "passed": True}), flush=True)


def history_restore():
    # Run only after the one observed native UI undo used to reset the old
    # checksum-error flag. Continue through our own verified test history.
    state = json.loads(STATE.read_text(encoding="utf-8"))
    history = call("craft.history")["data"]
    assert history["nativeSteps"][0]["Description"] == "Loaded '" + state["original"]["name"] + "'"
    assert all(s["Description"].startswith("SP2Build ") for s in history["nativeSteps"][1:])
    for _ in range(len(history["nativeSteps"])):
        now = snapshot()
        try:
            assert_restored(now, state["original"], require_same_session=False)
        except AssertionError:
            write("craft.undo", {}, now["identity"])
        else:
            (ART / "restored-after-0.1.1.json").write_text(json.dumps(now, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"checked": "native_history_recovery", "nativeStateEquivalent": True, "partCount": now["partCount"]}), flush=True)
            return
    raise AssertionError("Did not find the original state inside our own undo history")


def failure_checks():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    before = snapshot()
    result, _ = write("batch.apply", {"operations": [
        {"kind": "part.add", "templateId": state["blockTemplateId"], "temporaryId": "mustDisappear", "position": [23, 5, 0]},
        {"kind": "variable.add", "variable": "BuildAssistantMustNotRemain", "function": "clamp("}]}, before["identity"], expect=False)
    assert result["rollbackResult"]["attempted"] and result["rollbackResult"]["restored"]
    after = snapshot()
    assert after["partCount"] == before["partCount"]
    assert not after["identity"]["stateUncertain"]
    assert_restored(after, before)
    retried = call("operation.result", options=["--id", result["operationId"]], expect=False)
    assert retried["operationId"] == result["operationId"]
    # A subsequent read-only preview proves successful recovery did not lock writes.
    call("batch.preview", {"craftSessionId": after["identity"]["craftSessionId"], "expectedRevision": after["identity"]["revision"],
                           "operations": [{"kind": "variable.add", "variable": "NotApplied", "function": "1"}]})
    print(json.dumps({"checked": "failure_after_partial_native_edit_rolls_back", "rollbackRestored": True, "passed": True}), flush=True)


def run_all():
    assert call("designer.status")["data"]["pluginVersion"] == "0.1.4"
    # Preserve earlier investigation evidence; final-run result assertions are separate.
    previous = REPORT.read_bytes() if REPORT.exists() else None
    if previous:
        (ART / "investigation-results.json").write_bytes(previous)
    REPORT.write_text("[]", encoding="utf-8")
    completed = []
    try:
        for name, stage in [("read", read_checks), ("add", add_checks), ("edit", edit_checks),
                            ("variables", variable_checks), ("async", async_checks), ("failure", failure_checks)]:
            stage()
            completed.append(name)
    finally:
        restore()
    summary = {"pluginVersion": "0.1.4", "stagesPassed": completed + ["restore"],
               "restoredCurrentOpenCraft": True, "restoreEulerToleranceDegrees": 0.0001}
    (ART / "verification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    {"read": read_checks, "add": add_checks, "edit": edit_checks, "variables": variable_checks,
     "async": async_checks, "failure": failure_checks, "restore": restore, "history-restore": history_restore, "all": run_all}[sys.argv[1]]()
