# Native navigation and selection

Use this when the user authorizes opening a test/design aircraft, entering the designer, selecting a part or closing the game without desktop input. These operations use game APIs; they do not simulate clicks or require window focus. They do not start a process that is not running. DLL replacement still needs a restart.

First read `sp2model designer status --json`. With multiple processes, use the same `--instance PID` on every call. Require `data.designerControl.available:true`; installing a new CLI alone does not add this capability to an already loaded DLL.

Discover exact native IDs with:

```powershell
sp2model designer crafts --query "Precision Lab" --limit 50 --json
sp2model commands schema --command designer.control
```

The catalog returns `data.items[].craftId/name/subdirectory/lastModifiedUtc`, with `total` and `offset`. It provides metadata, not offline component inspection. Never identify a file solely by a non-unique display name.

All actions require a unique `requestId` and `expectedScene` from current status. In the Designer also supply fresh `craftSessionId`, `expectedRevision` and the exact `expectedCraftName` from `craft snapshot`.

| action | Scene | Additional arguments | Effect |
| --- | --- | --- | --- |
| `enter` | MainMenu | none | Native designer startup may restore the previous editor aircraft; inspect it before writing |
| `load` | Designer | exact `craftId`, `discardCurrent:true` | Replace the open aircraft through the native loader |
| `select` | Designer | `partId` **or** `clear:true` | Set native primary selection; no aircraft content edit |
| `save` (0.5.1+) | Designer | `name`, optional `overwrite:true` | Persist the open aircraft through `Designer.Save`; verify the target native save receipt |
| `new` (0.5.1+) | Designer | `discardCurrent:true` | Replace the editor with the native blank craft template and its starter parts |
| `delete` (0.6.0+) | MainMenu or ready designer | exact `craftId`, `expectedSavedName`, `expectedSavedModifiedUtc` | Delete one authorized saved craft through the native database; preserve the open aircraft |
| `menu` | Designer | `discardCurrent:true` | Return to the native menu |
| `quit` | MainMenu or Designer | `discardCurrent:true` in Designer | Schedule native exit after the response; verify process exit separately |

Loading, new and closing can lose unsaved in-memory work. Use `save` first for desired changes. Check the loaded `actions` list: installing the CLI does not add `save`/`new` to an old loaded DLL. Supply `discardCurrent:true` only within the user's authorized task. Loading even identical content and creating a new craft establish a new session and invalidate checkpoints and revision-scoped references. Select preserves content and session, but changes what the player sees selected.

Version 0.6.0 also recognizes an active flight-scene designer in `Terrain`. Require `designerReady:true` and `designerMode:"flight"`; the scene name alone does not establish edit readiness. Supply `expectedScene:"Terrain"` and the same fresh identity/name guards. A transitioning or inactive designer is rejected.

For authorized save cleanup, refresh the catalog immediately before each deletion and copy its exact ID, name and UTC timestamp into `delete`. A changed timestamp/name stops deletion. Stock, required, autosave, quicksave and the current craft's named save are protected. The result must include `deletedCraft.deletionVerified:true`; requery the catalog and verify the open craft identity afterwards. Deletion removes the named save; a checkpoint does not recover a deleted persistent save. Prefer overwriting a known working save during iterative modeling to creating a new name for every pass.

## Saving and creating a blank craft

`save` requires a fresh Designer identity, `expectedCraftName` and unique `requestId`, just like other writes. `name` is the native save name **without `.xml`**, optionally including relative folders (for example `Cargo/C17`). It is relative to the native craft root, independent of the selected native folder. Absolute paths, traversal, invalid filename characters, Windows device names, hidden reserved names and stock/required/autosave/quicksave folders are rejected. Unicode names are supported. `craftId` is only for loading and is not a save argument.

An existing target returns `craft_exists` without saving unless `overwrite:true` is explicitly provided. Overwrite retains the game's native backup behavior. Do not infer overwrite authorization from a similar display name; identify the exact target using `designer crafts`. Native save may rename/recenter the open craft, update its bounds and revision, and save the editor copy and autosave. Use the returned `identity` before the next write. A successful result has `saved:true` and `persistedCraft` with the exact ID, name, overwrite status, timestamp and `verification:"native_database_save_return"`. This verifies the native database completed its write, not cloud synchronization. Errors include whether the target write completed; editor/autosave or in-memory changes can already have occurred, so do not automatically roll back files or blindly retry.

Example save request:

```json
{
  "requestId": "UNIQUE_SAVE_REQUEST_ID",
  "action": "save",
  "expectedScene": "Designer",
  "expectedCraftName": "CURRENT_CRAFT_NAME",
  "craftSessionId": "CURRENT_SESSION",
  "expectedRevision": 12,
  "name": "C17",
  "overwrite": true
}
```

Submit with `sp2model designer control --input save.json --json`. `new` uses the same freshly read guards, `action:"new"` and `discardCurrent:true`. It calls the game's own New Craft method and verifies the native blank template. On game 0.7.8.103 the template has two starter parts: a Flight Computer and a Fuselage. This is the game's blank aircraft, not a zero-part craft. `new` returns `saved:false` and does not create a named persistent file. To make a new empty save, call `save` afterwards using the new identity and craft name. Both actions require Designer, and reject active tutorials; `new` is unavailable in the game demo.

Timeout/retry semantics are unchanged: resolve the original operation/request ID before sending another save or new request. A session checkpoint is not a persistent save.

Example `select.json` (replace guards and ID from the current snapshot):

```json
{
  "requestId": "UNIQUE_REQUEST_ID",
  "action": "select",
  "expectedScene": "Designer",
  "expectedCraftName": "Aircraft",
  "craftSessionId": "CURRENT_SESSION",
  "expectedRevision": 12,
  "partId": 19
}
```

Call `sp2model designer control --input select.json --json`, then `designer selection`. Use `designer capture` to see the native view and actually open the downloaded images. Selection by API is not evidence that mouse hit testing or UI focus works.

On a scene/revision/session conflict, re-read and replan. On timeout, query the returned operation ID before retrying. A failed load reports whether the original content was restored; recovery establishes a new session. If state is uncertain, stop dependent writes. `shutdownScheduled:true` acknowledges a scheduled exit, not a confirmed terminated process.
