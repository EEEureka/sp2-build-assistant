"""Independent, read-only comparison of two saved CLI snapshots after recovery.

Checks the complete native XML. Only generated target-set ordering/duplicates
and the documented 0.0001 degree Euler reconstruction tolerance are allowed.
No game access or edits are performed by this script.
"""
import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


def compare(before, after):
    errors, rotations, generated = [], [], []
    left, right = before["data"], after["data"]

    def fail(path, expected, actual):
        errors.append({"path": path, "expected": expected, "actual": actual})

    if not before.get("success") or not after.get("success"):
        raise ValueError("Both files must contain successful craft.snapshot results")
    for key in ("craftSessionId",):
        if left["identity"][key] != right["identity"][key]:
            fail("identity." + key, left["identity"][key], right["identity"][key])
    if right["identity"]["stateUncertain"]:
        fail("identity.stateUncertain", False, True)
    for key in ("partCount", "name", "selectedPartId", "variables"):
        if left.get(key) != right.get(key):
            fail(key, left.get(key), right.get(key))
    a_parts = {p["id"]: p["type"] for p in left["parts"]}
    b_parts = {p["id"]: p["type"] for p in right["parts"]}
    if a_parts != b_parts:
        for part_id in sorted(set(a_parts) | set(b_parts)):
            if a_parts.get(part_id) != b_parts.get(part_id):
                fail("partIdTypes." + str(part_id), a_parts.get(part_id), b_parts.get(part_id))

    def attributes(node, path):
        result = dict(node.attrib)
        if node.tag == "PartTargeting.State" and node.get("targetMode") != "Custom" and "partIds" in result:
            try:
                result["partIds"] = ",".join(map(str, sorted({int(x) for x in result["partIds"].split(",") if x})))
            except ValueError:
                pass
            if result["partIds"] != node.get("partIds"):
                generated.append(path)
        return result

    def visit(a, b, path):
        if a.tag != b.tag:
            fail(path + ".tag", a.tag, b.tag)
            return
        aa, ba = attributes(a, path), attributes(b, path)
        if a.tag == "Part" and "/Assembly[0]/Parts[0]/Part[" in path and aa.get("rotation") != ba.get("rotation"):
            try:
                av = [float(v) for v in aa["rotation"].split(",")]
                bv = [float(v) for v in ba["rotation"].split(",")]
                delta = [abs((x-y+180) % 360-180) for x, y in zip(av, bv)]
                if len(av) == len(bv) == 3 and all(math.isfinite(d) and d <= 0.0001 for d in delta):
                    rotations.append({"partId": a.get("id"), "before": aa["rotation"], "after": ba["rotation"], "maxDegrees": max(delta)})
                    ba["rotation"] = aa["rotation"]
            except (KeyError, ValueError):
                pass
        for key in sorted(set(aa) | set(ba)):
            if aa.get(key) != ba.get(key):
                fail(path + "/@" + key, aa.get(key), ba.get(key))
        # Native output is element-only except payload text. Ignore formatting
        # whitespace while preserving nonempty text and sibling ordering.
        for key in ("text", "tail"):
            x, y = getattr(a, key), getattr(b, key)
            x = None if x is None or not x.strip() else x
            y = None if y is None or not y.strip() else y
            if x != y:
                fail(path + "/" + key, x, y)
        if len(a) != len(b):
            fail(path + "/childCount", len(a), len(b))
        counts = {}
        for ac, bc in zip(a, b):
            index = counts.get(ac.tag, 0)
            counts[ac.tag] = index + 1
            visit(ac, bc, path + "/" + ac.tag + "[" + str(index) + "]")

    a_xml, b_xml = ET.fromstring(left["xml"]), ET.fromstring(right["xml"])
    visit(a_xml, b_xml, a_xml.tag)
    return {"equivalent": not errors, "beforeRevision": left["identity"]["revision"], "afterRevision": right["identity"]["revision"],
            "beforePartCount": left["partCount"], "afterPartCount": right["partCount"],
            "fingerprintIdentical": left["identity"]["fingerprint"] == right["identity"]["fingerprint"],
            "allowedEulerChanges": rotations, "normalizedGeneratedTargets": sorted(set(generated)), "differences": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    result = compare(json.loads(args.before.read_text(encoding="utf-8-sig")), json.loads(args.after.read_text(encoding="utf-8-sig")))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded if args.verbose else json.dumps({"equivalent": result["equivalent"], "beforeRevision": result["beforeRevision"],
          "afterRevision": result["afterRevision"], "beforePartCount": result["beforePartCount"], "afterPartCount": result["afterPartCount"],
          "allowedEulerChanges": len(result["allowedEulerChanges"]), "differenceCount": len(result["differences"]),
          "differencePaths": [entry["path"] for entry in result["differences"][:20]]}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["equivalent"] else 1)
