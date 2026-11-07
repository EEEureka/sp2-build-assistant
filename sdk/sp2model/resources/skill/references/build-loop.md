# Goal-driven building loop

Use this for geometry work with shared boundaries, reference fidelity, replacement, or repeated player reports of missed details. A simple isolated color edit needs its material readback and appearance check; it does not require a whole-craft geometry campaign. Keep the user's requested scope and original acceptance criteria throughout the loop.

## Start with observable goals

Record the user's subject, required details, source/reference, acceptance method and tolerance, protected fields, and direct editable scope. Identify expected continuous boundaries and intentional creases. Bind semantic ownership and actual part IDs to a fresh craft session/revision; names and numeric IDs alone are not stable identities.

Record related objects separately: geometric neighbors, mirror counterparts, above/below and fore/aft interfaces, cutter targets, shared materials, native attachment dependents and functional assemblies. Each relation needs its basis. Native graph connectivity does not prove touching surfaces, and proximity does not imply a design requirement to join. Use the union of before/after relations so an old contact that disappears is still checked. Distinguish certain dependencies, candidate spatial neighbors and unknown coverage.

For broad edits, store the goals and iterations in the local build-loop journal. Discover the installed contracts before preparing input:

```powershell
sp2model commands schema --command build.loop.init --json
sp2model commands schema --command build.loop.review --json
sp2model commands schema --command parts.observe --json
sp2model commands schema --command regional.review --json
```

The entrypoints are `sp2model build loop init/status/review/amend/rebind --input FILE --json`, `sp2model parts observe --input FILE --json`, and `sp2model regional review --input FILE --json`. Inspect each command's schema for its current fields; these are local evidence/planning tools, not an autonomous live geometry repair command. If the installed CLI does not advertise them, maintain the same goal/evidence record explicitly and use available native inspection commands. Do not substitute a repository Python entrypoint or claim an unavailable feature ran.

## Execute a coupled batch, then inspect two reports

Choose the next batch from unresolved goals and the latest evidence. Prefer editing the existing native body and jointly parameterizing shared contours; a successful write is an intermediate state. Preserve current player work field by field and resolve unknown operation outcomes before another mutation.

After native reconstruction, obtain actual geometry and relevant readbacks at a consistent identity, then produce both reports:

| Report | Questions to resolve |
| --- | --- |
| Subject | Are the user's shape, position, appearance, openings and requested details correct? Are there new protrusions, gaps, folds, coarse curves or duplicate skins in the subject? |
| Related impact | Did neighbors, shared edges, mirror parts, cutters, deck/roof interfaces or functional dependencies regress? Did moving the subject create or remove a contact? Which previously verified goals now need rechecking? |

Use [continuity review](continuity-review.md) for complete boundary/normal/contour evidence. Use [visual inspection](visual.md) and [designer screenshots](designer-screenshots.md) for actual images. Pair an isolated shape view with a view containing its neighbors. A body-sized detail tile may still hide a small defect: locate the suspected edge or face, inspect its projection and occlusion, and request a local oblique/grazing view when needed. Actually open recommended images; a returned path is not a vision result. Analysis colors cannot validate native paint.

Reports should give each finding's object/boundary, witness location, measured or visual evidence, certainty and remaining coverage. Distinguish defect, review candidate, missing evidence and justified design feature. A local all-pass report is bounded by the reported interfaces/observations; it is not whole-craft certification. Do not delete a component solely because its AABB overlaps another, its mesh is absent, or an old ID was once redundant; a Hole or buried cap may be functional.

`parts.observe` defaults to `detail:"summary"`: read concise shape, role, position, typed relationships, findings and image navigation first. Its `reportArtifact.path` contains the full actual contours, control readbacks and acceptance evidence; the returned SHA-256 binds those persisted bytes. Supply that full artifact to `build.loop.review`, or request `detail:"full"` when detailed inline data is needed. Abbreviated summary checks are navigation records, not substitute measurement evidence.

Provide `baseline:{snapshot,mesh,partIds}` for before/after overlays and relation propagation. Replacement comparisons additionally need explicit `replacements:[{semanticId,fromPartIds,toPartIds}]`; the system does not guess correspondence from a reused number. A `referenceMesh` with verified units, provenance and an explicit affine world transform enables same-frame reference layers and measured `referenceMatches`; a reference hash alone does not compare surfaces. All layers share a projection/scale, with their distinct source identities retained. Reference triangles outside the displayed local ROI are omitted only from the view, not certified absent.

For native appearance, `captureNativeViews:true` executes the planned read-only native captures. Inspect returned actual images before supplying `nativeImageReviews`, keyed by native view request ID, with each image's SHA-256, `status:"inspected"`, `visibility` and `outcome`. Planning, capture, framing checks and pixel inspection are separate states. Occlusion rays predict geometry visibility; only opened native images establish what is visible. See [continuity review](continuity-review.md) for complete boundary contracts and camera limits.

## Derive the next iteration from both reports

Build the next targets from:

1. Unfinished original subject goals and newly discovered subject defects.
2. Related regressions or requirements exposed by this iteration.
3. Previously passed goals whose geometry, material, relationship or reference evidence changed.
4. Necessary inspections for uncertain findings or missing evidence.

Each target needs a source finding/evidence, semantic owner and current identity, intended outcome, coupled scope, protected fields and verification method. Coalesce findings that share a contour or parameter rather than fixing their symptoms independently. An uncertain cause produces an inspection target first, not a guessed shape edit. Keep unrelated discoveries separate and do not silently expand the authorized construction scope. Preserve unaffected passed goals and keep the original user objective as the completion criterion.

For example, correcting a hangar's inward inclination may pass the hangar goal but expose a fore-hull fold and deck gap. The next target jointly fits that shared side plane and deck boundary with affected fore/aft sections. Its acceptance rechecks the original hangar angle, the new seams and both sides; it does not replace the hangar goal with a new checklist of the easiest measurements.

## Evidence and stopping behavior

Bind evidence to craft session/revision, geometry stamp/sample, frames/units, relevant field fingerprints and reference version. After replacement or ID reuse, resolve semantic mapping before comparisons. After a restart or player edit, rebind from actual current state; a local journal does not grant permission to replay old operations or roll back intervening player work.

`build.loop.rebind` accepts `semanticMapping` from each old ID to a list of current IDs: one-to-one, splits, merges, or `[]` for explicit retirement. Split/merge/retirement requires reviewed ownership evidence; split/retirement also binds `structureId` and `planHash`. Retirement must prove the old ID absent in the current snapshot and name nonempty surviving `supportPartIds` that carry its original regional obligation. Keep that obligation and ownership history; deleting its former part does not complete its goal. A new revision needs new current absence evidence.

Protected fields retain their original frozen values. Use explicit `protectedFieldMapping` when a field moves to another part/path or a source splits/retires; position and length protection must not fan out automatically. Conflicting frozen values cannot merge into one field, and rebinding cannot redefine a protection value. In structure plans, `partMapping` remains a single connection anchor per surviving source; `semanticMapping` records every candidate's actual semantic ownership. Validate every candidate's material slots against declared intent or frozen source materials, not only the anchor. Check surviving perimeter neighbors before retiring originals.

Keep native facts, actual-mesh measurements, reference observations and inferred roles distinct in a part observation report. Show concise shape/location/relationship findings first, with traceable raw fields available for precise edits. Do not describe an idealized box or an interpolated proxy as the actual cut native surface. Unknown topology or an unseen side remains unknown.

Require both subject and related-impact acceptance, adequate declared coverage and current evidence before completion. Check the affected region deeply and use a cheaper broader regression appropriate to the edit; repeat broader expensive checks when a new change or unresolved issue warrants them. If repeated iterations do not improve the result, inspect source completeness, registration, shape ownership, native expression/calibration and the inspection itself. Change the construction hypothesis or report an unresolved limitation; do not add cover skins, loosen error budgets or mark evidence gaps as passes to end the loop.

Accepted impact evidence freezes the discovered dependencies and a whole-inventory geometry basis. Changes to a previously unrelated part's pose, shape, visibility, cut targets or native connections can introduce a new contact; an empty old impact list is not permission to skip discovery. A new, deleted or changed outside object generates `system:impact-rediscovery` while unaffected subject goals retain their verified history. Supply fresh regional discovery with complete **before and after** inventories bound to the accepted basis; a current-only capture cannot exclude a lost former contact. Full native world/metre bounds inventories can cheaply exclude objects only when their old and current bounds are both distant. Scoped `mesh.complete` alone means its requested renderer scope, not complete inventory discovery. Missing discovery stays an inspection task.

## Version changes

Record game, loaded plugin/protocol, CLI capability and calibration versions for native shape assumptions. A game update can change generator behavior even when the setter accepts the same field. Read the current schema and effective controls, test the relevant generator on an authorized scope, and inspect its actual mesh before reusing a calibration. Current schema discovery and empirical native validation have different roles: neither is replaced by a version string or `validated:true` in an input file.

`sp2model knowledge capabilityaudit --input FILE --json` organizes supplied same-state native snapshots, mesh and effective shape evidence into versioned, exact-case observations. It distinguishes readable controls, measured observations and uncalibrated domains; it does not write a test craft, validate arbitrary interpolation or declare a split necessary. Read [low-part native modeling](low-part-native-modeling.md) when selecting a calibrated construction.
