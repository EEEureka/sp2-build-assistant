"""Isolated, one-request UTF-8 JSON worker. No network, game writes or global imports."""
import json
from pathlib import Path
import sys

# Only the owning SDK installation is added under -I. The numerical environment
# is separate; the old CLI tree and host site packages are never imported.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
__package__ = 'sp2model._services.reference_worker'



def dispatch(action, payload, context=None):
    if not isinstance(payload, dict):
        raise ValueError("worker payload must be an object")
    if action in ("doctor", "selftest"):
        import numpy as np
        import PIL
        import cv2
        import scipy
        from ..reference_render import render_mesh
        camera = {"projection": "orthographic", "width": 16, "height": 16, "orthographic": {"scaleX": 4},
                  "worldToCamera": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 3], [0, 0, 0, 1]]}
        rendered = render_mesh({"vertices": [[-1, -1, 0], [1, -1, 0], [0, 1, 0]], "triangles": [[0, 1, 2]]}, camera)
        passed = bool(rendered["mask"].any()) and np.allclose(rendered["depth"][rendered["mask"]], 3)
        return {"available": passed, "numericSelftest": "pass" if passed else "fail", "isolated": bool(sys.flags.isolated),
                "versions": {"numpy": np.__version__, "pillow": PIL.__version__, "opencv": cv2.__version__, "scipy": scipy.__version__},
                "actions": ["image.normalize", "reference.annotate", "reference.constraints", "reference.calibrate", "reference.project",
                            "reference.render", "reference.compare", "fit.plan", "fit.evaluate", "fit.verify"]}
    if action == "image.normalize":
        from ..reference_annotations import normalize_image
        return normalize_image(payload)
    if action in ("reference.annotate", "reference.constraints"):
        from ..reference_annotations import annotate, constraints
        return (annotate if action == "reference.annotate" else constraints)(payload)
    if action in ("reference.calibrate", "reference.project"):
        from ..reference_calibration import calibrate, project
        return (calibrate if action == "reference.calibrate" else project)(payload)
    if action == "reference.render":
        from ..reference_render import render
        return render(payload)
    if action == "reference.compare":
        from ..reference_compare import compare
        return compare(payload)
    if action in ("fit.plan", "fit.evaluate", "fit.verify", "fit.proxyCompare"):
        from ..fit_runner import plan, evaluate, verify, proxy_compare
        return {"fit.plan": plan, "fit.evaluate": evaluate, "fit.verify": verify, "fit.proxyCompare": proxy_compare}[action](payload)
    if action == "fit.apply":
        raise ValueError("fit.apply requires host-side guarded native callbacks; CPU worker cannot write to the game")
    raise ValueError("unsupported worker action: " + str(action))


def main():
    try:
        raw = sys.stdin.buffer.read(128 * 1024 * 1024 + 1)
        if len(raw) > 128 * 1024 * 1024:
            raise ValueError("worker request exceeds 128 MiB")
        request = json.loads(raw.decode("utf-8-sig"))
        if request.get("protocolVersion") != 1 or not isinstance(request.get("command"), str):
            raise ValueError("worker request requires protocolVersion=1 and command")
        result = dispatch(request["command"], request.get("payload", {}))
        response = {"success": True, "result": result}
    except ImportError as error:
        response = {"success": False, "error": {"code": "missing_worker_dependency", "message": str(error)}}
    except (ValueError, KeyError, TypeError, OSError) as error:
        response = {"success": False, "error": {"code": "invalid_reference_input", "message": str(error)}}
    except Exception as error:
        # Keep stdout one JSON document even for numeric-library failures.
        response = {"success": False, "error": {"code": "reference_worker_failed", "message": type(error).__name__ + ": " + str(error)}}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False))
    sys.stdout.flush()
    return 0 if response["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
