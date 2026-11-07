# Route A public modeling API

This reference retains the route1 modeling API in the 0.7.8a1 development SDK. See the [README](../SKILL.md) for installation/evidence, [Updates](Updates.md) for `Runtime.updates.check/status/guide`, and [Knowledge](Knowledge.md) for the retained read-only `Runtime.knowledge` services. Update notifications preserve operation results and do not authorize installing or restarting. Accepting an input does not certify its geometry. Freeze targets and measure native results.

For new/complex models, read [modeling workflow and public task state](Modeling-Workflow.md). For wings, controls, shafts, sphere/dome, native attributes, output/Setter/FT and checkpoints, read the relevant section of [advanced native interfaces](Advanced-Native.md). Basic constructors below remain compatible.

Multi-stage modeling uses `session.task(path, name=..., intent=...)`: register/freeze references, components and required metrics, create a candidate, `task.apply(candidate, plan)`, `task.bind(candidate, component, parts)` and `task.check(candidate, metric_ids=None)`. `task.parts` returns current bound members. Persist the same task/project/journal paths between scripts. See [modeling_task.py](../examples/modeling_task.py) for a complete runnable lifecycle.

`task.seam(id, component="front", other_component="rear", reference_id=..., origin=..., normal=...)` freezes two distinct semantic interface sides; `task.check` measures them using shared component/frame captures and a batch identity fence. Without `other_component`, one bound component must represent the full pair. Frozen denominator and standalone measurement guards remain strict. `task.report` exposes frozen `budget` and usage; pass explicit user limits rather than accepting defaults. Host envelopes expose per-invocation `transport.commandPostAttempts`; aggregate across scripts for the independent POST budget.

`task.save(name, overwrite=False)` returns the native `persistedCraft.craftId`; `task.reopen(craft_id, discard_current=True)` returns a **new task/session**, followed by explicit `task.rebind(candidate)` and current `task.check`. `task.resume()` only queries linked original requests. `task.keep_best(candidate)` retains a current-epoch checkpoint and its project proof; `task.restore_preview()` persists a current whole-craft review; `task.restore(token, accept_whole_craft=True)` requires that review and deduplicates across script restarts. After an exact restore use explicit `task.rebind(candidate, from_best=True)` and remeasure. This option requires this candidate/project/checkpoint and an exact restore at unchanged current identity; it does not relax content, pose or lifetime matching. Unsupported visual/function or implicit multi-part surface/section-union evaluations remain incomplete.

`PartRef.to_dict()` and `Scene.to_dict()` export detached captured data. For nested SDK handles, native state and rebind maps, use `from sp2model import to_jsonable`, then `json.dumps(to_jsonable(value), ensure_ascii=False)` when writing UTF-8 files. Assigning supported handles directly to the host's `result` already converts them. Avoid `vars()`, `__dict__`, or raw `json.dumps(handle)`; a serialization error after native save/apply is a local reporting error, so inspect its original journal instead of rerunning the write. Export never refreshes a stale reference or grants write permission; reload the project and explicitly rebind current native objects.

`session.rebind()` returns a dictionary keyed by logical IDs whose values are current `PartRef` handles. Use `part.logical_id` or its exported `logicalId`; don't guess a different binding-map shape. Native bridge reads such as `shape.schema` differ from tool-local discovery commands: `sp2model commands schema` / `Runtime.call("commands.schema",...)` is not a native bridge command. For Runtime administration, reference services and native operation migration, read [Services](Services.md).

## Task host, session and identity

```powershell
python -m sp2model run task.py --instance <pid-or-instance-id> --craft "<loaded-name-or-session-id>" --project model-project.json --journal-dir task-journals --params-file task.json
python -m sp2model inspect --instance <pid-or-instance-id> --craft "<loaded-name-or-session-id>" --project model-project.json
python -m sp2model resume execution.json --instance <pid-or-instance-id> --craft "<loaded-name-or-session-id>" --project model-project.json
```

The host injects `session` and JSON `task_parameters`; assign useful output to `result`. It accepts JSON, Scene, PartRef, MaterialRef, Preview and Receipt results. Script prints go to stderr; stdout is one JSON envelope. The host is trusted local Python execution, not a sandbox. It never calls apply or retries implicitly. `--params` accepts a JSON object instead of `--params-file`; all commands also accept `--discovery-dir` and finite positive `--timeout` seconds. Host `ok` means code completion, not model acceptance.

Standalone entry: `Session.attach(instance, craft, discovery_dir=None, journal_dir=None, timeout=30, project_path=None, summary_only=False)`; options after craft are keyword-only. Host inspect defaults to --detail summary (one native read); --detail full explicitly loads every part. Programmatic inspect remains full. The SDK exports Session, Section, Frame, WingSection, MeshEvidence, compare_contours, ModelingTask and ModelingError.

For an explicitly authorized disposable fixture, native new/save control can establish the craft before attaching a Session. `BridgeClient` is imported from `sp2model.transport`; its `instance` property is a sanitized descriptor. This changes the selected designer's current craft, so use only a reviewed isolated instance and explicitly confirm discard:

```python
import uuid
from sp2model.transport import BridgeClient
client = BridgeClient.discover(instance=reviewed_isolated_pid, timeout=120)
def control(action, **options):
    status = client.call("designer.status")
    snapshot = client.call("craft.snapshot")
    return client.call("designer.control", {
        "action": action, "expectedScene": status["scene"],
        "expectedCraftName": snapshot["name"],
        "craftSessionId": snapshot["identity"]["craftSessionId"],
        "expectedRevision": snapshot["identity"]["revision"], **options,
    }, request_id=uuid.uuid4().hex)
control("new", discardCurrent=True)
control("save", name="Explicit isolated test craft", overwrite=False)
```

Every control reads a fresh baseline. A control result is not a modeling acceptance result. Normal modeling should use the attached Session's durable `save()`/`reopen()` methods below. No operation chooses a player craft by guessing its name or numeric ID.

`scene = session.inspect()` exposes `name`, `identity`, `parts`, `connections`, `craft_frame`. Use `scene.part(id=reviewed_id)`, `scene.part(name=unique_name)` or `scene.select(name=..., type=..., tags=[...])`. PartRef exposes `id`, `name`, `type`, `logical_id`, `tags`, `project_id`, `frame`. It is an instance/session/revision-bound object, not a reusable numeric handle. `session.expand(part)` reads native detail; `shape(part)` reads typed shape; `schema(part)` discovers property fields; `schema(style="Body")` discovers a constructor template; `properties(part, fields=[...])` reads discovered fields.

Create `plan = session.plan(frame=None, length_unit="m", writable=None)`. `writable=[]` protects all existing objects while allowing new ones. Explicit lists must include every reviewed existing target/dependency: both connection/alignment endpoints, Wing and controls, Hole and affected targets. Omission derives IDs from explicit plan references, never the whole craft. Scope and implicit callback guards remain active.

`preview = plan.preview()` returns `token`, `plan_hash`, `writable_part_ids`, `report`; it validates but does not write or simulate geometry. `receipt = plan.apply(preview.token)` is explicit write intent. Changed plans invalidate previews; repeated use of the same accepted preview resolves its original execution. Receipt exposes `objects` (new logical name → PartRef), `identity`, `request_id`, `operation_id`, `journal_path`, `to_dict()`. Use returned objects or fresh inspection after a native revision. Planned objects cannot cross to another plan before apply. When stale, inspect and replan rather than refreshing a frozen baseline.

## Frames, sections and constructors

Constructor points, offsets and dimensions use the plan's m/cm/mm units. Rotations are `(x,y,z,w)` quaternions or explicit degree/radian arguments. Default frame is world. `Frame.custom(position=(0,0,0), rotation_quaternion=(0,0,0,1))` takes its **world origin in metres**, independent of plan units. `scene.craft_frame` and `part.frame` are captured rigid poses, exclude object scale and expire with native state.

`frame.child(position=(0,0,0), rotation_quaternion=(0,0,0,1))` composes a local rigid child pose. `frame.translated(local_metres)` shifts along local axes; `frame.rotated(axis, angle_deg=... or angle_rad=...)` rotates local axes about the same origin. Child distances are always metres and captured identity is inherited, so deriving a child cannot revive a stale frame.

```text
Section(width, height, corner_radius=0, corner_stretch=False, trapezium=0,
        edge_curvature=0, cutting=None, smoothing=None, sync_adjacent=None, thickness_fraction=.1)
plan.body(name, start, end, sections, style="Body", up=(0,1,0))
plan.cone(name, start, end, sections, up=(0,1,0))
plan.curved(name, start, end, sections, up=(0,1,0))
plan.wing(name, span, root_chord, tip_chord, position=(0,0,0), rotation_quaternion=(0,0,0,1),
          *, root_offset=0, tip_offset=0, airfoil=None)
plan.wing_control(name, wing, span_range, chord_fraction=(.25,.25), *, style="StandardFlap",
                  max_deflection_deg=None, flap_deflection_deg=None, brake_top_deg=None, brake_bottom_deg=None)
plan.hole(name, targets, width, height, depth, position=(0,0,0), rotation_quaternion=(0,0,0,1))
```

Body/Cone require two Sections; Curved requires three. Start/end define native center, length and local +Z direction; `up` fixes roll. Length is .001–1000m. Width/height and ordinary corner radii use plan units; stretched radii, cuts and edge curvature are fractions. Radius/stretch accepts a scalar or a complete dict of `topLeft`, `topRight`, `bottomRight`, `bottomLeft`; curvature/cutting uses `top`, `right`, `bottom`, `left`. Default ends are sharp and unsmoothed. Curved's middle Section is a control: widths 1,2,1 imply analytic center width 1.5, not 2. It has no cutting/smoothing/sync capability. `cone` interprets its Sections as actual requested ends: a zero terminal Section uses native Cone with explicit zero nose roundness; a nonzero terminal Section uses one native Body to represent a truncated cone. `PlannedPart.expected` and the plan report `nativeStyle` and `implementationStrategy`; native Cone itself does not support a nonzero actual end cap. The native sharp tip has no smoothing/sync capability. Advanced native rounded-nose control semantics need separate shape discovery and validation. Actual mesh still needs verification.

Wing is unbent, two-section, from its native root along local +X; chord lies along local ±Z. `position` is the root origin, not wing center. Root/tip offsets shift section centers along +Z in distance units. The constructor uses a discovered airfoil and clears rounded wingtips. Control span is increasing root-to-tip distance in plan units; chord fractions are dimensionless. Styles are StandardFlap/FowlerFlap/Slat/BrakeFlap, subject to native field/overlap constraints. BrakeFlap uses its three brake/flap arguments; other styles use `max_deflection_deg`. Certification is limited to separately tested styles/values.

Hole is a rectangular cutter over explicit fuselage targets. Local XYZ width/height/depth are .01–10m; these describe the envelope, not the final aperture on a curved body. Example task code:

```python
from sp2model import Section
plan = session.plan(writable=[])
body = plan.body("shell", (0,0,-1), (0,0,1), [Section(4,4), Section(4,4)])
hole = plan.hole("opening", [body], 1, 1, 4)
plan.expect_probe(body, (0,0,0), inside=False)
plan.expect_probe(body, (1.5,0,0), inside=True)
receipt = plan.apply(plan.preview().token)
result = {"receipt": receipt, "verification": session.verify(receipt)}
```

## Transforms, groups, connections and repetition

```text
plan.group(name, parts) -> ordered PlannedGroup
plan.move(parts, translation, *, symmetric=False)
plan.rotate(parts, axis, *, angle_deg=None, angle_rad=None, pivot=None, symmetric=False)
plan.pose(parts, position, rotation_quaternion, *, symmetric=False)
plan.scale(parts, factors)
plan.dimensions(part, *, width=None, height=None, length=None, span=None, root_chord=None, tip_chord=None)
plan.shape(part, patch, *, symmetric=False)
plan.properties(part, patch, *, symmetric=False)
plan.delete(part, *, assembly=False, symmetric=False)
plan.align_to(parts, source, target, *, source_point=None, target_point=None,
              offset=(0,0,0), axis="opposedNormals", symmetric=False)
plan.align(parts, source, source_point, target, target_point,
           *, offset=(0,0,0), axis="opposedNormals", symmetric=False)
plan.connect(source, target, source_point=None, target_point=None, *, shape_policy="preserve", symmetric=False)
```

Use ordered lists/tuples or PlannedGroup, not sets. Groups create membership, not topology. `pose` places the first member and moves others rigidly; `rotate` defaults its pivot to the first member. Explicit pivots/translation use the plan frame. `scale` sets absolute local XYZ object scale without moving positions. `dimensions` edits native parameters; fuselage width/height preserve proportional taper, Wing uses span/root/tip chord. Shape dimensions differ from scaled mesh extents. Advanced shape/property patches use discovered native fields in native metres/degrees/fractions, without automatic plan-unit conversion.

Alignment moves `parts`; source must be a member and target outside them. It imposes the selected attach-point axes, not an additional roll, and creates no connection. Give both discovered point IDs or omit both for native unique-compatible-pair selection; ambiguity rejects. `connect` changes topology without replacing alignment. `preserve` disables fuselage auto-resize; `native_resize` permits native resizing and needs fresh measured readback. Alignment/native resizing can invalidate planned poses.

```python
plan = session.plan(writable=[])
a = plan.body("rear", (0,3,-2), (0,3,0), [Section(1,1), Section(1,1)])
b = plan.body("front", (0,3,.4), (0,3,2.4), [Section(1,1), Section(1,1)])
plan.align_to([b], b, a)
plan.connect(b, a, shape_policy="preserve")
plan.expect_connected(a, b)
receipt = plan.apply(plan.preview().token)
```

```text
plan.copy(source, name, *, translation=(0,0,0), rotation_quaternion=None, pivot=None)
plan.linear_array(source, name, count, step)
plan.radial_array(source, name, count, axis, *, angle_deg=None, angle_rad=None, pivot=(0,0,0))
plan.mirror_group(source, name, linked=True) -> new PlannedGroup
plan.mirror(part, *, linked=True, plane="native") -> Plan
```

Copy preserves internal connections, detaches external edges and unlinks copied native symmetry. Include hosts/dependents/targets explicitly. Arrays return new members only: count=3 means three copies plus source. Linear positions use step, 2×step, 3×step; radial angle is the step, not total sweep. A source on the axis changes orientation without orbital spacing. Copies have unique logical identities.

Mirror requires native designer Mirrored mode and its reviewed plane; arbitrary planes/radial/disabled modes are unsupported. Prefer `mirror_group` for named peer references and Wing/control assemblies. Already symmetric sources reject. Native callbacks determine new poses/shapes: apply and read back before subsequent relative editing. `linked=False` requests independent peers. `mirror` returns the Plan, not a new peer reference.

```python
plan = session.plan(writable=[])
wing = plan.wing("right_wing", 3, 1.5, .7, position=(2,3,0))
control = plan.wing_control("right_control", wing, (.2,2.5), max_deflection_deg=20)
receipt = plan.apply(plan.preview().token)
members = [receipt.objects["right_wing"], receipt.objects["right_control"]]
mirror_plan = session.plan(writable=members)
mirrored = mirror_plan.mirror_group(mirror_plan.group("right", members), "left", linked=True)
mirror_plan.expect_connected(mirrored[1], mirrored[0])
mirror_receipt = mirror_plan.apply(mirror_plan.preview().token)
result = {"receipt": mirror_receipt, "verification": session.verify(mirror_receipt)}
```

`plan.update_hole(part, *, size=None, targets=None, position=None, rotation_quaternion=None)` updates a bounded cutter. Include both cutter and affected targets when moving them together, and remeasure the cut afterward.

For current existing objects, including after native reopen and explicit rebind, declare an expectation-only plan and call `session.check(plan)`. This is read-only and needs no preview/apply or synthetic Receipt. It refuses plans with any pending mutations; empty checks are `not_assessed`.

```python
body = session.select(name="shell")[0]
checks = session.plan(writable=[])
checks.expect(body, length_m=2, tolerance_m=.002)
checks.expect_probe(body, (0,0,0), inside=False)
result = session.check(checks)
```

## Material and project persistence

`session.materials(name=None)` returns palette dictionaries; `appearance(parts=None)` reads assignments and palette. `track_material(material_id, name=...)` returns MaterialRef; `material(name, rebind=True)` refreshes matching tracked palette evidence explicitly. Reserved/absent materials reject. `plan.material(parts, material_id, slots=(0,), patch=None)` assigns a discovered ID/fresh MaterialRef; a patch appends a clone without editing the shared source. Example within a current plan:

```python
paint = next(m for m in session.materials() if not m.get("reserved"))
plan.material(body, paint["id"], slots=(0,), patch={
    "name": "task red", "style": "SolidColor",
    "colors": [{"index": 0, "rgba": [.8, .1, .2, 1]}],
})
```

Reuse an explicit project path across scripts. `session.track(part, name=..., tags=[...])` stores an alias/evidence and returns tracked PartRef. `session.group(name, parts)` stores membership; `session.select(name=..., type=..., tags=[...], group=...)` and `group_parts(name)` return fresh objects. Aliases do not rename native parts. Successful plan readback records its logical names/groups in the project.

```python
# receipt comes from a successful plan creating "main_body".
tracked = session.track(receipt.objects["main_body"], name="main_body", tags=["hull"])
session.group("hull", [tracked])
saved = session.save("Named isolated test craft", overwrite=True)
session = session.reopen(saved["persistedCraft"]["craftId"], discard_current=True)
bindings = session.rebind()
hull = session.group_parts("hull")
plan = session.plan(writable=hull)
plan.move(hull, (0, 1, 0))
```

`save(name, overwrite=False)` has a durable native operation record. `saved_crafts(query=None, offset=0, limit=100)` discovers saved IDs. `reopen(craft_id, discard_current=True)` uses the exact ID and returns a new Session; save wanted work before discarding current designer state. `rebind(logical_ids=None, mapping=None)` checks content, relative pose and lifetime, not name/ID alone. Mapping values must be fresh PartRefs keyed by known logical IDs. Missing/recycled/ambiguous identities reject. Binding content tolerates native omission of unit scale; full revision and scope fingerprints stay strict.

## Native checks and views

```text
plan.expect(part, *, length_m=None, span_m=None, position_m=None, dimensions_m=None,
             rotation_quaternion=None, tolerance_m=.01, tolerance_deg=.01, sections=None, connected_to=None, endpoints_m=None)
plan.expect_section(part, axis, offset_m, width_m, height_m, *, tolerance_m=.002)
plan.expect_connected(source, target)
plan.expect_probe(part, point_world_m, *, inside)
session.verify(receipt)
session.check(expectation_only_plan)
session.capture(*, views, parts=None, width=1024, height=768)
```

Expectations use metres. Position/probe points are world-space; dimensions measure actual mesh extents in rigid part axes including object scale. Length is local Z, Wing span X. `endpoints_m=(start,end)` uses actual local -Z/+Z end-cap bounds centers transformed to world metres for certified straight Body/Cone/Curved; arbitrary oblique/skewed/trimmed shapes need their own endpoint definition and are not certified by this check. Sections intersect native mesh at a local-axis offset; width/height use `z`→x/y, `x`→z/y, `y`→x/z. They do not certify unsampled surface. Use frozen task tolerances rather than the general defaults. Solid probes require complete closed mesh; `solidMeshEvidence` reports welding tolerance, triangle/degenerate/edge counts. Boundary/mesh ambiguity is incomplete evidence. Verify before later edits make the receipt stale, or use a fresh expectation-only plan and `check()` after inspect/rebind. No targets gives not_assessed; passed covers only listed checks. Topology, appearance, functionality and aesthetics are separate.

```python
from pathlib import Path
import hashlib
capture = session.capture(views=[
    {"view": "isometric", "projection": "orthographic"},
    {"view": "right", "projection": "orthographic"},
])
for view in capture["views"]:
    file = next(f for f in capture["files"] if f["name"] == view["file"])
    image = session.client.artifact(capture["captureId"], file["name"])
    assert hashlib.sha256(image).hexdigest().lower() == file["sha256"].lower()
    Path(capture["captureId"] + "-" + file["name"]).write_bytes(image)
```

Use returned view filenames: overview.png may be an alias, not an extra requested view. Downloaded files still need actual image inspection. Artifacts have limited retention, so retain task evidence promptly.

## Sequences and recovery

Plans are limited to 100 native operations; one constructor can produce several. `session.execute_sequence(builders, name="...")` accepts 1–64 fresh-plan functions `(session, prior_receipts) -> Plan`. This call explicitly authorizes writes; it previews/applies each plan, stops at failure, and records completed receipt dictionaries plus a sequence journal. It neither verifies geometry automatically nor rolls back earlier successful batches.

```python
def add_section(current, completed):
    plan = current.plan(writable=[])
    body = plan.body("section", (0,3,-1), (0,3,1), [Section(1,1), Section(1,1)])
    plan.expect(body, length_m=2, tolerance_m=.002)
    return plan
result = session.execute_sequence([add_section], name="explicit section stage")
```

For inspection between batches, apply/verify individual plans before proceeding. Prior receipts are serialized data, not fresh PartRefs; select current project objects in each builder. Preserve `ModelingError.code`, `.details`, journalPath/sequenceJournalPath, request/operation IDs and completed boundaries.

`session.resume(execution_path)` queries the original request without resubmitting. If operationId was lost, it looks up the existing requestId; a missing/unavailable mapping leaves outcome_unknown, never authorizes replay. `resume_sequence(sequence_path)` only resolves an already submitted boundary and never invokes builders. `continue_sequence(sequence_path, remaining_builders)` is a separate explicit write after a known boundary; unresolved outcomes or external edits reject it. Supply exactly remaining builders, never completed ones. A failed atomic batch and a sequence with completed earlier batches are distinct outcomes.

Timeout does not imply failure; rerunning a script creates fresh IDs and may duplicate work. Process/session replacement needs current native reconciliation and explicit binding. External journals reduce context dependence but cannot guarantee permanent DSH instruction retention.
