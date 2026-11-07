# sp2build CLI reference

English · [简体中文](zh-CN/CLI-Usage.md)

For the latest [v0.7.8 release](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.7.8), use the [SDK installation and modeling guide](SDK-0.7.8.md). This reference covers the legacy 0.5.0 CLI.

This reference covers the 0.5.0 command-line package. The agent runs the installed `sp2build` launcher on the same Windows computer as the game. Start with [installation](Installation.md) and [the first agent-assisted task](Quickstart.md).

## Invocation and discovery

```powershell
sp2build version --json
sp2build instances list
sp2build designer status
sp2build capabilities
sp2build skill path
sp2build commands list
sp2build commands schema --command batch.apply
sp2build commands schema --operation part.update
```

`version` identifies the CLI. `instances list` and `designer status` identify the loaded plugin. Use the current installation's `commands list` for supported commands and batch operations. Query the command schema for input and output fields and the operation schema for a batch item's fields.

| Option | Use |
| --- | --- |
| `--instance PID_OR_ID` | Select a running game by PID or instance ID. |
| `--input FILE` | Read a UTF-8 JSON object. Use `--input -` for standard input. |
| `--output FILE` | Save the full JSON result and print a receipt with the output path, SHA-256 and `resultSuccess`. |
| `--output-dir DIR` | Choose the folder for downloaded images and manifests. |
| `--json` | Explicitly request the default JSON output. |
| `--async` | Return after submission, then check the operation's outcome. |
| `--timeout SECONDS` | Bound how long the CLI waits. The default is 20 seconds, with a maximum of 600. |
| `--request-id ID` | Set the deduplication ID, overriding the input object's `requestId`. |

Check both the exit code and the `success` field. Read results from `data`, failures from `error`, and asynchronous outcomes from the original operation. When saving a result to a file, use the receipt to locate and read that file.

## Read the current craft and part catalog

| Task | Command |
| --- | --- |
| Confirm the designer is ready and inspect selection | `sp2build designer status`, `sp2build designer selection` |
| Snapshot the craft, optionally including its current XML | `sp2build craft snapshot --include-xml --output snapshot.json` |
| List parts by name or type | `sp2build parts list --query Fuselage --limit 20` or `sp2build parts list --type JFuselage-1` |
| Inspect one part, its state tree, outputs and attach points | `sp2build parts get --id 15` |
| Resolve native assembly membership | `sp2build parts assembly --id 229` |
| Read connections and available attachment points | `sp2build connections list`, `sp2build connections points --part 15` |
| Compare two parts in space | `sp2build spatial query --part-a 15 --part-b 16` |
| Browse or search native templates | `sp2build catalog categories`, `sp2build catalog search --query Block --limit 20` |
| Inspect a template or its editable metadata | `sp2build catalog get --id TEMPLATE_ID`, `sp2build catalog schema --id TEMPLATE_ID` |
| Query effective field values and conditions | `sp2build properties get --id 15`, `sp2build properties describe --template-id TEMPLATE_ID` |
| Export native or offline catalog data | `sp2build catalog export --output catalog-runtime.json`, `sp2build knowledge catalog --output catalog-offline.json` |

Use the actual IDs returned by the current game. A numeric part ID can be reused after deletion, and a template ID refers to a catalog entry rather than an existing part. Live catalog queries include native defaults, enums, descriptions and condition-dependent metadata. Check `defaultState` for preset values and the effective property query for a live part. An omitted range or default means the metadata did not provide it.

Use `--view structured` where the schema supports it to obtain the structured connection, variable or output view. The connection graph describes topology. Use mesh geometry, transforms and ray queries to locate parts spatially. Alignment and creating a connection are separate steps.

For scoped visual and numeric review, see [native screenshots](Designer-Screenshots.md), [mesh inspection](Visual-Usage.md), [aircraft centers](Centers-Usage.md), and [precision editing](Precision-Workflow.md).

### Native designer navigation

With the player's authorization, `designer crafts` lists native saves and `designer control` can enter the designer, load a save, select parts, return to the menu or exit. Read the current identity and the schema for the specific action. Loading or leaving can discard unsaved edits. Check the `discardCurrent` requirement before proceeding. Editing operates on the craft open in the designer. [Navigation command reference](../skills/sp2-build-assistant/references/designer-navigation.md)

## Apply a batch

Read `craftSessionId` and `revision` immediately before editing. `expectedRevision` protects the state you inspected. The session can change when a craft is loaded or replaced. Read both fields again after an edit or recovery.

Save the following as `batch.json` and replace the example identity, template and request ID.

```json
{
  "requestId": "APPLY_REQUEST_ID",
  "craftSessionId": "SESSION",
  "expectedRevision": 1,
  "operations": [
    {"kind": "part.add", "templateId": "TEMPLATE_ID", "temporaryId": "blockA", "position": [20, 5, 0], "rotation": [0, 0, 0]},
    {"kind": "part.update", "partId": "blockA", "changes": [
      {"path": "", "attribute": "name", "value": "AgentBlock"},
      {"path": "", "attribute": "massScale", "value": 1.25}
    ]}
  ]
}
```

```powershell
sp2build batch preview --input batch.json --request-id PREVIEW_REQUEST_ID
sp2build batch apply --input batch.json
```

Use a distinct request ID for preview. Preview validates the input structure. Apply executes the native edits. A batch accepts one to 100 operations in array order. A `temporaryId` refers to a newly added part in that batch. After applying, use `temporaryIds`, `reusedPartIds` and `invalidatedTemporaryIds` together with a fresh read to find the surviving parts.

| Operation | Input and behavior |
| --- | --- |
| `part.add` | `templateId`, optionally `temporaryId`, `position` and `rotation`. Position places the template's first part in world space. Rotation is an Euler offset around that part. |
| `part.update` | `partId` and `changes`. Each change contains an `attribute`, a `value`, and optionally the state-tree `path`. An empty path targets the part root. |
| `part.delete` | `partId`, optionally `symmetric` or `assembly`. Assembly deletion applies to supported native ownership relationships. The active main cockpit is protected. |
| `connection.connect` | `partA`, `partB`, `attachPointA`, `attachPointB`, optionally `symmetric`. Native availability and compatibility checks apply. |
| `connection.disconnect` | `partA`, `partB`, optionally `symmetric`. Removes all connections between the two parts. |

Use `commands schema --operation` for typed shape, symmetry, material, group, alignment and other native operations. Single-operation commands such as `parts update` and `connections connect` take an input file. Read `effectiveChanges`, `actualChanges` and `validation` after execution. On failure, inspect `rollbackResult.restored` and `stateUncertain` before writing again.

## Variables, part outputs and Funky Trees

```powershell
sp2build variables list
sp2build outputs list --part 20
sp2build funky list
sp2build funky describe --name clamp
sp2build funky validate --expression 'clamp(Throttle,0,1)'
sp2build funky validate --expression 'Activate1' --type bool
```

Global variable setters are ordered. Part outputs are addressed by native part ID, modifier and output ID. They can feed named variables through a binding. Read the available outputs from the selected part and verify the input field and data type where the variable will be used.

| Operation | Fields |
| --- | --- |
| `variable.add` | `variable`, `function`, optional `priority` and `activator` |
| `variable.update` | `index` and the fields to change |
| `variable.delete` | `index` of the specific setter |
| `variable.reorder` | `order` containing every current setter index once |
| `output.bind` | `partId`, `modifier`, `outputId`, `variable`, optional `priority` and `activator` |
| `output.update` | Existing output binding identity and the fields to change |
| `output.unbind` | `partId`, `modifier` and `outputId` |

`funky list` reads the current native expression context, including constants, functions and inputs. `funky describe` matches the exact name. `funky validate` compiles an expression with the requested type. Check `compiledOnly` and `evaluated`, then test the logic in the game under the intended conditions.

## Checkpoints and recovery

```powershell
sp2build craft history
sp2build craft checkpoint list
sp2build craft checkpoint get --id CHECKPOINT_ID
sp2build craft checkpoint create --input checkpoint.json
sp2build craft diff --checkpoint-id CHECKPOINT_ID
sp2build craft rollback --input rollback.json
```

A checkpoint input contains `requestId`, `craftSessionId`, `expectedRevision`, and optionally `name`. A rollback input adds `checkpointId` and uses a fresh request ID and current revision.

Checkpoints are stored in the current designer session, up to 64 including automatic ones. Rollback restores the whole checkpoint state, so it can also affect work performed by the player since that point. `craft undo --input undo.json` follows native undo order for both player and agent changes. Re-read the craft after either action. If the tool reports uncertain state, resolve recovery before continuing ordinary edits.

## Asynchronous operations

```powershell
sp2build batch apply --input batch.json --async
sp2build operation status --id OPERATION_ID
sp2build operation wait --id OPERATION_ID --timeout 60
sp2build operation result --id OPERATION_ID
sp2build operation cancel --id OPERATION_ID
```

`status` reads the current task state. `wait` and `result` may wait for the result. `cancel` requests cancellation, so check the terminal state. Keep the original operation and request IDs after a timeout. Results can expire or become unavailable after a restart even if the edit ran. Reconcile the current craft before retrying.

## Common errors

| Exit code | Typical meaning |
| --- | --- |
| 0 | Command succeeded. Check the final task result for asynchronous work. |
| 2 | Invalid input or unsupported command |
| 3 | Bridge unavailable or ambiguous game instance |
| 4 | Session, revision, request or history conflict |
| 5 | Operation, validation, recovery or result error |
| 8 | Wait timed out |
| 9 | Operation ID unavailable |

Use `error.code` to choose the next step. For `session_conflict` or `revision_conflict`, re-read and re-plan against the current craft. For `multiple_instances`, select the game explicitly. For `part_not_found`, refresh the part list. For invalid properties or rejected connections, read native metadata and availability before revising the request.

Game saves, flight behavior, complete mechanism trajectories and aesthetic approval belong to the relevant in-game review. A craft snapshot is a JSON export of the current designer state.
