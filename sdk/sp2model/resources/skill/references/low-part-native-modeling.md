# Low-part native modeling

Use this procedure for a continuous hull, fuselage, nose, fairing, nacelle or wing before proposing a decomposition. It selects an economical native representation; it does not certify a globally minimal part count. Read [complex shapes](complex-shapes.md) for field semantics and [reference workflow](reference-workflow.md) for source and measurement contracts.

Keep the subject and related-impact goals in the [building loop](build-loop.md). Fewer parts is one construction objective; it cannot replace the user's shape, openings, materials, functional constraints or continuous interfaces.

## 1. Define the region and its real boundaries

Freeze the intended exterior, openings, separate bodies, hard chines/creases, functional attachments, material regions and protected player work. Assign ownership to each boundary. A reference triangle edge or an arbitrary station/height grid is not a construction boundary.

Verify source units, transforms, object selection, evaluated modifiers and separate visible objects before treating a missing surface as a hole. Keep every contour loop at a station; a single maximum half-width can hide a recess, disconnected bulb or inner surface. Record uncertain or absent reference areas instead of making them construction targets.

A largest-component filter is a selection heuristic, not proof of a complete shell. Shared original vertex indices can separate geometrically continuous panels. Compare full-object and filtered section loops, the center bottom line and extrema; inspect excluded components' original face IDs, bounds and boundary positions before accepting a gap. If an original panel was omitted, create a versioned source selection and refit the continuous body. Keep separate protruding appendages as explicit physical scopes; neither discard them from whole-craft acceptance nor force them into the main-shell fit. Do not invent faces or rewrite the earlier source hash.

Before native edits, bind a fresh complete snapshot and actual geometry to the same session/revision. Preserve current player edits. A changed protected or editable part requires a local reviewed plan based on its current state; an old plan, reused ID or whole-craft rollback does not override that edit.

When the player supplies parts as learning examples, preserve them and inspect their settings to understand native controls. Keep these examples outside the construction/replacement scope unless the player asks to use them in the build.

## 2. Set a cost and acceptance contract

Choose the visible features and regional error limits before fitting. Include independent views, section loops, openings and shared boundaries. Keep reference uncertainty and measurement/proxy error separate from the desired shape error.

Record both whole-craft baseline and proposed regional cost:

| Cost | Evidence |
| --- | --- |
| Native parts and connections | Current snapshot and explicit candidate ownership |
| Render triangles | Actual exported candidate mesh, including caps and duplicate surfaces |
| Colliders and physics geometry | Native collider readback; render triangles are not collider triangles |
| Generation/cooking and interaction cost | Measured native behavior when this is a task constraint |

Use project-specific limits and a bounded trial budget. Do not invent universal FPS, part-count or collider thresholds. Fewer parts with excessive native sampling can still cost more. Unknown physics cost remains unknown.

Label predicted triangle or collider costs as estimates until actual native readback verifies them. A render-mesh count does not establish physics cost or measured frame time.

## 3. Compare the smallest native constructions first

Start with one continuous native body per connected semantic volume, or one native wing per continuous lifting panel. Treat that as a hypothesis, not a guaranteed fit. Compare available fuselage/cone/Curved templates or wing section constructions before adding patches. Discover actual section capabilities and editable properties from the installed schema/current part.

Explore the supported parameter families together:

- End dimensions, offset, pose and trapezium.
- Per-corner radius **and** stretch mode: `cornerStretch:false` uses metres; `true` uses a dimensionless fraction. Check the effective native limits and clamping for the chosen template.
- Per-edge curvature and per-end planar cutting, including asymmetric combinations when the source requires them.
- Available longitudinal interpolation, including a Curved template's middle controls.
- Native wing airfoil, sweep/offset, bend and existing or replaceable stations when modeling a lifting surface.

Match the construction to the surface it owns:

| Intended feature | Native candidates and the decision to inspect |
| --- | --- |
| Continuous polygonal shell or island | Compare one hollow Body with independent corner radius/stretch/sharpness and edge controls before separate thin plates. Verify actual flat faces and corners; rounded corners do not automatically produce the required octagon. A few jointly fitted volumes remain an option for real profile changes or a verified one-body limit. |
| Tapered or bending continuous hull | Compare Body and Curved under shared endpoint contours; a bowed contour may need a middle control rather than several straight intervals. |
| Window, door or local opening | Compare a native Hole targeting the existing host, with the cutter's own outline controls; inspect both exterior trim and interior/back wall. |
| Flat center with curved side transitions | Assign the flat center and bilateral curved edge ownership explicitly. Compare a trimmed continuous native shell and targeted cutters; do not turn the whole transition into an arc because only its sides are curved. |
| Raked closure or trimmed rail | Compare end planar cutting and targeted Hole. Inspect cavity exposure, extra returns and caps; do not hide an incorrect closure with another skin. |

First change the parameterization when it is wrong; do not keep shrinking straight rectangular pieces to approximate a rounded body. Use bounded searches and a short candidate table with costs, remaining residuals and native evidence. “Explore the supported families” means a documented relevant comparison within the trial budget, not an unbounded numerical search or a claim that every parameter combination has been exhausted.

Curved middle dimensions are curve controls, not literal measured station dimensions. In a game 0.7.9.104 native assay, an 8 × 5 middle control with the tested endpoint controls produced an actual 7 × 4.5 mid-section; this is one tested parameter vector, not a general conversion formula. Inspect actual intermediate sections. In the current typed contract, middle controls have no cutting/smoothing/sync fields. Curved does not provide arbitrary section count: typed fuselage edits patch existing indices; choose a supported native template rather than adding slices through raw XML. Native cutting is planar trimming, not arbitrary boolean geometry. The current contract uses `null` for automatic cutting; zero still requests cutting at the nominal boundary. Inspect the installed contract and actual mesh.

Native part position is an authored origin, not proof that a length-L body occupies local Z=[0,L]. A tested length-8 Body generated actual Z=[-4,4] in its observed frame. Establish every plane/station and shared endpoint from the actual transformed mesh; do not compensate for a guessed origin by moving neighboring parts. Rotation, scale, offsets, cutting and native derived transforms can alter the relevant world bounds.

Observation and validation stations are not native control sections. Many densely spaced observations can fit two linear controls or three quadratic Bezier controls. In `representation check`, `sections` are observations; `nativeSectionCount` selects a two/three-control analytic candidate. The check fits/evaluates width/height and any present center offsets across all observations while anchoring the endpoints. Its middle Bezier control is fitted, not copied from the measured midpoint. Optional `model.controlSections` evaluates supplied controls. `modeledFields`, `unmodeledFields` and per-station residuals define the limited result.

`fit_candidate` means those observed scalar fields fit the candidate; `candidate_mismatch` means that candidate failed; `requires_calibration` means the candidate model is unknown or underconstrained. None proves a full native surface, topology or all possible single-part constructions. `splitRequired:false` means no split requirement has been established. Sparse passing observations do not bound the surface between them; add held-out contours and extrema. Unmodeled cutting/corner/thickness controls stay unassessed. The current `shape plan` sections path offers one straight rectangular two-control candidate when appropriate, and does not turn observation intervals into automatic separate bodies. Curved or other uncalibrated recipes return an inspection/calibration requirement without write operations.

For the new straight sections recipe, reuse of `nativeDomain` additionally requires its evidence document to record the same `pluginVersion` as the request, followed by the existing game/template/domain and hashed native-mesh checks. Missing or changed plugin version returns a calibration requirement with no operations. `model.calibration` is only declared version metadata and cannot substitute for that evidence. The legacy finite wall recipe retains its existing contract; its `split_required` result concerns that specific straight rectangular construction, not every native family.

Current native edge curvature is clamped to 0..1; a negative value does not produce arbitrary inward concavity. Combine section size, trapezium, independent corners, offsets and supported trimming before splitting the semantic body. Keep paint boundaries separate from fit residuals: a few complete thin bodies may represent a real waterline stripe, but extra skins must not conceal a failed outer-shape model. For hollow trimmed parts, inspect every section loop; a largest-component filter can select one wall and mistake its inner edge for the opposite outer hull.

## 4. Fit the continuous body before increasing segment count

Fit end sections, intermediate section loops, silhouette and surface witnesses jointly. Hold out another view or additional stations for validation. In rounded regions, measure extrema and changing curvature between controls, not just the controls themselves.

For neighboring bodies, parameterize a shared boundary once and constrain both sides to that boundary throughout its length. Matching endpoint dimensions does not establish a continuous shared edge; width and trapezium interpolation can diverge between endpoints.

Increase render sampling only when actual native geometry shows tessellation error. More corner/edge samples do not add new shape controls and cannot correct a wrong topology or longitudinal shape. Choose collider detail independently according to functional contact needs and verified native limits.

For a cut curve, identify whether the host, its hollow inset, or the Hole generates that edge. More host samples cannot refine a cutter-owned edge without evidence. Compare native generators under the same chord/tangent and shape budgets before changing representation. Record the generator's game/plugin/capability version and parameter domain; version metadata alone is not native calibration. A version change reopens relevant calibration and acceptance rather than proving the old limitation or old fit still applies.

Use `sp2model knowledge capabilityaudit --input FILE --json` to persist exact-case native evidence for closed/hollow Body, corner and edge controls, Curved, section cutting, Hole/Window and cut-edge sampling. Its input supplies native `snapshot`, actual `mesh`, same-state `shapeEvidence`, `versions:{gameVersion,pluginVersion,toolVersion}`, optional current `catalogEvidence`, and bounded `cases` with explicit control paths and actual mesh observations. `readable` means controls are available; `measured_exact_case_only` binds the exact native vector and measured domain; `uncalibrated` creates a calibration task. Source annotations and input claims never replace measurement. It does not generate write operations or establish mass, collision, buoyancy, appearance or an arbitrary parameter range.

Hole/Window editing uses the discovered effective `properties.describe/get` IDs with `properties.set`, including its own outline. In game 0.7.9.104, distinguish their shared `ModifierWindow-1` type by `hideGlass`; missing render geometry alone does not make a cutter redundant. Confirm dynamic `MultipleParts` intersections or explicit `Custom` `customPartIds` and both sides of the result. Compare host-owned rounded edges with cutter-owned edges under measured sampling limits; do not add thin plates because one uncalibrated route failed.

## 5. Diagnose a failed comparison before splitting

Check, in order: source scope/completeness; registration and current transforms; native/proxy agreement; contour ownership and multiple loops; sampling coverage; then the remaining shape residual. A proxy/domain failure is not a native representation failure.

Use bilateral surface witnesses, complete section loops, fixed silhouettes and actual cap/opening/ray checks as applicable. Inspect wrong normals, folds, coincident surfaces and unintended occlusion. State finite coverage limits: corner agreement, a nearest-surface score or a successful setter alone cannot pass the region.

Do not fill a residual with another skin unless it is a separate intended source structure. For each proposed new part, identify the source feature it owns, why existing continuous candidates cannot own it, the boundary it introduces, and the total cost after removing redundant candidates. If that explanation is missing, return to the continuous fit.

## 6. Split only for a demonstrated construction reason

Preferred split locations are a real disconnected volume/opening, a required hard crease, a distinct functional assembly, or a documented limit of the compared native continuous constructions. Preserve actual discontinuities; do not smooth them away to save parts. A lone optimizer failure or a residual peak is insufficient evidence for another segment.

When a smooth region still needs more longitudinal segments, record which native constructions and parameter families were tried, the failing native witnesses and why a different template/control arrangement did not resolve them. Put the new boundary at a meaningful shape transition, jointly refit both neighbors, and remeasure their entire common contour. Compare the resulting construction against the previous simpler one under the same limits.

Among verified candidates meeting the same acceptance and functional constraints, prefer the one with fewer parts unless measured triangle/physics cost or maintainability justifies another choice. Stop at the agreed trial/cost budget with an explicit unresolved region rather than a growing patch stack.

## 7. Native acceptance before replacement

On an authorized test copy or explicitly authorized current scope, make a small candidate and read back its effective parameters, actual render mesh and relevant collider behavior. Keep originals until the candidate's own geometry, placement, materials and dependency migration pass. Candidate validation applies only to its tested family/version/parameter domain.

Before each later write, verify a fresh identity and the frozen authored scope/context. Concurrent player edits take priority; preserve them and replan the affected scope. Unknown accepted outcomes must be attributed through operation status before another mutation. Saving/reopening and whole-region acceptance are separate from a candidate's successful setter.

For replacement, give each new candidate semantic ownership and a connection anchor separately. Split/merge/retirement mapping must preserve original goals, frozen protected values and surviving boundary obligations; verify material slots for **every** candidate before retirement. Use [scoped collaboration](scoped-collaboration.md) for interleaved in-place work. On restart, reconcile saved content and journal receipts before resuming; never infer that a missing old operation permits blind replay or whole-craft rollback.

Report: chosen construction; tested alternatives; parts/render/physics costs; native evidence; remaining errors/unobserved regions; and why each remaining split is needed. Keep geometric acceptance, native appearance and player aesthetic approval separate.
