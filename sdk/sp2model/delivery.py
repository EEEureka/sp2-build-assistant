"""Durable native save/reopen delivery, with a single evidenced frame translation.

No XML access and no implicit resubmission of a control operation. Diagnostic
snapshots are integrity evidence, not independently executable recovery points.
"""
from copy import deepcopy
import math

from .errors import ModelingError
from .geometry import magnitude, sub
from .project import label, same_identity
from .transport import canonical_json


def _vec(value, size):
    return (isinstance(value, (tuple, list)) and len(value) == size and
            all(type(v) in (int, float) and math.isfinite(v) for v in value))


def _connections(value):
    """Canonical complete topology for both native and structured snapshots.

    Native craft.snapshot returns an XML-node object, not the structured edge
    list used by some clients. Preserve every node/attribute rather than reducing
    connections to endpoint pairs (which would lose attachment-point evidence).
    Only sibling order is ignored; duplicate edges retain their multiplicity.
    """
    if isinstance(value, list) and all(isinstance(row, dict) for row in value):
        return ("structured", tuple(sorted(canonical_json(row) for row in value)))
    if (isinstance(value, dict) and value.get("element") == "Connections" and
            isinstance(value.get("attributes"), dict) and isinstance(value.get("children"), list) and
            all(isinstance(row, dict) and row.get("element") == "Connection" and
                isinstance(row.get("attributes"), dict) and
                all(key in row["attributes"] for key in ("partA", "partB", "attachPointsA", "attachPointsB")) and
                isinstance(row.get("children"), list) for row in value["children"])):
        parent = {key: item for key, item in value.items() if key != "children"}
        return ("native_xml", canonical_json(parent), tuple(sorted(canonical_json(row) for row in value["children"])))
    return None


def common_translation(before, after, *, tolerance_m=0.00002, quaternion_tolerance=0.00002):
    """Prove an all-part translation using IDs, content, rotations and connections.

    Requires native content fingerprints (which exclude the world transform).
    It never fits individual parts and fails closed when proof is unavailable.
    Float tolerances only cover native round trips, not modeling tolerances.
    """
    if (type(tolerance_m) not in (int, float) or not math.isfinite(tolerance_m) or tolerance_m <= 0 or
            type(quaternion_tolerance) not in (int, float) or not math.isfinite(quaternion_tolerance) or quaternion_tolerance <= 0):
        raise ModelingError("invalid_input", "Translation evidence tolerances must be finite and positive.")
    result = {"valid": False, "translationMetres": None, "partCount": 0, "maxResidualMetres": None,
              "toleranceMetres": tolerance_m, "quaternionTolerance": quaternion_tolerance,
              "rule": "same complete ID set, native content, rotation, scale, connections and one common translation",
              "failures": []}
    if not isinstance(before, dict) or not isinstance(after, dict):
        result["failures"].append({"reason": "snapshot_required"}); return result
    if not all(isinstance(s.get("parts"), list) and s["parts"] for s in (before, after)):
        result["failures"].append({"reason": "complete_nonempty_snapshot_required"}); return result
    left_connections, right_connections = _connections(before.get("connections")), _connections(after.get("connections"))
    if left_connections is None or right_connections is None:
        result["failures"].append({"reason": "complete_connections_required"}); return result
    left = {p.get("id"): p for p in before["parts"]}
    right = {p.get("id"): p for p in after["parts"]}
    if (len(left) != len(before["parts"]) or len(right) != len(after["parts"]) or
            set(left) != set(right) or any(type(i) is not int for i in left)):
        result["failures"].append({"reason": "part_ids_changed_or_ambiguous"}); return result
    result["partCount"] = len(left)
    if left_connections != right_connections:
        result["failures"].append({"reason": "connections_changed"})
    shifts = []
    for id in sorted(left):
        a, b = left[id], right[id]
        if not a.get("type") or a.get("type") != b.get("type"):
            result["failures"].append({"partId": id, "reason": "part_type_changed"})
        if not a.get("contentFingerprint") or a.get("contentFingerprint") != b.get("contentFingerprint"):
            result["failures"].append({"partId": id, "reason": "content_changed_or_unproved"})
        if a.get("contentFingerprintAlgorithm") != b.get("contentFingerprintAlgorithm"):
            result["failures"].append({"partId": id, "reason": "content_algorithm_changed"})
        for key in ("scale", "scaleXYZ"):
            if a.get(key) != b.get(key):
                result["failures"].append({"partId": id, "reason": "scale_changed", "field": key})
        if not _vec(a.get("position"), 3) or not _vec(b.get("position"), 3):
            result["failures"].append({"partId": id, "reason": "position_unavailable"})
        else:
            shifts.append((id, [y - x for x, y in zip(a["position"], b["position"])]))
        qa, qb = a.get("rotationQuaternion"), b.get("rotationQuaternion")
        if not _vec(qa, 4) or not _vec(qb, 4):
            result["failures"].append({"partId": id, "reason": "rotation_unavailable"})
        elif min(magnitude(sub(qa, qb)), magnitude([x + y for x, y in zip(qa, qb)])) > quaternion_tolerance:
            result["failures"].append({"partId": id, "reason": "rotation_changed"})
    if shifts:
        # The first part determines the common shift. No least-squares fitting
        # can hide a local displacement by spreading its error across parts.
        shift = shifts[0][1]
        residuals = [(id, magnitude(sub(delta, shift))) for id, delta in shifts]
        result["translationMetres"] = shift
        result["maxResidualMetres"] = max(error for _, error in residuals)
        result["failures"] += [{"partId": id, "reason": "local_displacement", "residualMetres": error}
                               for id, error in residuals if error > tolerance_m]
        fa, fb = before.get("craftFrame", {}), after.get("craftFrame", {})
        if not _vec(fa.get("position"), 3) or not _vec(fb.get("position"), 3):
            result["failures"].append({"reason": "craft_frame_unavailable"})
        elif magnitude(sub(sub(fb["position"], fa["position"]), shift)) > tolerance_m:
            result["failures"].append({"reason": "craft_frame_disagrees"})
        qa, qb = fa.get("rotationQuaternion"), fb.get("rotationQuaternion")
        if not _vec(qa, 4) or not _vec(qb, 4):
            result["failures"].append({"reason": "craft_rotation_unavailable"})
        elif min(magnitude(sub(qa, qb)), magnitude([x + y for x, y in zip(qa, qb)])) > quaternion_tolerance:
            result["failures"].append({"reason": "craft_rotation_changed"})
    result["valid"] = not result["failures"] and len(shifts) == len(left)
    return result


def _update(task, record, **values):
    with task._edit():
        record.update(deepcopy(values))


def _event(task, delivery_id, phase):
    matches = [e for e in task.data.get("lifecycle", []) if e.get("deliveryId") == delivery_id and e.get("deliveryPhase") == phase]
    if len(matches) > 1:
        raise ModelingError("delivery_history_conflict", "Multiple native requests claim the same delivery phase.",
                            {"deliveryId": delivery_id, "phase": phase})
    return matches[0] if matches else None


def _original(task, event):
    if not event.get("journalPath"):
        raise ModelingError("no_submission_evidence", "Delivery phase has no original request journal; it will not be replayed.",
                            {"deliveryId": event.get("deliveryId"), "phase": event.get("deliveryPhase")})
    result = task.session.resume(event["journalPath"])
    with task._edit():
        event.update(state="succeeded", result=deepcopy(result))
    return result


def _snapshot(session):
    session.inspect()
    return deepcopy(session._snapshot)


def _receipt_fence(snapshot, result, phase):
    if not same_identity(snapshot.get("identity", {}), result.get("identity", {})):
        raise ModelingError("delivery_scene_changed", "Current craft differs from the original delivery receipt; no next write is allowed.",
                            {"phase": phase, "expectedIdentity": result.get("identity"), "actualIdentity": snapshot.get("identity"),
                             "requestId": result.get("requestId"), "journalPath": result.get("journalPath")})


def _apply_shift(task, record, key, before, after):
    proof = common_translation(before, after)
    if not proof["valid"]:
        _update(task, record, state="integrity_blocked", **{key: proof})
        raise ModelingError("delivery_integrity_failed", "Native delivery changed more than a proven whole-craft translation.",
                            {"deliveryId": record["deliveryId"], "phase": key, "proof": proof})
    with task._edit():
        if not record.get(key + "Applied"):
            old = task.data.get("frameTranslationMetres", [0, 0, 0])
            task.data["frameTranslationMetres"] = [a + b for a, b in zip(old, proof["translationMetres"])]
            record[key + "Applied"] = True
        record[key] = proof


def deliver_task(task, candidate_id, name, delivery_id, *, overwrite=False, allow_incomplete=False):
    """Save once, reopen once, rebind and recheck; retries query original IDs.

    Mutates ``task.session`` to the explicitly reopened Session. All snapshots,
    phases, journals and results persist in the task document. ``allow_incomplete``
    permits preserving a partial candidate; it never turns failed metrics into a
    successful delivery. Same-ID retries cannot change name/candidate/overwrite.
    """
    label(delivery_id, "delivery ID"); label(name, "save name")
    if type(overwrite) is not bool or type(allow_incomplete) is not bool:
        raise ModelingError("invalid_input", "overwrite and allow_incomplete must be boolean.")
    task.reload(); task._contract()
    if candidate_id not in task.data["candidates"]:
        raise ModelingError("candidate_not_found", "Choose an existing task candidate.")
    if task.session.client.instance["instanceId"] != task.data["instanceId"]:
        raise ModelingError("instance_conflict", "Delivery belongs to another native instance.")
    args = {"candidateId": candidate_id, "name": name, "overwrite": overwrite, "allowIncomplete": allow_incomplete}
    record = task.data.get("deliveries", {}).get(delivery_id)
    if record is not None and record["arguments"] != args:
        raise ModelingError("intent_conflict", "This delivery ID already belongs to different save arguments.",
                            {"deliveryId": delivery_id, "originalArguments": record["arguments"]})
    if record is None:
        checked = task.check(candidate_id)
        passed = checked["report"]["candidates"][candidate_id]["allRequiredPassed"]
        if not passed and not allow_incomplete:
            raise ModelingError("delivery_gate_failed", "Required metrics are not all passed; inspect the candidate before delivery.",
                                {"candidateId": candidate_id, "report": checked["report"], "writesIssued": False})
        baseline = _snapshot(task.session)
        record = {"deliveryId": delivery_id, "arguments": args, "state": "prepared", "before": baseline,
                  "precheck": checked, "delivered": False, "saved": False, "reopened": False,
                  "snapshotMeaning": "diagnostic integrity evidence; not a cross-session recovery artifact"}
        with task._edit():
            task.data.setdefault("deliveries", {})[delivery_id] = record
    if record.get("state") in ("complete", "saved_incomplete"):
        current = task.session.client.call("craft.snapshot")["identity"]
        result = deepcopy(record["result"])
        result["currentIdentity"] = current
        result["currentEvidenceMatches"] = same_identity(current, result["identity"])
        if not result["currentEvidenceMatches"]:
            result.update(delivered=False, state="historical_delivery_current_state_changed",
                          nextAction="Inspect and recheck current state. This query did not save or reload again.")
        result["replayedNativeWrites"] = False
        return result
    try:
        save_event = _event(task, delivery_id, "save")
        load_event = _event(task, delivery_id, "reopen")
        if save_event is None:
            task.session._fresh(record["before"]["identity"])
            saved = task._lifecycle("save", lambda: task.session.save(name, overwrite=overwrite),
                                    metadata={"deliveryId": delivery_id, "deliveryPhase": "save"})
        else:
            saved = _original(task, save_event)
        persisted = saved.get("persistedCraft", {})
        if saved.get("saved") is not True or not persisted.get("craftId") or persisted.get("persistenceVerified") is not True:
            raise ModelingError("delivery_save_unverified", "Native result does not prove a named persisted craft.", {"save": saved})
        _update(task, record, saved=True, saveResult=saved, persistedCraft=persisted)
        if load_event is None:
            # Only the exact original save receipt allows the destructive reload.
            after_save = _snapshot(task.session)
            _receipt_fence(after_save, saved, "save")
            if "afterSave" not in record:
                _update(task, record, afterSave=after_save)
            _apply_shift(task, record, "saveTranslation", record["before"], after_save)
            _update(task, record, state="saved")
            new_session = task._lifecycle("reopen", lambda: task.session.reopen(persisted["craftId"], discard_current=True),
                                         metadata={"deliveryId": delivery_id, "deliveryPhase": "reopen"})
            loaded = deepcopy(new_session.last_control)
            task.session = new_session
        else:
            loaded = _original(task, load_event)
            # A load changes epoch even if its final Python callback failed.
            # Explicit attachment follows the queried original receipt only.
            from .session import Session
            task.session = Session(task.session.client, journal_dir=task.session.journal.directory,
                                   project_path=None if task.session.project is None else task.session.project.path)
        after_load = _snapshot(task.session)
        _receipt_fence(after_load, loaded, "reopen")
        if "afterSave" not in record or not record.get("saveTranslationApplied"):
            raise ModelingError("delivery_evidence_missing", "Reopen exists without prior save integrity evidence; no frame is inferred.")
        _apply_shift(task, record, "reopenTranslation", record["afterSave"], after_load)
        _update(task, record, reopened=True, loadResult=loaded, afterReopen=after_load, state="reopened")
        task.rebind(candidate_id)
        _update(task, record, state="rebound", bindingIdentity=task.session.identity)
        checked = task.check(candidate_id)
        passed = checked["report"]["candidates"][candidate_id]["allRequiredPassed"]
        result = {"deliveryId": delivery_id, "candidateId": candidate_id, "saved": True, "reopened": True,
                  "delivered": passed, "state": "complete" if passed else "saved_incomplete",
                  "persistedCraft": deepcopy(persisted), "identity": task.session.identity,
                  "frameTranslationMetres": deepcopy(task.data.get("frameTranslationMetres", [0, 0, 0])),
                  "saveTranslation": deepcopy(record["saveTranslation"]), "reopenTranslation": deepcopy(record["reopenTranslation"]),
                  "saveRequestId": saved.get("requestId"), "saveJournalPath": saved.get("journalPath"),
                  "reopenRequestId": loaded.get("requestId"), "reopenJournalPath": loaded.get("journalPath"),
                  "verification": checked, "taskPath": str(task.path), "replayedNativeWrites": False,
                  "checkpointNotice": "Session checkpoints from before reopen have expired. The explicit named native save is the preservation artifact."}
        _update(task, record, state=result["state"], delivered=passed, result=result)
        return result
    except Exception as error:
        details = error.to_dict() if isinstance(error, ModelingError) else {"code": "postprocess_error", "message": str(error), "type": type(error).__name__}
        _update(task, record, lastError=details, nextAction="Resume the same delivery ID to query linked original requests; do not create a replacement save intent.")
        raise
