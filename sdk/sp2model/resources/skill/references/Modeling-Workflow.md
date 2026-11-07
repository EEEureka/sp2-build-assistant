# Native modeling workflow — 0.7.2 development

Use this for new models, reconstruction and shape diagnosis. Blender, photos, drawings and verbal dimensions are reference options; Blender is optional. Simple edits can reuse still-valid component evidence and run only the relevant phase.

1. Record the original intent and actual subject. Prefer the correctly installed reference over an origin duplicate. Declare units, axes, installation frame, scale sources, handedness and uncertain dimensions; photographs do not define hidden geometry.
2. Decompose semantic features and complete shared interface profiles. Compare native continuous shapes before splitting. Curved's middle section is a control, Cone's tip is zero, corner samples determine polygon geometry, and omitted cutting retains its old value. Wings and mechanical components need native adapters.
3. Freeze required metrics, frames, tolerances, protection and budgets. Distinguish pose/scale, complete contours, folds/normals, curved surfaces, negative space, seams/installation and function. Extent is one metric, not a whole-model certificate. Correct inconsistent targets with original values and reasons retained; do not call a relaxed target an improved model.
4. Review reference, proportions, primary_shape, openings_interfaces, secondary, detail_material and function_delivery. Relevant earlier requirements must pass before dependent detail or retirement. Keep the old representation while measuring candidates and review overlap/collision effects separately.
5. Measure current native meshes at the same identity and actually inspect fixed views. Classify reference, measurement, parameters, representation, tool or scene residuals before another edit. Record hypothesis, related parameters, before/after evidence and costs. Average improvement cannot excuse a failed seam, opening, function or protected item. Stop honestly at tolerance, stagnation, insufficient constraints, representation limits, invalid measurement, tool blocking, scene change or budget exhaustion.

## Public task state

`session.task(path, name=..., intent=..., max_candidates=8, max_iterations=12, max_native_operations=800, minimum_improvement_m=.001)` creates external metadata. Every task script reuses the same task, project and execution-journal paths. The [runnable lifecycle example](../examples/modeling_task.py) supplies complete build/check/resume/save/reopen/rebind/checkpoint/restore actions. Copy and adapt it to the user's actual reference and required coverage. Its default action is read-only resume; write actions need `apply:true`. It refuses to rerun an existing build task.

Start with the contract, not a completed model plus a retrospective report. Use `task.apply` for each candidate/correction plan; it links the original execution before POST. Bind native members explicitly and use `task.check` for fresh geometry/pose checks. Keep fitting algorithms/data alongside the public task. A task is an evidence workflow, not a mesh importer, autonomous fitter or guarantee of DSH context retention.

When the user's contract specifies budgets, pass its candidate/iteration/native-operation values explicitly to the task constructor and its part budget to the candidate. Review `task.report()["budget"]` and `usage` before freeze/writes; defaults are not the user's budget. Native operations and command POSTs are different costs. Every host envelope exposes `transport.commandPostAttempts` for that Python invocation; aggregate it across scripts, including failed invocations. It counts attempted unknown submissions, excludes GET polls/artifacts and never reads a token. Unavailable counters remain unavailable. Leave budget for verification/delivery; never relax the frozen cap to finish.

```python
from sp2model import Section
task = session.task("shape-task.json", name="Square housing", intent="A one metre wide square housing")
task.reference("oral", kind="verbal", source="1 m square housing, 2 m long", subject="housing at the requested installation")
task.component("shell", intent="continuous square section", strategy="one native Body")
task.extent("width", component="shell", reference_id="oral", axis=(1,0,0), value_m=1)
# Add the independent contour/opening/seam/function requirements for this task.
task.freeze()
task.candidate("body-a", components=["shell"], strategy="one Body", part_budget=1)
plan = session.plan(writable=[])
plan.body("housing", (0,3,-1), (0,3,1), [Section(1,1), Section(1,1)])
receipt = task.apply("body-a", plan)  # execution link persists before submission
task.bind("body-a", "shell", [receipt.objects["housing"]])
result = task.check("body-a")  # this minimal contract certifies width only
```

The full runnable example also freezes height, length, a complete middle contour and installation pose. Add independently required openings, folds, seams, surfaces, function and protected state for the real task; never copy its limited denominator as whole-model acceptance.

`task.contour(id, component=..., reference_id=..., origin=..., normal=..., segments=..., tolerance_m=..., stage="primary_shape")` compares a complete reference section with native segments. `task.probe(..., point=..., inside=...)` checks one point when a closed native surface is available. These dimensions are metres in the declared frame. They do not implement arbitrary reference fitting or full curved-surface certification.

`task.pose(...,position_m=...,rotation_quaternion=...,tolerance_deg=.01)` and `task.measure_pose(candidate,metric,anchor)` check one explicit native anchor pose. `task.seam(...,origin=...,normal=...)` and `task.measure_seam(candidate,metric,left_mesh,right_mesh)` compare complete native profiles on both interface sides; they do not infer external-reference correctness or group rigidity. Native meshes must come from SHA256-verified session.mesh captures.

For separately bound semantic components, register both sides **before freeze**: `task.seam("joint", component="front", other_component="rear", reference_id="source", origin=(0,0,0), normal=(0,0,1))`. `task.check` then captures each component once and compares their complete interface contours. Omitting `other_component` means the metric's single component explicitly represents the entire pair, so its bound membership must cover both sides. Do not add a second component's parts to a frozen shape component simply to evade a coverage error; amend an incorrect contract explicitly.

`task.metric(...)` also registers visual, complete-surface and function requirements. Complete single-part surface evaluation is supported as described below. Visual/dynamic function requirements remain not_assessed until their appropriate evidence exists; the current helper cannot certify them. Extent cannot stand in for them. Evidence is invalidated when the observed native identity changes because part fingerprints alone cannot prove that an external cutter/host did not alter geometry.

`task.parts(candidate, component)` returns current explicitly bound members; it does not guess from a reused ID or name. `task.check(candidate, metric_ids=None)` refreshes native state, captures once per component/frame and evaluates extent, section, occupancy and single-part surface metrics plus single-member pose anchors. All frozen required metrics remain in the report even when checking a subset. Multi-part pose anchors, seams without declared opposite components and visual/function evaluations require their explicit evaluator and are not silently passed. Historical observations are retained across edits and invalidated by native identity changes.

The helper evaluates the represented required metrics (or the explicit subset), including seams with declared opposite components. It uses a read-only native identity fence around the batch and refreshes at delivery, rather than a status request for every metric. A concurrent edit invalidates the captured observations or stops the check; it cannot turn old evidence into a current pass. Standalone `measure`/`measure_pose`/`measure_seam` retain their individual freshness guards. This reduces read cost without broadening write scope or relaxing identity checks.

`task.advance(candidate_id, stage)` moves one phase after relevant prerequisites. `task.iteration(candidate_id, residual_kind=..., hypothesis=..., parameter_group=[...], cost={...})` stores immutable iteration evidence. `task.keep_best(candidate_id)` pins a native checkpoint/evidence and refuses regression of previously passed features. This is a whole-craft anchor: restore still needs current whole-craft review and must not overwrite concurrent edits implicitly. Candidate ranking/minimum-improvement diagnostics are advisory; the tool does not autonomously select geometry or guarantee convergence.

`task.retirement_plan(candidate_id, old_parts, writable=reviewed_parts)` returns a plan after required component metrics pass. Fresh references are mandatory and replacement members cannot be deleted as old parts. Connection/logic migration must be explicitly reviewed; apply is separate. `task.stop(reason, details=...)` retains the stop reason; within_tolerance requires the entire frozen metric denominator to pass.

Frozen contract hashes detect accidental in-memory/on-disk target or budget changes. Reference file hash changes block new writes/acceptance and appear in task reports. `task.amend_metric(new_path, metric_id, reason=..., expected=..., tolerance_m=...)` creates a fresh draft evaluation retaining the original target/contract/reason; it imports no successful candidate or measurements. Review and freeze it explicitly. Correcting a target is not measured model improvement. Iteration records include per-metric changes, significant-improvement threshold and required-feature regressions.

## Continue, save/reopen and restore

After a Python process interruption or reporting error, attach to the intended current craft through `sp2model run`, reuse `--project`, `--journal-dir` and task path, then run `task = session.task(path); result = task.resume()`. Resume queries the original linked plan/control/checkpoint requests, never submits geometry or repeats a control action. Review `pendingExecutions`, lifecycle receipts, bindings and remaining metrics. Missing result retention or a missing submission link remains unresolved; never infer cancellation. A native game process replacement requires explicit reconciliation, not automatic task migration.

```python
# Separate scripts can execute each boundary using the same task/project files.
saved = task.save("SP2-My-Model", overwrite=False)
craft_id = saved["persistedCraft"]["craftId"]  # exact native persisted ID
task = task.reopen(craft_id, discard_current=True)
session = task.session                         # explicit NEW native Session
task.rebind("body-a")                          # content/pose/lifetime evidence
result = task.check("body-a")                  # old measurements cannot pass
```

Saving may recenter the craft; fixed world targets can legitimately fail afterward. Choose the intended installation/reference frame before freeze. Do not move targets, broaden tolerances or mark stale evidence current just to pass. A rebind ambiguity/content mismatch fails without partial task bindings; review current native members and pass an evidenced `mapping` or explicitly `task.bind` them. `accept_native_endpoint_roundtrip=True` is only the documented explicit native endpoint-roundtrip exception, not general tolerance relaxation.

After rechecking the reopened craft, keep a best anchor in that **current epoch**. A checkpoint from before reopening cannot be restored into the new epoch.

```python
task.keep_best("body-a")
# A later unsuccessful candidate may now be inspected and measured.
review = task.restore_preview()                # read-only whole-craft diff
result = review                               # inspect before the write below
# In a subsequent script, after reviewing every overwritten change:
result = task.restore(review["token"], accept_whole_craft=True)
task.rebind("body-a", from_best=True)
result = task.check("body-a")
```

The task persists restore reviews and links controls/checkpoints before POST. Tokens remain usable across Python script restarts only while the native review is unchanged. Reusing a submitted restore token queries its original request, including after script restart; it never performs a second rollback. An external revision invalidates an unused review. Recovery success, exact/partial restoration, binding status and fresh shape acceptance are separate. After exact restore, `task.rebind(candidate, from_best=True)` explicitly uses the retained candidate/project evidence from that checkpoint. It requires the matching reviewed checkpoint, exact restoration and unchanged current identity; content, pose, uniqueness and lifetime checks remain strict. Ordinary `rebind` uses the latest project evidence, which may describe the unsuccessful candidate. A partial restoration needs explicit current investigation and fresh bindings rather than the best-evidence shortcut. Whole-craft restore needs explicit current scope review and can overwrite unrelated changes; never trigger it automatically on a local failure. User approval is only needed when that overwrite exceeds the task's existing authorization.

Only call `task.stop("within_tolerance", details=...)` after all declared required features pass at the delivery identity. A subsequent save/reopen or edit invalidates old measurements and the report becomes needs_review. Fixed-view visual review and actual dynamic tests remain separate evidence.

## Native evidence

`session.mesh(parts, frame=None)` captures indexed native meshes and verifies SHA256 and identity. `MeshEvidence.to_dict()` returns a compact receipt; include_geometry=True explicitly returns vertices/indices. Retain artifacts promptly because native retention is bounded.

`mesh.section(origin, normal, weld_tolerance_m=1e-6)` returns per-part segments, loops, open paths and branch diagnostics. It never force-closes a gap or applies an inter-part Boolean union. Coplanar internal triangulation edges are removed by incidence. Empty/unresolved sections remain incomplete.

`compare_contours(reference_segments, actual_segments, tolerance_m=..., sample_spacing_m=.005, max_samples=250000)` reports bidirectional sampled distance and a conservative between-sample bound. Small sampled error can still be incomplete. Coverage is only the supplied piecewise-linear contours, not a full ideal surface.

`compare_surfaces(reference_triangles, actual_triangles, tolerance_m=..., max_samples=50000, max_triangle_tests=2000000)` checks both entire explicit triangle sets with a spatial tree and adaptive triangle cells. It reports numerical lower/upper bounds and actual measurement costs; exhausted budgets remain incomplete. Matching vertices or extents cannot hide a missing face or protrusion. These are bounds for the selected triangulations with floating point padding, not a certificate for an ideal CAD surface. A surface is not implicitly united with neighboring parts.

Register `task.metric("skin", component=..., kind="surface", reference_id=..., expected={"triangles": reference_triangles}, tolerance_m=...)` before freeze, then `task.measure(..., session.mesh(parts))`. This evaluator requires one bound native part, explicit complete reference faces and matching frames. Multiple parts need a reviewed exterior/union policy and currently remain incomplete; overlapping interior faces cannot silently stand in for an exterior. Keep each source object's face selection, units and transform with the reference record. Visual and dynamic function metrics remain separate pending real evidence.

Read [advanced native interfaces](Advanced-Native.md) for wings, controls, shafts, sphere/dome, native attributes, logic and recovery. Historical CIWS/main-gun successes and the failed guided DSH reconstruction remain in the repository methodology document. Development scripts are not clean-Agent effectiveness evidence.
