"""Evidence-aware orthographic registration and bounded perspective PnP hypotheses."""
import math

from projection import camera_spec, camera_points, pixels_from_camera, project_points


def _inputs(payload):
    import numpy as np
    world = np.asarray(payload.get("worldPoints", []), dtype=float)
    image = np.asarray(payload.get("imagePoints", []), dtype=float)
    if world.ndim != 2 or world.shape[1] != 3 or image.shape != (len(world), 2) or len(world) < 3 or not np.isfinite(world).all() or not np.isfinite(image).all():
        raise ValueError("calibration requires matching finite worldPoints Nx3/imagePoints Nx2, N>=3")
    centered = world - world.mean(axis=0)
    singular = np.linalg.svd(centered, compute_uv=False)
    rank = int((singular > max(singular[0], 1.) * 1e-8).sum())
    scale_known = payload.get("scaleKnown", False) is True
    diagnostics = {"anchorCount": len(world), "anchorRank": rank, "anchorSingularValues": singular.tolist(),
                   "scaleStatus": "metric" if scale_known else "relative_unknown_scale", "uncertainties": []}
    if not scale_known:
        diagnostics["uncertainties"].append("absolute_scale_unproven")
    if rank < 2:
        diagnostics["uncertainties"].append("collinear_or_coincident_anchors")
    elif rank == 2:
        diagnostics["uncertainties"].append("coplanar_anchors_pose_ambiguity")
    return world, image, diagnostics


def _residual_report(predicted, observed):
    import numpy as np
    residuals = np.linalg.norm(predicted - observed, axis=1)
    return {"rmsPx": float(np.sqrt(np.mean(residuals ** 2))), "p95Px": float(np.percentile(residuals, 95)),
            "maxPx": float(residuals.max()), "perAnchorPx": residuals.tolist(), "worstAnchorIndex": int(np.argmax(residuals))}


def orthographic(payload):
    import numpy as np
    world, image, diagnostics = _inputs(payload)
    if diagnostics["anchorRank"] < 2:
        return {"status": "underconstrained", "candidates": [], "diagnostics": diagnostics}
    base = payload.get("camera", {})
    width, height = payload.get("width", base.get("width")), payload.get("height", base.get("height"))
    given_matrix = payload.get("worldToCamera", base.get("worldToCamera"))
    if given_matrix is None:
        if diagnostics["anchorRank"] < 3:
            diagnostics["uncertainties"].append("supply_known_view_basis_or_noncoplanar_anchors")
            return {"status": "underconstrained", "candidates": [], "diagnostics": diagnostics}
        design = np.column_stack((world, np.ones(len(world))))
        coefficients = np.linalg.lstsq(design, image, rcond=None)[0].T
        row_x, row_y = coefficients[0, :3], -coefficients[1, :3]
        scale_x, scale_y = np.linalg.norm(row_x), np.linalg.norm(row_y)
        if min(scale_x, scale_y) < 1e-12:
            return {"status": "underconstrained", "candidates": [], "diagnostics": diagnostics}
        shear = float(abs(row_x @ row_y) / (scale_x * scale_y))
        diagnostics["affineAxisNonOrthogonality"] = shear
        if shear > payload.get("maxAxisNonOrthogonality", .03):
            diagnostics["uncertainties"].append("not_consistent_with_orthographic_rigid_camera")
            return {"status": "inconsistent", "candidates": [], "diagnostics": diagnostics}
        row_x /= scale_x
        row_y -= (row_y @ row_x) * row_x
        row_y /= np.linalg.norm(row_y)
        matrix = np.eye(4)
        matrix[:3, :3] = [row_x, row_y, np.cross(row_x, row_y)]
    else:
        # Validate the supplied orientation without using it to absorb shape discrepancies.
        validated = camera_spec({"projection": "orthographic", "width": width, "height": height,
                                 "worldToCamera": given_matrix, "orthographic": {"scaleX": 1}})
        matrix = np.asarray(validated["worldToCamera"])
        diagnostics["knownViewBasis"] = True
        diagnostics["uncertainties"] = [x for x in diagnostics["uncertainties"] if x != "coplanar_anchors_pose_ambiguity"]
    coords = world @ matrix[:3, :3].T
    design_x = np.column_stack((coords[:, 0], np.ones(len(world))))
    design_y = np.column_stack((-coords[:, 1], np.ones(len(world))))
    if np.linalg.matrix_rank(design_x) < 2 or np.linalg.matrix_rank(design_y) < 2:
        diagnostics["uncertainties"].append("unobservable_image_axis_scale")
        return {"status": "underconstrained", "candidates": [], "diagnostics": diagnostics}
    sx, cx = np.linalg.lstsq(design_x, image[:, 0], rcond=None)[0]
    sy, cy = np.linalg.lstsq(design_y, image[:, 1], rcond=None)[0]
    if sx <= 0 or sy <= 0:
        diagnostics["uncertainties"].append("view_axis_direction_conflict")
        return {"status": "inconsistent", "candidates": [], "diagnostics": diagnostics}
    # Translation along the view direction is not observable from an orthographic image.
    # Choose a documented positive depth offset; image-center translation stays in cx/cy.
    matrix[:2, 3] = 0
    near = float(payload.get("near", .01))
    matrix[2, 3] = float(payload.get("depthOffset", max(1., near + 1. - coords[:, 2].min())))
    diagnostics["uncertainties"].append("orthographic_depth_offset_unobservable")
    camera = camera_spec({"projection": "orthographic", "width": width, "height": height,
                          "worldToCamera": matrix.tolist(), "near": near, "far": payload.get("far", 100000),
                          "orthographic": {"scaleX": float(sx), "scaleY": float(sy), "cx": float(cx), "cy": float(cy)}})
    residual = _residual_report(pixels_from_camera(camera_points(world, camera), camera), image)
    status = "registered" if residual["maxPx"] <= payload.get("maxResidualPx", 3.) else "inconsistent"
    return {"status": status, "camera": camera, "cameraFrozen": True,
            "candidates": [{"camera": camera, "residual": residual}], "diagnostics": diagnostics,
            "acceptanceStatus": "camera_registered" if status == "registered" else "needs_review"}


def perspective(payload):
    import cv2
    import numpy as np
    from scipy.optimize import least_squares
    world, image, diagnostics = _inputs(payload)
    if len(world) < 4 or diagnostics["anchorRank"] < 2:
        diagnostics["uncertainties"].append("pnp_requires_four_noncollinear_correspondences")
        return {"status": "underconstrained", "candidates": [], "diagnostics": diagnostics}
    width, height = payload["width"], payload["height"]
    known = payload.get("intrinsics")
    focal_range = payload.get("focalBounds")
    if known is None and (not isinstance(focal_range, list) or len(focal_range) != 2 or not 0 < focal_range[0] < focal_range[1]):
        raise ValueError("perspective calibration requires intrinsics or positive bounded focalBounds")
    cx = float(known.get("cx", width / 2)) if known else float(payload.get("cx", width / 2))
    cy = float(known.get("cy", height / 2)) if known else float(payload.get("cy", height / 2))
    if known:
        focals = [float(known["fx"])]
        fy_ratio = float(known.get("fy", known["fx"])) / focals[0]
    else:
        focals = np.geomspace(*focal_range, num=min(15, max(3, int(payload.get("focalCandidates", 7)))))
        fy_ratio = float(payload.get("fyRatio", 1))
        diagnostics["uncertainties"].append("focal_length_estimated_with_declared_bounds")
    if not math.isfinite(fy_ratio) or fy_ratio <= 0:
        raise ValueError("fyRatio must be positive")
    # Flip input pixel y about cy for this module's camera convention (+y up).
    cv_image = image.copy()
    cv_image[:, 1] = 2 * cy - cv_image[:, 1]
    candidates = []
    for focal in focals:
        intrinsics = np.array([[focal, 0, cx], [0, focal * fy_ratio, cy], [0, 0, 1]], dtype=float)
        method = cv2.SOLVEPNP_IPPE if diagnostics["anchorRank"] == 2 else cv2.SOLVEPNP_SQPNP
        inlier_indices = np.arange(len(world))
        if payload.get("ransac", True) and len(world) >= 6:
            try:
                valid, _, _, inliers = cv2.solvePnPRansac(world, cv_image, intrinsics, None,
                    iterationsCount=200, reprojectionError=float(payload.get("ransacThresholdPx", 3.)),
                    confidence=.999, flags=cv2.SOLVEPNP_EPNP)
                if valid and inliers is not None and len(inliers) >= 4:
                    inlier_indices = np.sort(inliers.ravel())
            except cv2.error:
                pass
        inlier_world, inlier_image = world[inlier_indices], cv_image[inlier_indices]
        try:
            solved = cv2.solvePnPGeneric(inlier_world, inlier_image, intrinsics, None, flags=method)
        except cv2.error:
            continue
        if not solved[0]:
            continue
        for rvec, tvec in zip(solved[1], solved[2]):
            initial = np.r_[rvec.reshape(3), tvec.reshape(3), focal] if not known else np.r_[rvec.reshape(3), tvec.reshape(3)]
            def residual(parameters):
                f = parameters[6] if not known else focal
                k = np.array([[f, 0, cx], [0, f * fy_ratio, cy], [0, 0, 1]])
                projected, _ = cv2.projectPoints(inlier_world, parameters[:3], parameters[3:6], k, None)
                return (projected.reshape((-1, 2)) - inlier_image).ravel()
            lower = np.r_[np.full(6, -np.inf), focal_range[0]] if not known else np.full(6, -np.inf)
            upper = np.r_[np.full(6, np.inf), focal_range[1]] if not known else np.full(6, np.inf)
            optimized = least_squares(residual, np.clip(initial, lower, upper), bounds=(lower, upper),
                                      loss="soft_l1", f_scale=float(payload.get("robustScalePx", 2.)), max_nfev=200)
            rotation, _ = cv2.Rodrigues(optimized.x[:3])
            matrix = np.eye(4); matrix[:3, :3] = rotation; matrix[:3, 3] = optimized.x[3:6]
            f = float(optimized.x[6] if not known else focal)
            camera = camera_spec({"projection": "perspective", "width": width, "height": height,
                                  "worldToCamera": matrix.tolist(), "intrinsics": {"fx": f, "fy": f * fy_ratio, "cx": cx, "cy": cy},
                                  "near": payload.get("near", .01), "far": payload.get("far", 100000)})
            coords = camera_points(world, camera)
            if (coords[:, 2] <= camera["near"]).any():
                continue
            residuals = _residual_report(pixels_from_camera(coords, camera), image)
            # Focal refinement can make initially rejected points consistent.
            # Reclassify against the final hypothesis before reporting exclusions.
            final_inliers = np.flatnonzero(np.asarray(residuals["perAnchorPx"]) <= float(payload.get("ransacThresholdPx", 3.)))
            if len(final_inliers) >= 4:
                inlier_indices = final_inliers
            inlier_residuals = _residual_report(pixels_from_camera(coords, camera)[inlier_indices], image[inlier_indices])
            singular = np.linalg.svd(optimized.jac, compute_uv=False)
            jac_rank = int((singular > max(singular[0], 1.) * 1e-7).sum())
            candidate = {"camera": camera, "residual": residuals, "jacobianRank": jac_rank,
                         "inlierResidual": inlier_residuals, "inlierIndices": inlier_indices.tolist(),
                         "outlierIndices": sorted(set(range(len(world))) - set(map(int, inlier_indices))),
                         "parameterCount": len(optimized.x), "conditionNumber": float(singular[0] / singular[-1]) if singular[-1] > 1e-12 else None}
            duplicates = [i for i, c in enumerate(candidates) if np.linalg.norm(np.asarray(c["camera"]["worldToCamera"]) - matrix) < 1e-4 and abs(c["camera"]["intrinsics"]["fx"] - f) < 1e-3]
            if not duplicates:
                candidates.append(candidate)
            elif (-len(candidate["inlierIndices"]), candidate["residual"]["rmsPx"]) < (-len(candidates[duplicates[0]]["inlierIndices"]), candidates[duplicates[0]]["residual"]["rmsPx"]):
                candidates[duplicates[0]] = candidate
    candidates.sort(key=lambda c: (-len(c["inlierIndices"]), c["inlierResidual"]["rmsPx"]))
    if not candidates:
        return {"status": "no_valid_solution", "candidates": [], "diagnostics": diagnostics}
    cutoff = float(payload.get("maxResidualPx", 3.))
    good = [c for c in candidates if c["inlierResidual"]["maxPx"] <= cutoff]
    best = candidates[0]
    ambiguous = diagnostics["anchorRank"] == 2 or best["jacobianRank"] < best["parameterCount"] or len(good) > 1
    if ambiguous:
        diagnostics["uncertainties"].append("multiple_or_weak_camera_hypotheses")
    status = "ambiguous" if ambiguous else ("registered" if good else "inconsistent")
    if best["outlierIndices"] and not payload.get("allowRejectedAnchors", False):
        status = "inconsistent_correspondences"
        diagnostics["uncertainties"].append("ransac_rejected_anchors_require_review")
    return {"status": status, "camera": best["camera"], "cameraFrozen": status == "registered",
            "candidates": candidates, "diagnostics": diagnostics,
            "acceptanceStatus": "camera_registered" if status == "registered" else "hypothesis_requires_review"}


def calibrate(payload):
    projection = payload.get("projection", "orthographic")
    if projection == "orthographic":
        return orthographic(payload)
    if projection == "perspective":
        return perspective(payload)
    raise ValueError("unsupported calibration projection")


def project(payload):
    from projection import pixel_ray
    if "pixel" in payload:
        return pixel_ray(payload["pixel"], payload["camera"], payload.get("plane"), payload.get("depth"))
    return project_points(payload["points"], payload["camera"])
