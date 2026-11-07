"""Optional reference sources; importing this package needs only Python stdlib."""


def dispatch(action, payload):
    payload = payload or {}
    selection = payload.get("selection")
    if any(key in payload for key in ("includeHidden", "includeExcluded")):
        selection = {"objectNames": selection} if isinstance(selection, list) else dict(selection or {})
        for key in ("includeHidden", "includeExcluded"):
            if key in payload:
                selection[key] = payload[key]
    if action in ("image.inspect", "reference.image.inspect"):
        from .images import inspect_image
        return inspect_image(payload["path"], payload)
    if action in ("image.normalize", "reference.image.normalize"):
        from .images import normalize_image
        return normalize_image(payload)
    if action in ("mesh.load", "mesh.inspect", "reference.mesh.load", "reference.mesh.inspect"):
        from .mesh_file import load_obj
        return load_obj(payload["path"], payload.get("unit", payload.get("units")), payload.get("upAxis", "+Y"), payload.get("forwardAxis", "+Z"), selection)
    if action in ("blender.load", "blender.inspect", "reference.blender.load", "reference.blender.inspect"):
        from .blender_exchange import load_exchange
        return load_exchange(payload["path"], selection)
    raise ValueError(f"Unknown reference provider action: {action}")
