# Precision editing with sp2build

English · [简体中文](zh-CN/Precision-Workflow.md)

Use this 0.5.0 workflow for details such as a nose, window, pod, pylon or landing gear assembly. Review the native state, a comparable measurement and a matching view together.

## Run one refinement pass

1. Identify the parts to edit, the reference parts and the surrounding geometry to preserve. State a measurable target such as a width, section or clearance. Record dimensions that the reference does not show as unknown.
2. Read the effective properties and dependencies. Create a checkpoint and record the initial measurements and views.
3. Change one related group of parameters, wait for completion, and read back the affected parts.
4. Open the native images and compare matching views. Measure the actual mesh and inspect the full craft-state diff.
5. Retain a change that improves the result or restore the checkpoint. Report the remaining difference when the target has been met, repeated edits stop helping, or the native part cannot express the required shape.

For a nose, start with sections and seams, then refine windows. For a pod, choose the engine and fairing before locating the pylon. For landing gear, map the leg, wheel, door and piston dependencies before checking clearances.

## Discover properties and scope

```powershell
sp2build version --json
sp2build designer status --json
sp2build designer selection --json
sp2build craft snapshot --include-xml --output before.json
sp2build parts get --id 76 --json
sp2build properties get --id 76 --limit 1000 --json
sp2build commands schema --operation properties.set
```

Use actual part IDs from the open craft. `properties get` returns fields in `data.parts[].fields[]`. Use the case-sensitive `propertyId` and check `valueAvailable`, `value`, `editability`, `writeOperation`, `condition` and `currentCondition`, along with units, limits and resource options. An omitted XML field can still have an effective value.

For a part that is absent from the craft, search the catalog and run `properties describe --template-id TEMPLATE_ID`. Each part in a compound template has its own pagination.

| Goal | Interface | What to verify |
| --- | --- | --- |
| Sections, cuts, bevels, airfoils and control surfaces | `shape get/schema`, `shape.update`, `wing.control.add` | Measure actual sections after interpolation. |
| Windows, text, decals, fairings and mechanisms | `properties get`, `properties.set` | Use effective conditions and enumerated resources. |
| Material slots | `appearance get`, `appearance.set` | `clone` creates a local copy. `shared` affects all users of that material in the craft. |
| Rigid group positioning | `groups resolve`, `transform.apply` | Include dependent parts, such as the wheel on a gear leg. |
| Attachment alignment | `transform.align`, `connection.connect` | Alignment and creating a connection are separate operations. |
| Decal projector pose | `decal pose get`, `decal.pose.set` | The origin is the front projection plane. Local +Z covers zero to the configured depth. |

## Checkpoint, apply and compare

```powershell
sp2build craft checkpoint create --input checkpoint.json --json
sp2build batch preview --input patch.json --request-id PREVIEW_REQUEST_ID --json
sp2build batch apply --input patch.json --json
sp2build craft diff --checkpoint-id CHECKPOINT_ID --json
sp2build craft rollback --input rollback.json --json
```

For `patch.json`, use the following structure.

```json
{
  "craftSessionId": "CURRENT_SESSION",
  "expectedRevision": 12,
  "requestId": "UNIQUE_REQUEST_ID",
  "operations": [{
    "kind": "properties.set",
    "partId": 76,
    "symmetric": false,
    "patch": {"ProceduralWindow[0].height": 0.64}
  }]
}
```

The checkpoint input contains the same identity and request fields plus an optional `name`. Rollback adds `checkpointId`. Use a fresh request ID for each distinct action and re-read the current revision after each edit or restore. Preview validates the request without building geometry or reserving a revision. After applying, read `effectiveChanges`, `validation` and, on failure, `rollbackResult.restored` and `stateUncertain`.

Changing a gear style retains existing animation data. Recheck the poses and conditional fields for the new geometry. Set any newly available attachment options in a later operation. Symmetry still follows the native group and modifier settings.

## Capture and measure

```powershell
sp2build designer capture --input views.json --output-dir inspection --json
sp2build geometry section --input section.json --json
sp2build geometry seam --input seam.json --json
sp2build geometry measure --input clearance.json --json
```

Build each input from its command schema. Reuse `repeatableViews` and `repeatableResolution` from the native capture. Open the PNGs to inspect transparency, decals, text and occlusion. Automatic framing can change the scale between images.

`geometry measure` returns the nearest surface distance and witness points. Zero can indicate contact or intersection. Use `geometry seam` with a local plane and region to read sampled maximum and RMS error across the join. A cross-section is the intersection of the triangle mesh and the section plane.

Check `complete`, `exclusions` and `staleAtDelivery` before treating a result as evidence. Test the full path of a mechanism when checking motion and clearance.

## Navigate the designer

With the user's authorization, `designer crafts` and `designer control` can enter the designer, load a save, select parts, return to the menu or exit through native APIs. Loading or leaving can discard unsaved edits and invalidate checkpoints, so check the current identity and the `discardCurrent` requirement first. [Navigation command reference](../skills/sp2-build-assistant/references/designer-navigation.md)
