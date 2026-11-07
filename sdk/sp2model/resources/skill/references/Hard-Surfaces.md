# Hard planes and native shading (0.7.6)

Use this workflow for flat facets, chamfers and unexplained shading gradients.
An expectation is a complete convex boundary in a declared frame, its outward
normal, geometric/shading tolerances, allowed shape tradeoffs and a verification
method. Freeze it before writing. A triangle is always planar; one triangle or
an AABB does not certify the complete expected face.

## Read and inspect

```python
scene = session.inspect()
part = scene.part(id=part_id)
mesh = session.mesh([part], vertex_attributes=['normals', 'tangents'])
result = mesh.planar_face_region(
    0, boundary=expected_boundary, normal=expected_outward_normal,
    tolerance_m=.001, normal_tolerance_deg=.5,
    selection_angle_deg=25, selection_distance_m=.05)
```

The search corridor selects all projected-overlapping candidate triangles;
it does not relax acceptance. Full footprint area, overlap, geometry and actual
normals are checked separately. Freeze a corridor appropriate to the face and
neighbouring crease angles. Missing coverage or actual attributes never passes.
`planar_face(mesh_index, triangle_indices, boundary=..., normal=...)` accepts
explicit indices in that immutable capture when precise selection is needed.
Neither API certifies unselected or invisible surfaces outside the boundary.

`sp2model model surface.inspect --workspace PATH --instance ID --craft NAME
--input-file request.json --full` accepts `part_ids` and optional
`vertex_attributes`. `surface.check` accepts `part_id`, optional `mesh_index`
(default 0), `boundary`, `normal` and the four tolerance/search options above;
it captures fresh render normals and evaluates world-metre targets. Inspect the
saved `resultFile` when the console response is compacted. These operations do
not need a modeling task to exist and never write native geometry.

At native query level, `geometry.section/measure/seam/symmetry` supports
`vertexAttributes:["normals","tangents"]` with `export:true,exportMeshes:true`.
Only final owned render surfaces provide shader attributes; colliders reject
this option. Normals are inverse-transpose transformed and normalized. Native
triangle winding is preserved with `windingParity`; tangents are transformed,
orthogonalized and have handedness adjusted for reflection. Custom SDK frames
rotate vectors with the positions. No normal recalculation or mesh mutation is
performed. Missing/invalid arrays or singular transforms return unavailable.
Shader displacement is outside this snapshot.

Attributes include renderer/source identity, effective transform, submesh
indices and material-slot mapping. Position-only artifacts retain their shape.
Attribute captures permit 250,000 vertices; all exports retain the 80 MiB
artifact limit. Reduce the selected scope on budget failure. Artifact SHA256,
identity, geometry/attribute stamps and capture ID bind evidence. Fresh captures
are required after native rebuilding, editing or reopening.

## Construct a true hard face

Semantic `model.loft/prism` with `corner.kind="chamfer"` now compiles rectangular
parallel sections to sharp Bodies plus native plane cutters. The plan reports
`nativePartCount`, including cutters; budget accordingly (a simple chamfered
prism usually needs 5 native parts). Curved/advanced profiles are rejected when
the hard-plane guarantee is not supported. `round` retains sampled smooth
corners; explicit native corner parameters remain available but provide no
hard-shading guarantee. Existing native saves are never automatically migrated.
Hard-cut semantic loft refinement currently needs an explicit reviewed complete
component replacement; it cannot silently update only the body and leave stale
cutters.

For an existing reviewed body:

```python
plan = session.plan(writable=[part])
# Set any required body shape parameters explicitly first.
cut = plan.clip_plane('facet', [part], origin, outward_normal,
                      bounds_min, bounds_max, max_cutters=8)
preview = plan.preview()
# Inspect cut['preview'] and preview before session.apply.
receipt = session.apply(plan, preview.token)
```

Lengths use plan units; preview values are metres. The cut removes the positive
half-space `dot(point-origin,normal)>0` inside explicit finite target bounds.
Each native Hole axis is limited to 10m; tangential tiling is planned with small
overlap, while unsupported cut depth is rejected. Review target IDs, cutter
count and the exposed face. Existing holes/materials/connections are not reset.
The caller must provide complete target bounds; intersecting a cutter with the
wrong bounds is not repaired by the tool. All normal scope/revision guards apply.

Never use more corner samples, paint changes, overlays or global normal
recalculation to hide a failed hard face. Preserve smooth cylinders and rounds.
Verify the actual resulting mesh and native fixed views, then save/reopen and
repeat using current identities. Geometry and shading are separate from source
fidelity and functional acceptance.

## Persist the completion gate

`task.metric(..., kind='hard_face', expected={'boundary': [...], 'normal': [...],
'normal_tolerance_deg': .5, 'selection_angle_deg': 25,
'selection_distance_m': .05}, tolerance_m=.001, reference_id=...)` freezes the
expected face. Bind its single rendered owner and call `task.measure` with a
current SHA256-verified `session.mesh(..., vertex_attributes=['normals'])`.
The existing task gate retains failed/incomplete/unavailable results and cannot
complete without required passing evidence. Multi-renderer owners need a more
specific explicit check; this metric does not guess which surface to certify.

Keep fixed-view visual inspection as a separate required visual gate. Normal
lighting, reflections and contact shadows may still vary over a genuine plane;
uniform pixel brightness is not a valid universal goal.

Creating native Hole parts enables cutting-volume editor outlines. For a clean
fixed-view review, clear selection with native `designer.control select`, then
use `session.capture(..., cutting_outlines_visible=False)`. This temporarily
changes only the native editor outline switch and restores it even on capture
failure. `helperDisplay` records before/during/after; other helpers may remain.
Omitting this option preserves existing capture behavior. Use the same recorded
`repeatableViews` for comparisons, not independently auto-framed views.

An exact zero-width bevel tip can produce tiny CSG slivers whose geometric
normals are numerically unstable. Measure them rather than discarding them.
An explicitly reviewed cutter inset within the frozen geometric tolerance can
stabilize the tip; preserve the original target, record the offset and remeasure.
The compiler never silently applies this approximation or relaxes tolerances.
