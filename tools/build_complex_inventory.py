"""Index native catalog schemas and serializer source evidence, without loading Unity."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "Game/Assets/Scripts"
MOD = "Craft/Parts/Modifiers/"
FAMILIES = [
    ("fuselage", "JFuselage body / cone / curved multi-section", ["JFuselage.State"], [MOD+"JFuselageData.cs", "Craft/Parts/Fuselage/SectionParams.cs", "Craft/Parts/Fuselage/FuselageJob.cs"], "typed"),
    ("wing", "JWing multi-section airfoil and wingtip", ["JWing.State"], [MOD+"JWingData.cs", "Craft/Wings/InputWingSlice.cs", "Craft/Wings/WingTip*.cs", "Craft/Wings/RoundedTip.cs", "Craft/Wings/Airfoils/*.cs"], "typed"),
    ("controlSurface", "Wing control surface cluster", ["ControlSurfacePart.State"], [MOD+"ControlSurfacePartData.cs", "Craft/Wings/ControlSurfaces/*.cs"], "typed: StandardFlap/FowlerFlap/BrakeFlap/Slat; source-only: Spoiler/SplitFlap"),
    ("legacyGeometry", "Legacy Fuselage / Wing", ["Fuselage.State", "Wing.State", "ControlSurface.State"], [MOD+"FuselageData.cs", MOD+"WingData.cs", MOD+"ControlSurfaceData.cs"], "native metadata and raw state; no typed editor"),
    ("carver", "Window / shape modifier / bay carving", ["ProceduralWindow.State", "ProceduralBay.State", "PartTargeting.State"], [MOD+"CarverParts/*Data.cs", MOD+"PartTargetingData.cs"], "inventory and native metadata"),
    ("landingGear", "Gear bay / leg / animated poses", ["GearBay.State", "GearLeg.State", "Animator.State"], [MOD+"CarverParts/*Data.cs", MOD+"LandingGear/Procedural/*Data.cs", MOD+"Animator/*.cs"], "inventory and native metadata"),
    ("wheel", "Wheel / suspension geometry and constraints", ["JWheelAssembly.State", "JWheel.State", "JWheelSuspension.State"], [MOD+"Wheel/*Data.cs", MOD+"Car/JWheel*Data.cs", MOD+"ResizableWheelData.cs"], "inventory and native metadata"),
    ("missile", "Procedural in-game missile body / fins / subparts", ["ProceduralMissile.State", "ProceduralMissileSubPart.State"], [MOD+"Weapons/ProceduralMissile*Data.cs"], "inventory and native metadata"),
    ("propulsion", "Propeller / engine assembly", ["PropellerAssembly.State", "JEngine.State"], [MOD+"Propulsion/Propeller/*Data.cs", MOD+"Powertrain/*Data.cs"], "inventory and native metadata"),
    ("cockpit", "Instruments / controls / grips / poses", ["Gauge.State", "Indicator.State", "ControlBase.State", "PosedGrip.State", "IKTarget.State"], [MOD+"GaugeData.cs", MOD+"*Indicator*Data.cs", MOD+"XR/*Data.cs", MOD+"Character/IKTargetData.cs"], "inventory and native metadata"),
    ("articulation", "Rotator / hinge / piston joint semantics", ["JointRotator.State", "Piston.State"], [MOD+"JointRotatorData.cs", MOD+"PistonData.cs", "Craft/Parts/AttachPointData.cs"], "native attach point roles and property metadata"),
]

def main():
    catalog = json.loads((ROOT / "knowledge/catalog.json").read_text(encoding="utf-8-sig"))["data"]
    families = []
    # Evidence, not an inferred list of writable fields: constructor/config fields can be read-only.
    call = re.compile(r'(?:Get\w*Attribute\w*|SetAttribute\w*|\bAttribute|\bXAttribute|\bAdd(?:Float|Int|Bool|String|Enum)(?:<[^>]+>)?)\s*\(\s*"([^"]+)"')
    for key, label, states, patterns, support in FAMILIES:
        files = sorted({p for pattern in patterns for p in SOURCE.glob(pattern)})
        evidence = []
        for path in files:
            data = path.read_bytes()
            parameters = []
            for line, text in enumerate(data.decode("utf-8-sig").splitlines(), 1):
                for match in call.finditer(text):
                    parameters.append({"name": match[1], "line": line, "expression": text.strip()})
            evidence.append({"file": str(path.relative_to(SOURCE)).replace("\\", "/"), "sha256": hashlib.sha256(data).hexdigest(), "parameters": parameters})
        native = []
        for template in catalog["schemas"]:
            for part in template.get("parts", []):
                nodes = part.get("defaultState", {}).get("children", [])
                present = [n["element"] for n in nodes]
                # Animator IDs have a numeric suffix in native templates.
                if any(s in present or (s == "Animator.State" and any(n.startswith("Animator") for n in present)) for s in states):
                    native.append({"templateId": template["id"], "name": template["name"], "description": template.get("description"), "part": part})
        families.append({"id": key, "label": label, "support": support, "stateElements": states,
                         "nativeTemplates": native, "sourceFiles": evidence,
                         "sourceAttributeNames": sorted({p["name"] for f in evidence for p in f["parameters"]})})
    result = {"schemaVersion": 1, "catalogGameVersion": catalog["gameVersion"], "catalogGeneratedAt": catalog["generatedAt"],
              "scope": "All catalog parts, including unused parts; native schemas + nested serializer evidence + inherited classes. Dynamic names and mod hooks require runtime schema inspection.",
              "important": "Source parameter evidence is not a writable allowlist. Distinguish constructor-only, derived and serialized state. Typed support is explicitly listed per family.", "families": families}
    path = ROOT / "knowledge/complex-parts.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "families": len(families), "sourceFiles": sum(len(f["sourceFiles"]) for f in families), "parameterEvidence": sum(len(s["parameters"]) for f in families for s in f["sourceFiles"])}, ensure_ascii=False))

if __name__ == "__main__":
    main()
