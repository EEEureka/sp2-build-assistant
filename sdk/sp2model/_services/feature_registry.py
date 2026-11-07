"""Per-feature discovery. A missing CPU worker never disables core editing."""
from __future__ import annotations

try:
    from . import dependencies
except ImportError:
    from . import dependencies


def discover(payload=None, bridge=None):
    payload = payload or {}
    worker = dependencies.doctor({"selfTest": payload.get("selfTest", False)})
    def feature(name, available=True, requires_game=False, reason="available", missing=None, provider="stdlib"):
        return {"name": name, "available": available, "requiresGame": requires_game,
                "missingDependencies": missing or [], "minimumBridgeProtocol": None,
                "validatedGameVersions": [], "reasonCode": reason, "provider": provider}
    features = [feature("core.cli"), feature("reference.project"), feature("reference.image.metadata"),
                feature("reference.obj"), feature("reference.blender_exchange"),
                feature("build.loop"), feature("regional.review"), feature("parts.observe"),
                feature("knowledge.capabilityaudit"),
                feature("reference.blender_live", False, reason="optional_connection_not_probed", provider="optional_blender")]
    for name in ("reference.image.normalize", "reference.calibrate", "reference.render", "reference.compare", "fit.optimizer"):
        features.append(feature(name, worker["available"], reason=worker["reasonCode"], missing=worker["missingDependencies"], provider="reference-cpu"))
    bridge_data = (bridge.get("data", bridge) if isinstance(bridge, dict) else {})
    if not isinstance(bridge_data, dict):
        bridge_data = {}
    if bridge is None:
        bridge_reason = "bridge_not_probed"
    elif not isinstance(bridge, dict) or bridge.get("success") is False:
        bridge_reason = "bridge_not_available"
    elif bridge_data.get("designerReady") is not True:
        bridge_reason = "designer_not_ready"
    else:
        bridge_reason = "available"
    bridge_feature = feature("bridge.edit", bridge_reason == "available", True, bridge_reason, provider="live_bridge")
    bridge_feature["minimumBridgeProtocol"] = bridge_data.get("protocolVersion", bridge_data.get("protocol"))
    bridge_feature["observedPluginVersion"] = bridge_data.get("pluginVersion")
    features.append(bridge_feature)
    for name,command in (("bridge.scoped_editing","scoped.batch.apply"),("bridge.content_scopes","scope.capture")):
        present=bridge_reason=="available" and command in bridge_data.get("commands",[])
        features.append(feature(name,present,True,"available" if present else "loaded_bridge_command_missing" if bridge_reason=="available" else bridge_reason,provider="live_bridge"))
    return {"featureSchemaVersion": 1, "features": features, "worker": worker, "bridge": bridge, "downloadsAttempted": False}


def dispatch(action, payload=None):
    if action in ("feature.list", "features.list", "reference.features", "features"):
        return discover(payload)
    return dependencies.dispatch(action, payload)
