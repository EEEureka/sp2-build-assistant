# Precision building with DLL 0.5.0

Use the global `sp2model` entrypoint. Inspect `designer status` and its loaded buildId, commands and releaseStatus: installing a CLI does not reload a DLL. Development builds expose provisional adapters; consult the release acceptance report before assuming complete certification.

## Start with a measurable local goal

1. Establish the player's intended shape, function and reference. Separate visible dimensions from inferred ones. Pick a small explicit part set, retain surrounding context, and identify the region that must stay unchanged. For a nose: sections, seams, then glass. For an engine: supported engine/shroud pair, pylon pose, then clearance. For gear: leg/wheel/bay/actuator constraints, then reachable native preview endpoints.
2. Read `craft snapshot`, `parts get`, `shape get` and `properties get --id ID`. For absent parts query `properties describe --template-id TEMPLATE_ID`, which enumerates every member of a composite template. The per-part `total` and `offset` apply independently; request further pages when necessary.
3. Read `commands schema --command COMMAND` or `--operation KIND`. `propertyId` is exact and case-sensitive, including modifier instance index. UI labels and saved XML paths are not interchangeable. `valueAvailable:false` is unknown, not zero; a metadata default is not the live effective value. Honor `editability`, `writeOperation`, `condition`, units, choices and limits. `conditional` means inspect and satisfy the declared condition, not permission to invent parameters.
4. Establish a checkpoint using fresh session/revision/requestId. Record numeric tolerances and freeze the measuring frame and camera views before editing. For comparison, replay `designer capture.data.repeatableViews` and `repeatableResolution`. Auto-fit zoom can hide a real change. Open native images to inspect glass, paint, text, shadows and occlusion; mesh analysis images cannot certify these.

## Choose the native edit path

| Task | Read | Write in an ordered batch |
| --- | --- | --- |
| Fuselage slices/cuts, wing airfoils, slats/flaps/spoilers | `shape get`, `shape schema` | `shape.update`, `fuselage.match`, `wing.control.add` |
| Windows, glass, decal/text dimensions/content/targets | `properties get`, `resources list` | `properties.set` |
| Engine shroud, piston/hinge, gear/wheel/bay | `properties get`, `connections points` | `properties.set` |
| Decal projection pose | `decal pose get` | `decal.pose.set` |
| Local material/texture/slot | `appearance get`, `resources list --category textures` | `appearance.set` with explicit `clone`, `assign` or `shared` mode |
| Rigid positioning of a part set | `groups resolve`, `parts get` | `transform.apply` or `transform.align` |
| Inputs/activation | `parts get` inputControllers | validated `part.update` input path |

Prefer named native dimensions over `Part.scale`. Scaling shifts geometry about the Part origin and can detach fins, wheel pieces or a shroud. Piston `range` is unscaled metres; the physical stroke also includes the native Part axis scale. Shroud radius and related scales are derived from the connected engine and prefab, not independent write fields. Animator keyframes and arbitrary instruments remain outside this version's typed editors: state the limitation, preserve their serialized values, and do not guess XML writes.

Window/bay trapezoid widths, offsets, height, depth and door thickness use Part-local axes. Penetration/corner-radius/other ratios use their discovered native units. Changes that enable another property go in an earlier operation, e.g. targetMode=`Custom` before customPartIds, autoHingeAxis=false before manual hinge poses. Targets are explicit numeric IDs in the current revision; create new parts first, then resolve their final IDs before setting target lists. Set symmetric=false for an isolated edit.

When a typed descriptor includes `currentCondition`, use its `satisfied` flag to check the current native prerequisites before preparing a write. `false` includes a reason; change the prerequisite in an earlier operation and query again. `null` is unknown (including isolated catalog templates without live mounts/connections). `true` checks prerequisites only, so proposed values, resources, symmetry peers and final geometry still require validation. An older DLL may omit the field.

The decal projector origin is the front plane of its volume, not its center. Local +Z spans 0..depth; read decal.pose.get.projectorLocalBox and projectorToWorldRows for effective size/basis. A receiving surface exactly on the front plane can clip a texture decal even when a text decal at that pose remains visible. Place the intended surface inside the volume with a measured margin, avoiding unrelated/back surfaces. properties.get.parts[].textRendering reports current native font glyph availability when present; missing glyphs can render as boxes even though the string was saved correctly. In the tested Roboto font, Chinese “测试” rendered as replacement boxes. Check actual images after selecting text/font.

```json
{
  "craftSessionId": "FROM_FRESH_STATUS", "expectedRevision": 1,
  "requestId": "UNIQUE_REQUEST_ID",
  "operations": [{
    "kind": "properties.set", "partId": 76, "symmetric": false,
    "patch": {"ProceduralWindow[0].height": 0.64}
  }]
}
```

IDs and the property above are examples: discover them in the open craft. Run `sp2model batch preview --input patch.json`, then `sp2model batch apply --input patch.json`. Preview lists checked constraints and pending native validation; it does not simulate native geometry or reserve a revision. Inspect final settled `actualChanges`, `effectiveChanges`, affected IDs and normalization reasons. A successful property setter alone does not prove the visual target is met.

## Position, symmetry and attachment

`groups resolve` accepts the same explicit selectors as visual resolve. A group handle expires on revision changes or reconstructed object identity; resolve again after editing. It is not a persistent assembly identity. A wing and its native controls, a missile and its dependent pieces, or a gear leg and the wheel it actually animates must be selected together when moving rigidly. Inspect `nativeDependencies`; ordinary connectivity, decal targeting and carver targets do not automatically define movement ownership.

`transform.apply` frames are world, craft (main control Part), part or an explicit custom position/quaternion. Frames are rigid: existing nonuniform Part scale never scales the coordinate axes. Quaternions are `[x,y,z,w]`; q and -q are equivalent. Delta applies `p' = pivot + Q(p-pivot) + translation`, `R'=Q*R` after converting the chosen frame to world. Omitted pivot uses the anchor's current position. Absolute mode specifies the anchor's desired pose and preserves the group's rigid offsets. It does not scale the group.

Default transform symmetry is false. With symmetric=true, select one side and let the native symmetry relation expand it; including both the source and its mirrored peer is rejected to avoid applying the transform twice. `transform.align` aligns a chosen attachment point and axis with an optional target-local offset; it uses shortest-axis rotation, without a separate roll constraint, and creates no connection. Conversely `connection.connect` creates topology without general spatial snapping. Keep positioning and connection intent explicit.

For mounting-point compatibility, prefer `connections points` / `parts get` decoded `seekTypes`, `receiveTypes` and `excludeTypes` when present. Legacy `seekType`/`receiveType` can be numeric strings for combined flags (e.g. 1025 means Normal + GearBay), so string equality is insufficient. A candidate needs overlap between the seeking and receiving types and no exclusion on either side, plus available capacity; native validation still decides the final connection. Prefer a free external mount on the assembly, not an engine point already occupied by its shroud.

## Measure, compare and iterate

- `geometry measure`: disjoint `partIdsA/B`, unsigned nearest surface distance with both witness points and normals. Zero may be touching or intersecting; positive distance does not rule out one closed object containing another. No penetration depth is inferred.
- `geometry section`: `partIds`, frame and plane `{origin,normal}`; optionally region `{min,max}`. Returns unordered triangle-plane segments, not an ideal smooth CAD curve. Coplanar triangles are excluded explicitly.
- `geometry seam`: two disjoint part sets, plane and a required local region. Returns bidirectionally sampled max/RMS distance, spacing, normal differences and worst locations. A small whole-part nearest distance cannot prove an entire seam is closed.
- `geometry symmetry`: two disjoint sets and a reflection plane. It samples both reflected surfaces against the opposite side; sample budget is bounded. Increase spacing or narrow the scope if the budget is exceeded. RMS is sample weighted; maxima do not certify unmeasured points.

Choose source renderMesh or collider explicitly when relevant. Collider mode supports exact readable nonconvex MeshCollider and BoxCollider surfaces; convex PhysX hulls and analytic sphere/capsule shapes are excluded. Read `measurement.status`, `complete`, `exclusions`, `capturedFrame`, `geometryStamp` and `staleAtDelivery`. An unavailable or partial result cannot prove clearance. Measurements use an immutable native float-mesh sample with double precision calculation; they exclude shader effects and do not promise ideal parametric accuracy. Region and plane coordinates use the requested rigid frame, whose transform is returned.

Distance normals belong to witness triangles; edges/vertices and tied nearest faces may have several valid normals. Symmetry excludes these ambiguous angle samples and reports normalSampleCount/ambiguousNormalSampleCount; null angle means unavailable, not zero error. Set export=true and exportMeshes=true, with CLI --output-dir, to retain same-sample vertices/indices for independent verification.

For fuselages, read shape.get.sectionCapabilities before composing section patches. A curved middle section is a curve control, so its width/height does not directly equal the resulting surface cross-section. It has no cutting/smoothing/syncAdjacent controls; use geometry section to measure the actual interpolated surface.

Make a small coherent change, read effective values, check its geometry and open fixed-view native pictures. Use `craft diff --checkpoint-id CHECKPOINT` to inspect every changed field, including target references, bindings and material users; explain native derived differences instead of silently ignoring them. Adjust one relevant parameter group at a time and record the metric before and after. Retain a change only if it improves the stated target without damaging the frozen region. Roll back a worse trial with fresh identity.

Stop when the stated measurable targets pass and the native images agree. Also stop and explain when the native representation cannot express the target, a required adapter is unsupported, measurements are incomplete, the trial budget is exhausted, or improvement stalls. Do not turn repeated identical edits into evidence of progress. Report developer self-testing and user aesthetic approval separately; no automatic claim of real-aircraft fidelity or flight stability follows from geometric agreement.

## Materials and recovery

`appearance.set mode=clone` clones one non-reserved palette material, edits it and assigns only the selected Part slots. `assign` changes those slots without editing material values. `shared` deliberately edits the current material for every user in this aircraft and returns the full affected ID list. Read native resources for compatible textures/presets; reserved slots and palette capacity are enforced. Colors are quantized to native RGBA8, so compare returned effective color within that representation. The global custom theme must remain unchanged.

For an unexpected grey/hidden appearance, inspect appearance.get.parts[].designerDisplayState and designer.capture.nativeDisplayOverrides when available. The native designer replaces disconnected parts' materials with grey; palette changes can be correct but visually masked. Captures preserve this state. Confirm the intended connection/display context before using image colors to judge paint edits; do not attach a deliberately independent part merely to make it look painted.

Ordered batches retain one atomic commit. Only adjacent compatible raw Part/InputController edits are merged into one native rebuild; style/shape/native callback boundaries remain ordered. `stageTimings`, `rebuildCount` and complete `effectiveChanges` help diagnose costs. Check beforeCheckpointId for null if session checkpoint capacity is exhausted. Recovery errors can set stateUncertain; stop new writes, inspect the actual state and use an explicit valid checkpoint. Never reuse stale revision or pre-delete numeric IDs after a failed or successful batch.

Rigid transforms are settled and checked before a later operation executes. A later native size/style setter can legitimately move its dependent wheel or control surface. Read the final poses and `effectiveChanges`; an earlier transform's immediate result does not promise that later edits preserve it. Put dimensions before the final rigid pose when that matches the intended modeling order.

`GearLeg[0].gearLegStyle` uses the native serialized style-edit behavior and preserves existing Animator keyframes. It rebuilds live instances; read `effectiveChanges` and re-query mount-dependent fields after changing style. To enable a newly available support strut or catapult setting, put that edit in a subsequent operation so its prerequisites can be checked against the new style. Preserved keyframes still need native-view/clearance inspection: a different leg geometry does not automatically fit the previous poses.

Style propagation respects both the part's symmetry group and the modifier's native synchronization switch. `symmetric: true` permits propagation to eligible peers; it does not override a disabled modifier switch. Use `symmetric: false` for an explicitly single-part edit and verify the affected IDs in `effectiveChanges`.

When present, `validation.retainedNativeCaches` (or failure `rollbackResult.retainedNativeCaches`) reports exact trusted checkpoint center/mass caches retained after tiny native fuselage regeneration drift. This requires all other serialized state already to match, center drift at most 1e-7 metres and mass drift at most 1e-6 native mass units. It is not a relaxed fingerprint or an ignored difference: native cache values are restored, then normal full-state validation runs again. Real shape/pose/fuel/connection differences or larger cache discrepancies still fail recovery.
