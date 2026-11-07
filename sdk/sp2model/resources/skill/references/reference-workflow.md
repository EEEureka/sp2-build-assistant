# Reference projects, fixed views, comparison and bounded fitting

Use the globally installed `sp2model` command for every command below. Discover the installed contract with `sp2model commands schema --command reference.compare --json` (or the relevant command). Local analysis does not require a running game. `fit apply` and structure replacement use the public native bridge and require the intended craft already open. Do not read or modify native saved-craft XML files.

The CPU worker supplies deterministic projection, clipping, depth/ID/mask rasterization, camera registration, comparison and bounded least squares. It does not segment photographs, reconstruct unseen geometry or produce arbitrary freeform native parts. Current precise native fitting is limited to rigid translation of an actual exported baseline mesh, inside a domain calibrated against the same native operation, part family and game version. Bounded property and fuselage-section candidates are advisory until their native mesh proxy is implemented and validated.

## Product setup and JSON files

```powershell
sp2model version --json
sp2model features list --json
sp2model reference doctor --json
sp2model commands schema --command fit.apply --json
```

`reference doctor` must report a successful numerical self-test before numerical work. Ordinary commands never install or download dependencies. A missing worker leaves image metadata, OBJ/Blender-file loading, projects and core commands usable. The supported worker is CPython 3.12 x64 with locked NumPy/Pillow/OpenCV-headless/SciPy; use `feature setup` when installation is authorized, rather than installing arbitrary package versions or using Blender Python.

Examples below use PowerShell and explicit JSON input files. `--output` saves the complete CLI envelope, so extract `.data` before embedding a result in another request. A raw downloaded `meshes.json` already is a mesh artifact and has no CLI `.data` wrapper.

```powershell
$work = 'D:\reference-work\example'
New-Item -ItemType Directory -Force -Path $work | Out-Null
function Save-ReferenceJson($path, $value) {
    [IO.File]::WriteAllText($path, ($value | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false))
}
function Read-ReferenceData($path) {
    $response = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if (-not $response.success) { throw ($response.error | ConvertTo-Json -Depth 20) }
    return $response.data
}
```

Check shell exit codes, `success`, the command's evaluation/acceptance status and any operation state. A successful analysis command can return `underconstrained`, `insufficient_evidence`, `proxy_invalid` or `needs_revision`.

## Register sources and scope

```powershell
sp2model reference create --project "$work\project.json" --name 'Example exterior' --json
Save-ReferenceJson "$work\source.json" @{
    project="$work\project.json"
    source=@{id='front-v1';kind='image';path='D:\references\front.jpg';metadata=@{view='front'}}
}
sp2model reference add --input "$work\source.json" --json
sp2model reference inspect --project "$work\project.json" --json
sp2model reference validate --project "$work\project.json" --json
```

Each source records an absolute original path and SHA256. A changed source needs investigation and a new version ID; duplicate IDs are rejected. Define precedence when multiple sources describe the same semantic structure. Projects use metres; every source conversion must be explicit.

When native work is needed, obtain a fresh `craft snapshot` including XML through the public command, then bind only the agreed part scope:

```powershell
sp2model craft snapshot --input snapshot-request.json --output "$work\snapshot.json" --json
# snapshot-request.json: {"includeXml":true}
$snapshot = Read-ReferenceData "$work\snapshot.json"
# Choose IDs from this snapshot; do not copy numeric IDs from an earlier session.
Save-ReferenceJson "$work\bind.json" @{
    project="$work\project.json";snapshot=$snapshot;partIds=@(123,124)
}
sp2model reference bind --input "$work\bind.json" --json
```

Use `structure set` to record stable semantic roles, source IDs, editable parts and locked parts; use `reference freeze` to store an immutable tolerance profile before optimization. For example, a structure contains `id`, `partIds`, `lockedPartIds`, `roles:[{role,partIds}]`, `sourceIds` and `toleranceProfile`; a profile contains `id` and `metrics:[{name,target,unit,referenceUncertainty,measurementError}]`. These project profiles are evidence records: pass the intended numerical thresholds explicitly to `reference compare` and freeze those definitions into `fit plan`. Local annotate/calibrate/compare outputs do not automatically add themselves to the project.

## Images and original pixel coordinates

```powershell
sp2model image inspect --path 'D:\references\front.jpg' --output "$work\front-original.json" --json
Save-ReferenceJson "$work\normalize.json" @{
    path='D:\references\front.jpg';outputPath="$work\front-normalized.png"
}
sp2model image normalize --input "$work\normalize.json" --output "$work\front-normalized.json" --json
```

Inspection reads metadata without changing pixels. Normalization decodes the image, applies EXIF orientation and writes a separate copy. Preserve the original hash, raw and normalized dimensions, and the returned 3×3 coordinate transform. Coordinates are zero-based pixel centres; EXIF rotations/reflections use `width-1` or `height-1` offsets. A viewer's display coordinates are not automatically original-file coordinates.

`reference annotate` draws numbered points, polylines and regions onto a supplied preview image. `points` are in original-image coordinates. If the displayed image is normalized/cropped/scaled, supply the original dimensions and the composed `originalToPreview` matrix. A crop with top-left `(left,top)` and scale `(sx,sy)` uses `[[sx,0,-sx*left],[0,sy,-sy*top],[0,0,1]]`, composed after the EXIF matrix. Preserve an invertible transform; convert clicks back through its inverse before recording them.

```json
{
  "sourceId":"front-v1",
  "imagePath":"D:\\reference-work\\example\\front-normalized.png",
  "outputPath":"D:\\reference-work\\example\\front-numbered.png",
  "originalSize":[1920,1080],
  "originalToPreview":[[1,0,0],[0,1,0],[0,0,1]],
  "annotations":[
    {"id":"bow","semanticId":"hull.bow.tip","kind":"point","points":[[140,540]],"status":"measured","visibility":"visible","uncertaintyPx":2},
    {"id":"deck","semanticId":"hull.deck.edge","kind":"polyline","points":[[140,540],[1700,540]],"status":"inferred","visibility":"visible","uncertaintyPx":4}
  ]
}
```

```powershell
sp2model reference annotate --input annotations.json --output "$work\annotations-result.json" --json
sp2model reference constraints --input constraints.json --output "$work\constraints-result.json" --json
```

The image coordinates above illustrate the schema; measure actual source coordinates before use. Semantic IDs match the same feature across images and must be unique within an image. Distinguish `measured`, `inferred` and `unconstrained`; visibility is `visible`, `occluded`, `unknown` or `ignored`. Drawing a hidden point does not make its location measured. Open the numbered preview before confirming that the annotations represent the intended features.

Constraints are evaluated, not just stored. A minimal `constraints.json` is:

```json
{"unit":"px","points":{"A":[0,0],"B":[100,0],"C":[100,50]},"constraints":[
  {"id":"AB","kind":"distance","points":["A","B"],"target":100,"tolerance":1},
  {"id":"ABC","kind":"angle","points":["A","B","C"],"target":90,"tolerance":0.5}
]}
```

Supported relations also include `parallel`, `perpendicular`, `equalLength` (four points), and `symmetry` (two points plus `plane:{point,normal}`). Point records may contain `position`, `status` and `visibility`. Missing/unconstrained/occluded evidence remains missing; degenerate line directions do not pass as zero error. Pixel constraints are not metric dimensions without scale evidence.

## OBJ files and Blender exchange files

```powershell
sp2model mesh load --input obj-source.json --output "$work\reference-mesh.json" --json
# obj-source.json:
# {"path":"D:\\references\\model.obj","unit":"m","upAxis":"+Y","forwardAxis":"+Z",
#  "selection":{"objectNames":["hull"],"groupNames":["port"]}}
sp2model blender load --input blender-source.json --output "$work\exchange-mesh.json" --json
# blender-source.json:
# {"path":"D:\\references\\exchange.json","selection":{"objectIds":["hull"],"includeHidden":false,"includeExcluded":false}}
```

OBJ has no reliable built-in scale: declare `unit` (`m/cm/mm/ft/in`) and axes. Inspect source object/group/material IDs, original-face mapping, bounds and diagnostics before comparison. Concave polygons are triangulated; invalid indices and missing units are errors. OBJ cannot prove hidden objects were exported.

Blender exchange is a file format, separate from controlling the live Blender application. Loading it requires neither Blender nor MCP. Export each mesh's local `vertices`, zero-based `triangles`, `matrixWorld`, object ID/name, `visible`, `hidden`, `excluded`, plus top-level units, axes, exporter version and scope. The adapter applies object transforms before units/axes and corrects mirrored winding. Missing matrices/visibility/exported geometry remain explicit uncertainties. Capture evaluated geometry, modifiers and instances when the intended reference requires them; the loader cannot infer omitted scene data.

```json
{"schemaVersion":1,"units":"m","upAxis":"+Z","forwardAxis":"-Y",
 "blenderVersion":"record actual exporter version","exportScope":"record actual scope",
 "objects":[{"id":"hull","name":"Hull","type":"MESH","visible":true,"hidden":false,"excluded":false,
   "matrixWorld":[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],
   "vertices":[[0,0,0],[1,0,0],[0,1,0]],"triangles":[[0,1,2]]}]}
```

Both adapters yield the same mesh contract: `vertices`, `triangles`, `faceObjectIds`, source/object metadata, conversions and diagnostics. Use `(Read-ReferenceData "$work\reference-mesh.json")` as a mesh object. Numerical mesh arguments also accept the path to a **raw** mesh JSON file; they do not unwrap a saved CLI envelope automatically.

## Camera registration and fixed projection

All numerical cameras use `+X` right, `+Y` up, `+Z` forward and pixels `x` right/`y` down. `worldToCamera` is a rigid, right-handed row-major 4×4 transform; units are metres. Positive camera depth must lie between `near` and `far`. Orthographic scales are pixels/metre; perspective `fx/fy` are pixels. Freeze the returned `camera` and `cameraHash` before editing.

This small offline fixture is reproducible and does not touch the game:

```powershell
$mesh = @{vertices=@(@(0,0,0),@(1,0,0),@(0,1,0));triangles=@(@(0,1,2));faceObjectIds=@('fixture')}
$camera = @{
    projection='orthographic';width=256;height=256;near=0.01;far=100
    worldToCamera=@(@(1,0,0,0),@(0,1,0,0),@(0,0,1,5),@(0,0,0,1))
    orthographic=@{scaleX=80;scaleY=80;cx=128;cy=128}
}
Save-ReferenceJson "$work\render-input.json" @{mesh=$mesh;camera=$camera;outputDirectory="$work\fixture-render";includeBuffers=$false}
sp2model reference render --input "$work\render-input.json" --output "$work\render-result.json" --json
Save-ReferenceJson "$work\calibrate-input.json" @{
    projection='orthographic';width=256;height=256;scaleKnown=$true
    worldPoints=$mesh.vertices;imagePoints=@(@(128,128),@(208,128),@(128,48))
    worldToCamera=$camera.worldToCamera;maxResidualPx=0.01
}
sp2model reference calibrate --input "$work\calibrate-input.json" --output "$work\calibration.json" --json
$registered = Read-ReferenceData "$work\calibration.json"
$frozenCamera = $registered.camera
```

Known orthographic orientation needs noncollinear anchors spanning both image axes; an unknown orientation needs noncoplanar anchors. Review per-anchor residuals, rank and uncertainties. Orthographic depth offset is unobservable even when registration passes. `scaleKnown:true` is a declaration requiring real metric evidence, not a command that discovers scale.

For perspective, supply corresponding `worldPoints` / `imagePoints`, image dimensions and either `intrinsics:{fx,fy,cx,cy}` or positive `focalBounds:[min,max]`. Example additional fields are `projection:"perspective"`, `focalBounds:[600,1600]`, `ransac:true`, `ransacThresholdPx:3`, `maxResidualPx:3`, `scaleKnown:true`. At least four noncollinear correspondences are needed; noncoplanar distributed anchors are preferable. Inspect **all** returned `candidates`, rejected anchors and planar/weak-pose diagnostics. Unknown scale, unknown focal length and planar multi-solutions must remain visible in the report. Do not silently permit rejected anchors; `allowRejectedAnchors:true` requires an evidence-based decision.

```powershell
Save-ReferenceJson "$work\project-input.json" @{camera=$frozenCamera;points=@(@(0,0,0),@(1,0,0))}
sp2model reference project --input "$work\project-input.json" --json
Save-ReferenceJson "$work\ray-input.json" @{camera=$frozenCamera;pixel=@(128,128);plane=@{point=@(0,0,0);normal=@(0,0,1)}}
sp2model reference project --input "$work\ray-input.json" --json
```

A pixel without a plane or camera-space depth returns a ray (`point:null`), not a known 3D point. Ray/plane parallelism and near/far failures are explicit. The renderer provides triangle-depth occlusion, an object-ID buffer and a mask; its colours are analysis colours, not native paint. Use `designer capture` separately for actual game appearance and open the returned image before claiming visual inspection.

## Compare without moving the camera

```powershell
$render = Read-ReferenceData "$work\render-result.json"
Save-ReferenceJson "$work\compare-input.json" @{
    actualMesh=$mesh;referenceMask=$render.files.mask;compareSurface=$false
    camera=$frozenCamera;cameraFrozen=$true;expectedCameraHash=$frozenCamera.cameraHash
    tolerances=@{silhouette=@{p95=0.1;max=0.1;iou=0.999}}
    outputDirectory="$work\fixture-overlay"
}
sp2model reference compare --input "$work\compare-input.json" --output "$work\comparison.json" --json
```

For photographs, supply a reviewed binary `referenceMask` of the measured object rather than the photograph itself. The worker does not derive that mask automatically. Mask dimensions must exactly match the frozen camera; use `ignoreMask` for occluded/unknown pixels. Use `regions` with stable IDs, `referenceIds`, `actualIds`, optional masks, sections, features and per-region tolerances. Record explicit exclusions and `unobserved` areas; an excluded region has no passing measurements.

For 3D comparison, provide `referenceMesh` and actual current native `actualMesh`, with `sampleCount` or an explicitly affordable `sampleSpacing`. Add sections such as `sections:[{id:"station",plane:{point:[0,0,0],normal:[0,0,1]},sampleSpacing:0.05}]`; corresponding tolerances are `{"surface":{"max":0.01,"p95":0.005},"section.station":{"max":0.01}}`. Local section planes use `point`; native `geometry section` export planes use `origin`.

Semantic features use `semanticId`, `kind:"point"|"polyline"`, `referencePoints` and either `actualPoints` or `actualWorldPoints`, plus visibility/status. Thresholds address the generated metric key, for example `"feature.hull.bow.tip":{"residual":2}`. World features project through the frozen camera; clipped/hidden/unknown features stay missing.

Read both directions' P95/max and worst-point witnesses, IoU, valid area, face/sample coverage, diagnostics and units. Surface queries measure points to triangles, not just nearest vertices. Finite samples do not prove a continuous Hausdorff bound; inspect `coverageComplete` and `continuousErrorBoundProven`. Empty contours, missing sections, absent thresholds or an unfrozen camera cannot yield a passing comparison. An image match alone does not prove a 3D surface match.

## Freeze a bounded fit and validate the actual native result

Start from a fresh `craft snapshot` and complete same-revision world-frame mesh export for every affected and frozen part. For native export use `geometry section` with `partIds`, `frame:{kind:"world"}`, `plane:{origin:[0,0,0],normal:[0,1,0]}`, `limit:1`, `export:true`, `exportMeshes:true`, current session/revision, and `--output-dir`. Check `complete`, `staleAtDelivery`, identity, geometryStamp and downloaded file hashes. Missing/excluded geometry prevents full-scope acceptance.

For a precise translation fit, calibrate the proxy **before** optimizing: apply declared small bounded translations on an authorized test copy, export each actual native mesh, compare against a translated baseline mesh, record predeclared error budget, actual errors, identities and hashes, then restore the baseline with a valid checkpoint. The native acceptance fixture tested all 8 corners of a three-axis `±0.05 m` box. This is evidence for that operation/family/version; it does not calibrate shape edits or prove an arbitrary larger domain. Never create `validated:true` or `nativeEvidence` from expected values.

A translation plan uses the following fields, assembled from those actual records:

```json
{
  "parameters":[
    {"name":"tx","value":0,"min":-0.05,"max":0.05,"binding":{"kind":"translation","partIds":[123],"axis":"x"}},
    {"name":"ty","value":0,"min":-0.05,"max":0.05,"binding":{"kind":"translation","partIds":[123],"axis":"y"}},
    {"name":"tz","value":0,"min":-0.05,"max":0.05,"binding":{"kind":"translation","partIds":[123],"axis":"z"}}
  ],
  "model":{"kind":"translation_points","points":[[0,0,0],[1,0,0],[0,1,0]],
    "targetPoints":[[0.03,-0.0216,0.0264],[1.03,-0.0216,0.0264],[0.03,0.9784,0.0264]],
    "parameterAxes":{"tx":"x","ty":"y","tz":"z"}},
  "tolerances":{"maxResidual":0.000001},"budget":{"maxEvaluations":100},
  "requireNativePrecision":true
}
```

This fragment is deliberately incomplete for native apply: replace IDs and points with measured native bindings, then add the actual `model.mesh` baseline, `identity`, `geometryStamp`, `gameVersion`, `shapeFamily`, `proxyCalibration` and frozen `validation`. `proxyCalibration` requires matching `gameVersion`, `shapeFamily`, `domains` for every parameter, `maxError`, `errorBudget`, `validated` and actual `nativeEvidence`. Do not reuse the example coordinates as evidence for another craft.

`validation` is a complete `reference compare` request without the actual mesh: freeze target mesh/mask, regional tolerances, primary camera, `cameraFrozen:true` and sample budget. Add `independentViews:[{camera, cameraFrozen:true, referenceMesh or referenceMask, compareSurface:false, tolerances:{silhouette:{max:...,iou:...}}}]`. Choose this view before optimization and keep it out of training targets. A duplicate camera or the same orthographic direction with another zoom/pan is not independent. Native validation derives holdout evidence from the actual exported mesh; a boolean is insufficient.

```powershell
sp2model fit plan --input "$work\fit-input.json" --output "$work\fit-plan.json" --json
$plan = (Read-ReferenceData "$work\fit-plan.json").plan
Save-ReferenceJson "$work\evaluate-input.json" @{plan=$plan}
sp2model fit evaluate --input "$work\evaluate-input.json" --output "$work\candidate.json" --json
$candidate = Read-ReferenceData "$work\candidate.json"
# Inspect stopReason, diagnostics, proxyValidation, candidates, best and operations first.
Save-ReferenceJson "$work\apply-input.json" @{
    plan=$plan;candidate=$candidate;partIds=@(123)
    frame=@{kind='world'};journalPath="$work\fit-native-journal.jsonl"
    parameterTolerance=0.00005;requireIndependentView=$true;rollbackOnFailure=$true
}
sp2model fit apply --input "$work\apply-input.json" --output "$work\fit-native-result.json" --json
```

`fit plan` hashes parameters, native bindings, baseline identity/stamp, model, validation targets and tolerances. Changing any frozen definition requires a new plan and candidate. Scalar `frozen:true` and `frozenPartIds` are enforced; the apply export scope must include every affected/frozen part. Native translation bindings are world-axis deltas, so native fit rejects other export frames.

`fit evaluate` only proposes a candidate. It accounts for actual model calls, including finite-difference Jacobian calls, and reports rank/conditioning. Single orthographic-view depth is unobservable; regularization cannot turn an underconstrained model into a measured solution. `orthographic_translation_points` / `perspective_translation_points` use `points` in 3D, `targetPoints` in pixels, a frozen `camera` and `parameterAxes`. A generic `linear` model uses `matrix`, optional `offset`, `targets` and optional `weights`; it is useful for advisory bounded shape parameters and has no implemented precise native mesh proxy.

Typed advisory native bindings are `{kind:"property",partId,propertyId}` using a discovered effective numeric property, and `{kind:"fuselageSection",partId,sectionIndex,field:"width"|"height"|"trapezium"}` using an existing native section. There is no arbitrary operation template. Native application must still read back effective values and actual geometry; advisory candidates do not justify a precise shape-fidelity claim.

`fit apply` performs a fresh identity/geometry guard, baseline comparison, checkpoint, native batch, same-result native mesh export, parameter readback, frozen target/holdout comparisons and proxy comparison. It rejects a candidate that worsens an already measured regional maximum. Inspect `nativeAcceptanceProven`, `acceptanceStatus`, `stopReason`, comparisons, actual identity/stamp, checkpoint and journal. `fit verify` is available for re-evaluating the complete captured evidence, but manually supplying a passing report does not perform native readback.

On a known failed final validation, rollback is guarded against intervening edits. On an unknown native outcome, stop dependent writes and reconcile the recorded operation/request before another attempt; do not replay with a new request ID or automatically restore over an unknown state. A changed craft/session, reused part ID, native undo/save/recenter or restart needs fresh observations and binding. Use `reference changes` / `reference rebind` with the current snapshot to diagnose pose changes and part mapping; never copy an old revision onto old IDs.

## Completion and representation limits

Record tool execution, reference uncertainty, actual surface/section/seam measurements, fixed views actually opened, native appearance and the user's aesthetic judgment separately. Stop reasons include `underconstrained`, `representation_limited`, `proxy_invalid`, `budget_exhausted`, `stagnated`, `state_changed` and `native_validation_incomplete`; retain the unresolved regions and parameters.

For plane/wedge or other native construction planning, inspect `representation check` and `shape plan` contracts and the finite native domain before choosing components. Structure replacement has its own plan, dependency/material migrations, locks and persistent recovery journal; read [precision-building.md](precision-building.md) and [edits.md](edits.md) before execution. Reference content does not automatically authorize added weapons, sensors or unrelated assemblies.

After saving, obtain the returned native identity, rebind/re-export as required by recentering, and repeat the same frozen reference-frame measurements and native views. Do not re-fit the camera to conceal a shape error. Preserve original sources, transforms, hashes, plans, before/after geometry, numerical reports, opened images and recovery records with the result.
