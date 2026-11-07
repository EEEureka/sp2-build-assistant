# Scoped collaboration and responsive editing

Use this when independent agents share one craft or an in-place sequence should yield ordinary editor frames between mutations. Discover `scope.capture`, `scope.get`, `scope.release` and `scoped.batch.apply` in the installed CLI and loaded bridge before relying on them. Keep the instance PID on every call when several games run.

## Capture ownership and dependencies

Read a fresh snapshot. Capture writable `partIds` and explicitly protected `boundaryPartIds` with that `craftSessionId` and `expectedRevision`; add `ownerId` for attribution. For example:

```json
{
  "craftSessionId": "CURRENT_SESSION",
  "expectedRevision": 12,
  "partIds": [293, 299],
  "boundaryPartIds": [254, 262],
  "ownerId": "hangar-agent",
  "spatialMarginMetres": 0.02
}
```

```powershell
sp2model scope capture --input scope.json --request-id capture-hangar-1 --json
sp2model scope get --scope-id RETURNED_SCOPE_ID --json
```

The lease records native object/content fingerprints, shared craft state and guarded attachment, symmetry, cutting, derived-transform and conservative spatial dependencies. It is a content guard, not an exclusive lock or a geometric-contact proof. Declare expected shared boundaries even when separated by a current gap; spatial bounds cannot infer the design intent. `MultipleParts` targeting follows current native volume intersections and handler state; `Custom` targeting uses its explicit custom IDs. Neither is inferred from the cutter's visible mesh.

An unrelated revision advance can be accepted only while the captured scoped content, native object continuity, dependencies and shared state remain valid. A changed shared boundary, mirror/cutter dependency, global variable/theme/symmetry state or reused object ID stops dependent work. `scope get` explains validity; recapture only after reviewing the changed state and updating the plan. Do not refresh the baseline merely to make a conflict disappear.

## Commit small chunks

```json
{
  "craftSessionId": "CURRENT_SESSION",
  "scopeId": "RETURNED_SCOPE_ID",
  "chunkSize": 1,
  "operations": [
    {"kind": "shape.update", "partId": 293, "symmetric": false, "patch": {"autoResize": false}}
  ]
}
```

```powershell
sp2model scoped batch apply --input edits.json --request-id reshape-hangar-1 --json
```

`chunkSize` defaults to **1**, permits **1..4**, and the request permits **1..100 operations**. Supported families are in-place `part.update`, `shape.update`, `properties.set`, `transform.apply`, `transform.align`, `decal.pose.set` and assigning an existing material through `appearance.set`. Targets must be writable; alignment/anchor sources must be guarded. Include native symmetric peers or explicitly use `symmetric:false` where supported. Adds, deletes, topology edits, palette cloning/shared changes and unknown group expansion need a separate reviewed strict batch.

Each chunk performs guarded native setters, rebuild/settlement, cache refresh, readback and history commit atomically. Between chunks, the scheduler leaves at least one complete ordinary editor input frame and 100 ms. It passively detects pointer/scroll/key activity and waits for at least 150 ms of quiet before scoped writing. Dragging, native text focus, dialogs, external transform targets and unadapted stateful tools keep it paused. Reads and cancellation remain dispatchable while paused. The same activity and cancellation checks run again after native history awaits, immediately before atomic entry.

Read `designer status` fields `interactiveScheduling` and `nativeInputSafety` to distinguish waiting for the user from a failed or stuck task. A long pause while the user edits is intentional; do not replace it with a strict batch to force progress. Supported ordinary move/view/color/rotate/translate tools retain their native tool and rebound selection across verified rebuilds. Finish a shape tool interaction and return to an ordinary tool before expecting scoped mutations to resume; do not silently close the user's active editor.

Native pointer, keyboard shortcut and transform-panel mutation entry points are gated only during an atomic chunk. Focus/pause-triggered native saves arriving inside that boundary are merged for their captured session/script and consumed once when idle and safe; they are discarded when that identity changes. A returned automatic-save call is not disk-persistence proof. Explicit native CLI saving can recenter the craft: read its returned identity and reconcile stale scopes rather than refreshing guards automatically.

A synchronous native setter/rebuild cannot be preempted. Discrete input landing inside the necessary atomic boundary may still be ignored; input replay and universally zero lost events are not promised. Ordinary `batch.apply` remains a strict whole-batch atomic operation. Chunk wall time includes awaited settlement; frame intervals include rendering and OS work. Neither measures continuous CPU occupation or human input latency.

For acceptance, bind the loaded DLL/build ID, game version, named fixture, real agent callers and input window. Record actual original-method execution, camera/tool/pose changes, task overlap, frames and user feedback separately. Message-to-callback estimates need gesture/button/position-compatible single-use pairs; unmatched events remain unknown. An idle window without input cannot pass human acceptance. Keep failed historical measurements, use fixed budgets per trial, and compare throughput only with matched operations/CLI calls and comparable user activity. A large fuselage fixture does not establish performance on every ship topology or GPU.

On conflict, failure or cancellation, **successful earlier chunks remain committed**. Only the currently executing atomic chunk can recover its own before-state. Query the original operation after timeout, inspect `completedOperationCount`, `chunks`, `scopedProgress` and fresh readback, then plan remaining work. Reusing the same request ID retrieves the original task; a new ID can duplicate an unknown edit. Cancel and wait for an active operation before releasing its scope:

```powershell
sp2model scope release --scope-id RETURNED_SCOPE_ID --request-id release-hangar-1 --json
```

Do not use whole-craft rollback to undo one agent's completed chunks: it can erase another agent's or player's intervening changes. Create a reviewed compensating edit from current state when needed. Structure plans now default to `batchSize:4`; this is a strict-batch size, not an automatic scoped lease or the scoped maximum. A single strict native batch remains atomic even with a small size.

After all chunks, run the [subject and related-impact loop](build-loop.md); execution isolation does not establish geometry, material, visual or aesthetic acceptance. Scopes expire with the designer session. After restart, reconcile saved current content and semantic ownership before creating new scopes; old operation lookup failure does not prove the edit never ran.
