# Edit and recovery payloads

Read schemas from the installed CLI. These examples use placeholders; replace the session, revision, part IDs and template IDs with current returned values.

```json
{
  "requestId": "a-new-unique-id-for-this-batch",
  "craftSessionId": "SESSION_FROM_SNAPSHOT",
  "expectedRevision": 1,
  "operations": [
    {"kind": "part.update", "partId": 123, "changes": [{"path": "", "attribute": "name", "value": "Agent named part"}]},
    {"kind": "part.add", "templateId": "TEMPLATE_ID", "temporaryId": "newPart", "position": [0, 1, 0], "rotation": [0, 0, 0]},
    {"kind": "variable.add", "variable": "BuildTest", "function": "clamp(Throttle,0,1)", "priority": 0},
    {"kind": "output.bind", "partId": 123, "modifier": "JointRotator.State", "outputId": "BodyAngle", "variable": "BayAngle", "priority": 0}
  ]
}
```

Use `part.delete` with `partId` and optional `symmetric` and `assembly` (both false by default; assembly requires DLL 0.2.2+); `connection.connect` with `partA`, `partB`, `attachPointA`, `attachPointB` and optional `symmetric`; `connection.disconnect` with the two part IDs. Query available connection points first. A temporaryId refers to the first part produced by the template; the result lists all produced IDs. Templates may be assemblies with more than one part.

`part.add.position` targets the template's first part in world metres. `rotation` is a Unity Euler **offset** applied around that part and composed with each template part's existing rotation; omit it or use `[0,0,0]` to retain template orientation. A Vertical Stabilizer already rotated `[0,0,90]` remains vertical with zero offset; adding another 90 degrees does not set its final rotation to 90. Inspect `catalog schema` defaultState and read back `rotationEulerDegrees`. Existing-part `part.update` writes to the Part rotation attribute are absolute world Euler values.

`connection.connect` establishes the native connection without a general pose-alignment step. Wing-mounted stores can have attach points separated in space; preserve intended geometry and edit position/rotation separately. It does not promise every connection becomes a Fixed joint: articulation and specialized modifier callbacks retain native behavior.

Fuselage/cone exception: `autoResize:true` lets the native connection callback copy neighbouring sections/length and align the part, then disables the flag. Explicitly patch `autoResize:false` before connecting manually dimensioned parts. Completion identity and validation are a point-in-time readback; later save/AutoRecenter can move the whole craft and advance revision. Inspect `craft history` → `data.nativeSteps` for `Craft Repositioned`, with `data.operations` for bridge writes. This cannot distinguish an automatic from a manual save. Re-read after conflict and verify geometry against the same revision.

## Input controllers (DLL 0.4.8+)

`sp2model catalog schema --id TEMPLATE_ID` returns `data.templates[].parts[].toolEditableExtensions` for templates with input controllers, including ones absent from the current craft. `sp2model designer status` returns `data.inputControllerEditing` with the same plugin-validated fields; the native `metadata` list alone can omit them. Older DLLs may reject `input` even when it is visible in saved state.

DLL 0.4.9 adds effective native configuration at `parts get` → `data.part.inputControllers`, `shape get` → `data.shape.inputControllers`, and `catalog schema` → `data.templates[].parts[].inputControllers`. Each row contains `index`, an editable `path`, native `name`/`description`, `input`, `activationGroup`, `invert`, `invertType`, `min`, `max`, `zeroOnDeactivate`, and contextual `invertOnMirror`. These are typed values read from native data, including defaults that the raw XML omits. `serializedAttributes` lists which attributes the native serializer emits; absence there does not override the effective value. `valueSource` distinguishes a live part from an isolated template. No controller expression is evaluated. Empty arrays mean no input controller; an absent field on an older DLL means this readout is unavailable.

Use the returned `path` and native controller name to choose among repeated controllers. Native BrakeFlap has separate flap/brake controllers, and a wheel has steering/braking controllers. Do not flatten repeated nodes into a dictionary keyed only by `InputController.State`. `name`, `description`, and `invertOnMirror` explain native behavior; they are not additional writable fields.

Use a guarded `part.update` operation, for example `{"kind":"part.update","partId":123,"changes":[{"path":"InputController.State","attribute":"input","value":"Aileron"}]}`. Repeated controllers use `InputController.State[0]`, `[1]`, etc.; check each node's current state before choosing its index.

Writable fields: `input` (native axis or float expression), `activationGroup` (string `"0"`..`"8"`, or boolean expression), `invert` and `zeroOnDeactivate` (booleans), `min`/`max` (finite output values), `invertType` (`Axis` or `Output`). Null/removal is rejected; use explicit values. `min > max` is a supported reversed mapping. Zero activation group means always active. Changed expressions are compiled in the part context without evaluating flight telemetry; malformed expressions trigger batch recovery. Existing controllers whose input/activator is unchanged are not revalidated by this extension.

For native wing control surfaces, `Aileron` chooses opposite Roll signs according to the connected wing's `flipped` state. Ordinary `Roll` has no such adjustment. Inspect the template's actual input: a Standard Flap may default to `Pitch`; geometry and type do not establish its intended role. Verify input, invert, min/max and activation group after assigning the role. Do not double-invert an Aileron binding merely because its wing is mirrored. This is input configuration, not a flight or control-effectiveness test.

## ID lifetime (DLL 0.3.1+)

The game reuses free numeric IDs. After a delete/add batch, a number may identify a different part, even one of the same type. `reusedPartIds` records each reuse with `previous`/`current` part summaries, zero-based `deletedAtOperationIndex`/`createdAtOperationIndex` and the new `temporaryIds`. It describes each creation event; later operations may rename or delete that replacement. Re-read final state before reusing IDs across batches.

Within a batch, a deleted numeric reference fails with `stale_part_reference`, even when the number has been reassigned. A temporary binding to a deleted part fails with `deleted_temporary_reference`; it never follows a replacement. Use a new, unique temporary name for the new part and use that name in subsequent operations. `temporaryIds` contains only surviving bindings; `invalidatedTemporaryIds` lists dead bindings. Any failure uses the existing whole-batch recovery; inspect its result and fresh identity before continuing.

```json
[
  {"kind":"part.delete","partId":214,"assembly":true},
  {"kind":"part.add","templateId":"CURRENT_TEMPLATE_ID","temporaryId":"newPod"},
  {"kind":"part.update","partId":"newPod","changes":[{"path":"","attribute":"name","value":"New pod"}]}
]
```

Wrap these operations in the usual guarded batch. Never replace `newPod` with the deleted number 214. Native allocation, connection positioning and default deletion scope remain unchanged.

## Bounded assembly deletion (DLL 0.2.2+)

Read `sp2model parts assembly --id ROOT_ID --json` (optional `--symmetric true`) to obtain `memberPartIds`, `childPartIds`, `rootPartIds` and `externalConnections`. The query is a current snapshot, not a reservation; submit the edit with its current session/revision. The root must be a procedural missile body or JWing. A missile includes its directly attached, natively owned components; a wing includes its directly owned control surfaces. An independent pylon, tank, weapon or connected fuselage is outside the scope. Arbitrary user-created subassemblies have no retained ownership identity and must use an explicit list of deletion operations. Selecting a child does not implicitly promote deletion to its owner.

```json
{"kind":"part.delete","partId":229,"assembly":true,"symmetric":false}
```

Use this object in a guarded batch. `symmetric:true` expands the root's native symmetry group and each root's owned components, matching explicit native deletion semantics (the symmetry-disabled edit flag does not protect a member from explicit symmetric deletion). The complete scope is resolved before removing any part. A shared/mismatched owner or child connected outside the scope returns `assembly_ambiguous`; unsupported roots return `assembly_not_supported`. Native deletion must match the plan or the transaction restores its starting snapshot. `actualChanges[].deletedPartIds` lists the removed IDs. Omit assembly to retain existing single-part deletion behavior.

Attribute `path` examples: empty string for Part attributes; `JetEngine.State`; `Fuselage.State/Sections/Section[0]`. The actual names come from `catalog schema` or `parts get`; do not assume examples exist. Updates support metadata-defined values and validate types, ranges, enumerations and read-only flags. Structural ID, type, symmetry and material references have no generic setter in v0.1. Unknown schema attributes remain visible as template state but may not be writable.

Setter updates/deletes identify the zero-based `index`. Reorder supplies ALL old zero-based indices in their desired NEW sequence: for `[A,B,C]`, `order:[2,0,1]` produces `[C,A,B]`. It does not map old indices to destination positions and is not a list of swap pairs. Each current index must appear exactly once; fractional numbers, strings, duplicates, omissions and out-of-range indices are rejected. Query indices again after edits. With DLL 0.3.2+, `variables list --view structured` returns direct indexed setter rows; `outputs list --view structured` and `variables list --view structured` share `sources[].modifiers[].definitions/bindings`. Output updates/unbinds identify partId, modifier and outputId. Removing the final output binding retains an empty Variables element so game defaults do not recreate it.

## Fuselage cross-sections

From 0.2, prefer the structured `shape.get/schema/update` interface in [complex-shapes.md](complex-shapes.md). The raw XML interface below remains for compatibility and has weaker cross-field semantics; it is not the recommended way to author complex shapes.

A fuselage keeps its shape on repeated cross-section children of the state: `JFuselage.State/Slice[i]` in current XML, `SectionA`/`SectionB` in older saves. Native overload metadata omits these elements, so from 0.1.4 they are validated against the documented XML shape instead of the game UI metadata. Writable attributes: `size` (Vector2, metres), `cornerRadii` (Vector4), `cornerStretch` (Bool4), `cornerSamples` (Int4), `edgeCurvature` (Vector4), `edgeSamples` (Int4), `smoothing` (Bool), `trapezium` (Float), `thickness` (Float), `cutting` (up to four empty-or-0..1 entries). Anything else on a cross-section is still rejected; list the shape from `parts get --id` because slice counts and order differ per fuselage.

`cornerRadii` entries are metres while that corner has `cornerStretch` false, and a 0-1 factor where it is true; a 1x1 section becomes a circle at `0.5,0.5,0.5,0.5`. To round every section of a two-slice fuselage:

```json
{"kind":"part.update","partId":1,"changes":[
  {"path":"JFuselage.State/Slice[0]","attribute":"cornerRadii","value":"0.5,0.5,0.5,0.5"},
  {"path":"JFuselage.State/Slice[1]","attribute":"cornerRadii","value":"0.5,0.5,0.5,0.5"}]}
```

Length is the `JFuselage.State` `offset` vector separating the two cross-sections: a 1 m body uses `0,0,1`, and native long bodies use values such as `0,0,10.40004`. Native metadata omits `offset`, but from 0.1.4 it is writable and is the correct way to resize a body: `{"path":"JFuselage.State","attribute":"offset","value":"0,0,5"}` builds a 5 m fuselage and moves the end attach points to +/-2.5. Scaling the part instead (`{"path":"","attribute":"scale","value":"1,1,5"}`) also stretches the mesh, but it distorts the procedural body, so prefer `offset`. Re-read the part after either edit.

`Part.scale` scales geometry about the part origin, which can differ from the visible mesh center. Missile subparts can have their origin on the missile axis, so scaling a fin may move its root away from the missile body. Verify root contact using actual geometry and joint views. Do not silently substitute scaling for an unsupported procedural missile dimension. The complex inventory is source evidence, not a writable allowlist; missile geometry fields without exposed native metadata remain unsupported in 0.3.1.

Checkpoint creation:

```json
{"requestId":"unique-checkpoint-request","craftSessionId":"CURRENT_SESSION","expectedRevision":1,"name":"Before wing redesign"}
```

Undo / rollback:

```json
{"requestId":"unique-undo-request","craftSessionId":"CURRENT_SESSION","expectedRevision":2,"expectedHeadHash":"OPTIONAL_NATIVE_HISTORY_HASH"}
```

```json
{"requestId":"unique-rollback-request","craftSessionId":"CURRENT_SESSION","expectedRevision":3,"checkpointId":"ID_FROM_CHECKPOINT_OR_APPLY_RESULT"}
```

Cancellation is best effort for a task still queued. An edit already running is allowed to finish; use recovery after its outcome is known. Results expire after the documented retention interval; never infer that an unavailable task did not run.

From 0.5.0 dev12, completed task results share a 64 MiB compressed budget and expire after at most 15 minutes from completion or earlier under capacity pressure. `operation status` keeps `completionState` and `resultRetention` even when the payload is `result_expired`; the requestId still prevents execution again. Retain downloaded results, and inspect the live state before any recovery. Do not replace the requestId merely to obtain a missing response. `designer status.runtimeRetention` exposes cache counters for diagnosing a long session; these counters are not the game's total memory usage.

A failed batch may advance revision even when every intended edit is rolled back. Revision is an observed XML content version, not a success counter. Use the failure's top-level `identity` or fresh status before another write; never reuse the cached pre-failure revision. DLL 0.3.2 adds `rollbackResult.beforeRevision`, `currentRevision`, `revisionChanged` and an explanation. Rejections before mutation, or restores with an identical fingerprint, need not advance revision. A changed revision alone does not prove partial edits remain; verify restoration and independently read back affected content.

In v0.1.2, revision fingerprints normalize ordering and duplicate IDs in native generated target sets. Custom targets and setter order stay significant. Native undo/reload can alter Euler angle serialization through Unity float quaternions: recovery allows at most 0.0001 degrees per axis while checking other fields. Check `rollbackResult.restored` or `validation.restorationVerified`; do not demand identical fingerprints after a native reconstruction. This tolerance applies only to recovery verification; even smaller angle edits still change revision fingerprints.
