# Reference feature contracts and JSON example

Use `sp2model model help` with an input file containing `{"operation":"reference.bind","topic":"/properties/spec/properties/features"}` for the current operation schema. This page gives the geometry dictionaries needed by each common feature. All geometry below is already in **task-frame metres**. `spec.frame` describes source-to-task conversion; it does not magically convert numbers inside `features` for you.

Each feature has `id`, `component`, `kind`, `evidenceKind` and `geometry`. `evidenceKind` is `measured`, `user`, `inferred` or `assumption`; the last two need recorded `assumptionAccepted:true` for exact target checks, and remain estimates. A photo/text measurement additionally records `measurementSource`. Each component needs a required `section_contour` or `surface` check: extents/void probes alone are insufficient.

| kind | Required geometry keys and meaning |
| --- | --- |
| `section_contour` | `origin:[x,y,z]`, `normal:[x,y,z]`, `segments:[[[x,y,z],[x,y,z]],...]`. Segments form complete closed coplanar loops. `boundaryRule` is `planar_union`, `single_part` or `cap_boundary`. The current contour union is planar, not arbitrary 3D Boolean union. |
| `section_center` | `origin`, `normal`, `center:[x,y,z]`, `definition:"boundary_bbox"`. This means the bounding-box center of the measured plane boundary, not the native part origin or area centroid. |
| `section_boundary` | `origin`, `normal`, in-plane `axis:[x,y,z]`, `side:"min"` or `"max"`, `valueMetres:number`. The value is the absolute task-coordinate projection onto axis, not a width. |
| `negative_space` | `probes:[[x,y,z],...]`; each declared point must lie outside the component's closed part surfaces. This checks specified points only; pair it with contours so a few empty points do not certify the whole recess. |
| `relative_pose` | `otherComponent:"name"`, `anchor:"mesh_bbox_center"`, `deltaMetres:[x,y,z]`. Delta is **this component center minus otherComponent center**. This checks translation, not rotation. |
| `mesh_extent` | `axis:[x,y,z]`, `valueMetres:number`; measures the span along the direction, and does not replace a contour. |
| `surface` | `triangles:[[[x,y,z],[x,y,z],[x,y,z]],...]`; current exact surface checks support a single native part. Multi-part 3D exterior union stays incomplete; use explicit planar exterior checks where appropriate. |
| `visual` | `requiredViews:["view-id",...]`; image generation never automatically passes visual review. |

Example contour at z=1.5:

```json
{"id":"shell-mid","component":"shell","kind":"section_contour","evidenceKind":"user","tolerance_m":0.01,"geometry":{"origin":[0,0,1.5],"normal":[0,0,1],"segments":[[[-1,-0.5,1.5],[1,-0.5,1.5]],[[1,-0.5,1.5],[1,0.5,1.5]],[[1,0.5,1.5],[-1,0.5,1.5]],[[-1,0.5,1.5],[-1,-0.5,1.5]]],"boundaryRule":"planar_union"}}
```

An identity source frame still needs explicit units/scale/axis labels/handedness/scale source and rotation:

```json
{"units":"m","scale":1,"origin":[0,0,0],"axes":{"x":"right","y":"up","z":"forward"},"handedness":"right","scaleSource":"user","rotationQuaternion":[0,0,0,1]}
```

For a nonidentity source, normalize measurements once using the declared transform before recording these features. Mesh/Blender references also require candidate objects/regions (`id`, `locator`, `transform`, `selection`), `selectedCandidateIds` and a `selectionReason`. Never select origin scraps just because their names match. Photos need files/fingerprint, observable view information and uncertainty; text uses `source.kind:"text"`, `locator`, and `text`, without Blender.

## Generic example requests

[Reference](../examples/semantic_reference.json) describes a user-dimensioned shell and a small marker. It demonstrates contour, center, boundary, void probes and relative placement. [Task](../examples/semantic_task.json) freezes those checks. [Shell](../examples/semantic_prism.json) and [marker](../examples/semantic_marker.json) are separate shape previews. These are an educational box example, not a generic reference importer or an aircraft recipe.

Run from the installed package directory, with a fresh persistent task workspace and the explicitly authorized test craft:

```text
sp2model model reference.bind --workspace demo-task --input-file examples/semantic_reference.json
sp2model model task.create --workspace demo-task --input-file examples/semantic_task.json --instance <id> --craft <current-name>
sp2model model model.prism --workspace demo-task --input-file examples/semantic_prism.json --instance <id> --craft <current-name>
```

Inspect that preview, then write its returned ID to an input file as `{"review_id":"<exact reviewId>"}` and call `edit.apply` with the same workspace and live selectors. Preview/apply the marker similarly. Then call `model.compare`; inspect overlays and required native images. Geometry checks do not connect the two independent sample components or certify dynamics. Each requested real connection must be planned and verified separately.

[Delivery](../examples/semantic_deliver.json) supplies a unique destination name and stable delivery ID; copy it and choose your own unused name before `task.deliver`. After save/reopen, use the returned saved name with the next live selector. A repeated delivery ID continues its original lifecycle, and cannot be changed to another name. A failed/unknown result requires status/original-journal recovery, not replaying the whole request series.

The examples have finite budgets and exact user dimensions. For a real mesh, measured features come from the selected source; for photos/words, explicitly record estimation limits. None of these templates guarantees image understanding or permanent context retention.

## Measure a selected mesh instead of transcribing its coordinates

`reference.measure_mesh` reads inert UTF-8 mesh JSON and requires no live game session, Blender installation, or numerical worker. Use `mesh_path` and the explicit source `frame`; omit `sections` for an inventory of mesh IDs, names, task-space bounds and source SHA256. It never selects a similar-looking object for you. With `sections`, the same command measures reviewed planes and returns complete contours, local centres, four in-plane extremal boundaries, and the corresponding feature dictionaries.

The file format is either `{"vertices":[[x,y,z],...],"indices":[0,1,2,...]}` or `{"meshes":[{"partId":"unique-id","name":"optional name","vertices":[...],"indices":[...]}]}`. Triangle indices may also be triples. Single meshes without `partId` receive `mesh-0`; inspect before choosing. Coordinates are **source-space vertices with object transforms already baked**. Per-mesh transform matrices are rejected; the declared source-to-task frame is applied exactly once. The importer never executes Python, opens a `.blend` scene, or infers source units.

A section explicitly provides `id`, `component`, and exactly one of `partIds` or unique `meshNames`. Choose either `origin` plus `normal`, or `axis` plus `fractions`. All these plane directions and positions are already in **task metres**. Fractions locate planes between the selected geometry's minimum and maximum projection along the declared axis; they do not move or recenter the geometry. `up` fixes width/height orientation for the returned station values. For example:

```json
{"id":"shell-sections","component":"shell","partIds":["chosen-shell"],"axis":[0,0,1],"fractions":[0.1,0.5,0.9],"up":[0,1,0],"viewId":"front","tolerance_m":0.01}
```

Returned `measurements[].station` preserves each plane's own centre, width and height. It can inform `model.loft` with the same `normal` and `profileAxes.up`. A rectangular station is only a bounds suggestion: retain the measured contour, required recesses and other important features. Do not replace every local dimension with the global maximum. The comparison centre uses the documented `boundary_bbox` definition; the station's width/height basis is explicitly reported.

`reference.bind_mesh` takes `reference_id`, `spec`, `mesh_path`, `sections`, and optional `replace`. It measures the file, verifies that the section meshes belong to the explicitly selected candidates, merges generated features with any separately declared negative-space or installation constraints, and freezes a versioned reference. Here `spec.features` can be empty or omitted because the tool derives the geometric features. A candidate's `selection` is `{"partIds":[...]}` or `{"meshNames":[...]}`. Every chosen candidate still needs its locator, baked-transform description and selection reason. File changes between measurement and binding reject the operation; later changes require an explicit new reference version.

For a deliberately declared cap use `boundaryRule:"cap_boundary"`; otherwise coplanar cap slices, open meshes, empty cuts, ambiguous selection and exhausted geometry budgets remain incomplete and cannot freeze targets. Limits are 64 MiB JSON, 250,000 total vertices, 250,000 total triangles, 2,048 mesh records and 32 expanded section planes. The mesh-record allowance supports many disconnected components in a complete assembly; it does not increase the total geometry or section-comparison budgets. This measures the selected planes, not all possible visual features. When source scale is inferred, generated target evidence remains uncertain until an explicit modeling assumption is accepted.

[Measurement request](../examples/semantic_measure_mesh.json), [binding request](../examples/semantic_bind_mesh.json) and [generic mesh](../examples/reference_mesh_demo.json) form a self-contained offline example. Run from the SDK or packaged skill root, or replace `mesh_path` with an absolute path:

```text
sp2model model reference.measure_mesh --workspace measured-demo --input-file examples/semantic_measure_mesh.json
sp2model model reference.bind_mesh --workspace measured-demo --input-file examples/semantic_bind_mesh.json
```

These reference operations do not attach to a game even if live selectors are supplied. They write only their requested reference/workspace evidence. After reviewing the measurements, create the task with `reference_id:"measured-demo"` and its actual component names.

## Short operation examples and local refinement

`operation.example` with `{"operation":"model.loft"}` returns the packaged generic request without opening a session. The same data appears in operation help when it fits the local reply budget. [Loft](../examples/semantic_loft.json), [U channel](../examples/semantic_recess.json), and [station refinement](../examples/semantic_refine.json) are separate syntax examples with generic dimensions; first bind matching reference targets/components. They are not additional pieces of the earlier verbal-box task.

`model.refine` previews a named compiled loft with `station_updates` keyed by stable station ID and optional `protected_station_ids`. Only equal-topology changes are supported. Existing authored shape and pose must still match the prior compilation; unknown changes are not silently accepted. Unmentioned native fields and connections remain untouched. Apply its returned review through `edit.apply`, then compare again. A topology change requires an explicitly reviewed replacement instead.

## Optional Blender export

This is a script the caller deliberately runs in Blender **after selecting the intended installed objects**. It bakes evaluated object transforms and triangulates the selection. The importer itself never executes it. For a merged object, first select/export the intended connected region into separate mesh records; exporting the whole ship does not identify the gun automatically.

```python
import bpy, json
EXPORT_PATH = r"D:\your-task\selected-reference.json"
meshes = []
for obj in bpy.context.selected_objects:
    if obj.type != "MESH":
        continue
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        meshes.append({"partId": obj.name, "name": obj.name,
            "vertices": [list(evaluated.matrix_world @ v.co) for v in mesh.vertices],
            "indices": [i for tri in mesh.loop_triangles for i in tri.vertices]})
    finally:
        evaluated.to_mesh_clear()
with open(EXPORT_PATH, "w", encoding="utf-8") as stream:
    json.dump({"meshes": meshes}, stream)
```

Record actual Blender/source units and axis meanings explicitly. No Blender MCP or origin-based object guess is required by the JSON importer.
