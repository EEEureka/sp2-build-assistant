# Native navigation and selection

Use this when the user authorizes opening a test/design aircraft, entering the designer, selecting a part or closing the game without desktop input. These operations use game APIs; they do not simulate clicks or require window focus. They do not start a process that is not running. DLL replacement still needs a restart.

First read `sp2build designer status --json`. With multiple processes, use the same `--instance PID` on every call. Require `data.designerControl.available:true`; installing a new CLI alone does not add this capability to an already loaded DLL.

Discover exact native IDs with:

```powershell
sp2build designer crafts --query "Precision Lab" --limit 50 --json
sp2build commands schema --command designer.control
```

The catalog returns `data.items[].craftId/name/subdirectory`, with `total` and `offset`. It provides metadata, not offline component inspection. Never identify a file solely by a non-unique display name.

All actions require a unique `requestId` and `expectedScene` from current status. In the Designer also supply fresh `craftSessionId`, `expectedRevision` and the exact `expectedCraftName` from `craft snapshot`.

| action | Scene | Additional arguments | Effect |
| --- | --- | --- | --- |
| `enter` | MainMenu | none | Native designer startup may restore the previous editor aircraft; inspect it before writing |
| `load` | Designer | exact `craftId`, `discardCurrent:true` | Replace the open aircraft through the native loader |
| `select` | Designer | `partId` **or** `clear:true` | Set native primary selection; no aircraft content edit |
| `menu` | Designer | `discardCurrent:true` | Return to the native menu |
| `quit` | MainMenu or Designer | `discardCurrent:true` in Designer | Schedule native exit after the response; verify process exit separately |

Loading/closing can lose unsaved in-memory work; save desired changes first through the game's normal save workflow. The tool does not explicitly save an aircraft; normal game autosave/settings behavior remains native. Supply `discardCurrent:true` only within the user's authorized task. Loading even identical content creates a new session and invalidates checkpoints and revision-scoped references. Select preserves content and session, but changes what the player sees selected.

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

Call `sp2build designer control --input select.json --json`, then `designer selection`. Use `designer capture` to see the native view and actually open the downloaded images. Selection by API is not evidence that mouse hit testing or UI focus works.

On a scene/revision/session conflict, re-read and replan. On timeout, query the returned operation ID before retrying. A failed load reports whether the original content was restored; recovery establishes a new session. If state is uncertain, stop dependent writes. `shutdownScheduled:true` acknowledges a scheduled exit, not a confirmed terminated process.
