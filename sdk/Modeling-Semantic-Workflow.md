# Short semantic modeling workflow

This guide accompanies the 0.7.4 route 1 semantic host. Query the installed host's capabilities before using an operation: a document in a source checkout does not prove that an older installation supports it. Blender is optional; mesh, photo and verbal inputs retain different certainty.

## Discover, then keep a task on disk

The public carrier is `sp2model model OP --workspace DIR --input-file JSON`. `DIR` is a persistent task workspace, not a transient Python script. Live actions also receive the intended instance/craft/discovery selectors. Start with `capabilities`, then `help` for the operation you need. Query nested help by the returned JSON pointer; do not read an entire SDK implementation to guess a field.

Use the actual help result for required JSON fields, enums, units, frame and the minimal example. The short reply has a configurable budget below 8192 characters. `detailComplete:false` means more help exists; query the expansion pointer. This controls tool output length, not the host's later summarization or the model's understanding.

## Reference and goals

Use `reference.bind`/`reference.inspect` to identify the intended installed object or input evidence. Resolve duplicated/origin objects before dependent writes. Freeze the source fingerprint, selection, scale, axes, origin and common task frame. All dimensions, independent section centers, outlines and relative placements use that frame.

For photos, record known dimensions, observable directions, intervals and hidden/unresolved surfaces. For verbal targets, distinguish user constraints from assumptions. A photo estimate is not exact mesh truth. Unresolved facts require another observation or an explicit assumption, not silently invented precision.

Before construction, declare required outlines, section centers/front and rear edges, recesses/negative spaces and relative placement. Extents alone cannot prove shape fidelity. Set scope, tolerance, protection and budgets before comparing candidates; do not loosen them after a failed result.

## Preview shape, then apply once

Use `model.loft`, `model.prism` or `model.recess` for supported geometry, after checking each current operation contract. Parallel section planes with moving centers differ from a tilted axis. A chamfer is straight; a round is curved. A multi-section request can need several native parts. Read compilation mappings, expected limits and piece budget before applying.

Shape operations preview a plan and return `reviewId`, also used as its intent ID. Commit through `edit.apply` with `{"review_id":"<returned reviewId>"}`. A fresh reviewed edit gets a new ID; retrying the original ID queries its existing execution. The result distinguishes preparation, native commit and postprocessing. If native commit succeeded but binding or script postprocessing failed, use `edit.resume` with `{"intent_id":"<original reviewId>"}`. Never replay a relative translation, rotation or scale because the overall script returned an error.

Use the returned current references. A stale-reference error is not evidence that a player edited the craft. Compare expected/current identities and the original journal; stop when safe attribution or rebinding is impossible.

## Compare and change one failed feature

Use `model.compare` with the frozen reference and candidate. Check top/side/front contours, declared section boundaries, recess occupancy and relative placements. Inspect the actual local comparison images; a screenshot path does not mean it was viewed or accepted. Multicomponent exterior/union and coplanar-seam limits must remain visible: `incomplete` is not zero error.

Choose the largest required residual, its feature and suggested parameter direction. Modify only that feature, compare again and check protected features for regression. Keep formal iteration records and the best fully measured candidate. Stop honestly for convergence, plateau, underconstraint, representation limit, invalid evidence, tool block, budget or changed live state. An improved top view does not make an unchanged bad side view pass.

## Deliver, reopen and recover

Use `task.deliver` for the supported inspection/save/reopen/rebind/recheck flow. Name the destination and save-as/overwrite intent explicitly. Saving may uniformly recenter the whole craft; only an evidenced common transform may compensate that shift. Never independently fit each part to erase a real placement error.

A checkpoint can be current-session-only and expire on load/restart/eviction. Read its lifecycle in the creation receipt. A mesh dump or diagnostic snapshot is not an executable cross-session recovery point. Use an explicit named native saved copy when lasting recovery is needed; keep its manifest, scope and verified identity. Delivery takes `{"name":"<unique native save name>","delivery_id":"<stable identifier>","overwrite":false,"allow_incomplete":false}`. Keep that ID unchanged during recovery.

After context loss, use `task.status` and original execution/intent IDs from disk. These records outrank a conversational summary. Query omitted sections; do not blindly rerun a saved script. Saving, reopening and rechecking are separate results; report remaining visual/seam/shape unknowns rather than declaring completion from a save receipt.

## Scope

For exact feature geometry keys and a runnable generic two-component verbal example, read [reference features](Modeling-Reference-Features.md). It supplies plain JSON requests, no model-specific reconstruction answer. `task.create` is required after binding; a source name alone does not create geometry checks. The current short host uses candidate ID `model`; Python tasks may define other candidate IDs.

The short host and Python SDK share the same product state; advanced custom code remains available. Use the installed help to determine actual operation coverage and fall back to documented SDK methods only where explicitly supported. Run edits through the SDK in the designer. Product constraints must be enforced by request/task validation, not by hoping every paragraph stays in context.

