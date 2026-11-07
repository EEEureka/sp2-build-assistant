"""Small robust bounded least squares with rank diagnostics and best-candidate retention."""
import math

from fit_parameters import validate_parameters


def residual_function(model, parameters):
    import numpy as np
    from projection import camera_spec, camera_points, pixels_from_camera
    names = [p["name"] for p in parameters]
    kind = model.get("kind")
    if kind == "linear":
        matrix = np.asarray(model["matrix"], dtype=float)
        offset = np.asarray(model.get("offset", [0] * len(matrix)), dtype=float)
        targets = np.asarray(model["targets"], dtype=float)
        weights = np.asarray(model.get("weights", [1] * len(matrix)), dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != len(names) or offset.shape != targets.shape or targets.shape != weights.shape or targets.shape != (len(matrix),) or not all(np.isfinite(a).all() for a in (matrix, offset, targets, weights)) or (weights <= 0).any():
            raise ValueError("linear model needs finite matrix MxN, offset/targets/positive weights M")
        return lambda values: (matrix @ np.asarray([values[n] for n in names]) + offset - targets) * np.sqrt(weights)
    if kind in ("translation_points", "orthographic_translation_points", "perspective_translation_points"):
        points = np.asarray(model["points"], dtype=float)
        targets = np.asarray(model["targetPoints"], dtype=float)
        axes = model.get("parameterAxes", {})
        if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0 or not np.isfinite(points).all() or not np.isfinite(targets).all():
            raise ValueError("translation model requires finite points Nx3")
        if set(axes) != set(names) or any(axis not in ("x", "y", "z") for axis in axes.values()) or len(set(axes.values())) != len(axes):
            raise ValueError("translation parameterAxes must assign a unique axis to each parameter")
        projected = kind != "translation_points"
        camera = camera_spec(model["camera"]) if projected else None
        if projected and ((kind == "orthographic_translation_points") != (camera["projection"] == "orthographic")):
            raise ValueError("translation image model and camera projection differ")
        if targets.shape != (len(points), 2 if projected else 3):
            raise ValueError("translation targetPoints dimension differs")
        def evaluate(values):
            displacement = np.zeros(3)
            for parameter in parameters:
                name = parameter["name"]
                displacement["xyz".index(axes[name])] = values[name] - parameter["value"]
            moved = points + displacement
            if projected:
                local = camera_points(moved, camera)
                if (local[:, 2] <= camera["near"]).any():
                    raise ValueError("fit candidate crosses the camera near plane")
                moved = pixels_from_camera(local, camera)
            return (moved - targets).ravel()
        return evaluate
    raise ValueError("unsupported fit model; first release supports linear observables and constrained point translations")


def optimize(parameters, model, budget=None, tolerance=None, robust_scale=1., regularization=0.):
    import numpy as np
    from scipy.optimize import least_squares
    parameters = validate_parameters(parameters)
    budget = budget or {}; tolerance = tolerance or {}
    maximum = int(budget.get("maxEvaluations", 100))
    if not 1 <= maximum <= 10000 or not math.isfinite(robust_scale) or robust_scale <= 0 or not math.isfinite(regularization) or regularization < 0:
        raise ValueError("invalid fit evaluation budget/robustScale/regularization")
    free = [p for p in parameters if not p["frozen"]]
    baseline = {p["name"]: p["value"] for p in parameters}
    raw_function = residual_function(model, parameters)
    model_evaluations = 0
    class BudgetReached(Exception):
        pass
    def function(values):
        nonlocal model_evaluations
        if model_evaluations >= maximum:
            raise BudgetReached()
        model_evaluations += 1
        return raw_function(values)
    initial_residual = np.asarray(function(baseline), dtype=float)
    if not initial_residual.size or not np.isfinite(initial_residual).all():
        raise ValueError("fit model must return nonempty finite residuals")
    def score(residual):
        # Same soft-L1 objective used by the solver; candidates never win by iteration order.
        return float(np.sum(2 * robust_scale ** 2 * (np.sqrt(1 + (residual / robust_scale) ** 2) - 1)))
    base_score = score(initial_residual)
    candidates = [{"values": baseline.copy(), "objective": base_score, "maxResidual": float(abs(initial_residual).max()), "source": "baseline"}]
    if not free:
        return {"best": candidates[0], "candidates": candidates, "stopReason": "frozen_parameters", "diagnostics": {"freeParameterCount": 0, "jacobianRank": 0}}
    if maximum < 1 + 2 * len(free):
        return {"best": candidates[0], "candidates": candidates, "stopReason": "budget_exhausted",
                "diagnostics": {"freeParameterCount": len(free), "jacobianRank": None, "modelEvaluations": model_evaluations}}
    x0 = np.asarray([p["value"] for p in free], dtype=float)
    lower, upper = np.asarray([p["min"] for p in free]), np.asarray([p["max"] for p in free])
    def expand(x):
        return {**baseline, **{p["name"]: float(v) for p, v in zip(free, x)}}
    # Identifiability is checked on the unregularized observable Jacobian: a prior
    # must not create evidence for a single-view depth or another invisible parameter.
    columns = []
    for index in range(len(free)):
        step = max(1e-6, (upper[index] - lower[index]) * 1e-5)
        a, b = x0.copy(), x0.copy()
        a[index] = max(lower[index], x0[index] - step); b[index] = min(upper[index], x0[index] + step)
        columns.append((function(expand(b)) - function(expand(a))) / (b[index] - a[index]))
    jacobian = np.column_stack(columns)
    u, singular, vt = np.linalg.svd(jacobian, full_matrices=True)
    rank = int((singular > max(singular[0] if len(singular) else 0, 1.) * 1e-7).sum())
    diagnostics = {"freeParameterCount": len(free), "jacobianRank": rank, "singularValues": singular.tolist(),
                   "conditionNumber": float(singular[0] / singular[-1]) if len(singular) and singular[-1] > 1e-12 else None,
                   "unobservableDirections": vt[rank:].tolist() if rank < len(free) else []}
    if rank < len(free):
        return {"best": candidates[0], "candidates": candidates, "stopReason": "underconstrained", "diagnostics": diagnostics}
    def objective(x):
        residual = np.asarray(function(expand(x)))
        if not np.isfinite(residual).all():
            raise ValueError("nonfinite candidate residual")
        maximum_residual = float(abs(residual).max())
        if regularization:
            residual = np.r_[residual, math.sqrt(regularization) * (x - x0) / np.maximum(upper - lower, 1e-12)]
        current = {"values": expand(x), "objective": score(residual), "maxResidual": maximum_residual, "source": "solver"}
        if current["objective"] < min(c["objective"] for c in candidates) - 1e-12:
            candidates.append(current)
        return residual
    exhausted = False
    try:
        fitted = least_squares(objective, x0, bounds=(lower, upper), loss="soft_l1", f_scale=robust_scale,
                               max_nfev=maximum, xtol=1e-10, ftol=1e-10, gtol=1e-10)
    except BudgetReached:
        fitted = None; exhausted = True
    best = min(candidates, key=lambda c: c["objective"])
    target = tolerance.get("maxResidual")
    if target is not None and best["maxResidual"] <= target:
        reason = "tolerance_met"
    elif exhausted or fitted.status == 0:
        reason = "budget_exhausted"
    elif any(abs(best["values"][p["name"]] - bound) <= 1e-6 for p in free for bound in (p["min"], p["max"])) and target is not None:
        reason = "representation_limited"
    else:
        reason = "stagnated"
    diagnostics.update(modelEvaluations=model_evaluations, solverEvaluations=int(fitted.nfev) if fitted else None, solverStatus=int(fitted.status) if fitted else 0,
                       objectiveImprovement=base_score - best["objective"])
    return {"best": best, "candidates": candidates, "stopReason": reason, "diagnostics": diagnostics,
            "proxyToleranceMet": reason == "tolerance_met", "nativeAcceptanceProven": False}
