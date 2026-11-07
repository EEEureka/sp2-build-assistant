---
name: sp2-build-assistant
description: Build and revise SimplePlanes 2 vehicles through sp2model semantic modeling, native editing and recoverable tasks, using meshes, photos or verbal targets.
---

# SimplePlanes 2 modeling

For hard facets, chamfers or shading gradients, read [hard surfaces](references/Hard-Surfaces.md): native round-corner sampling does not guarantee a hard plane. Use actual render normals and whole-face coverage with the geometric and visual checks.

<!-- core:start -->
C01. Use installed `sp2model`; its launcher selects the owned Python runtime. Use current native plugin capabilities. Leave player aircraft XML and DSH source untouched.

C02. Check intended instance, craft session, revision and object identities before writes. Numeric IDs can be reused. Inspect and explicitly replan stale work while preserving player and concurrent edits.

C03. Persist execution IDs before writes. Timeout/interruption is not cancellation: query the original request/journal, never replace its ID or replay relative edits to guess the outcome.

C04. Start reconstruction with `sp2model model capabilities`; use operation-level `help` and nested topics before unfamiliar calls. Keep one persistent workspace for reference, task, reviews and journals. Read only relevant supporting topics.

C05. Before modeling actions, set and persist a detailed expected result: source/selection, units/frame, dimensions/proportions/features, hard planes versus smooth rounds, tolerances, allowed tradeoffs, protected objects, budget and verification/completion criteria. Read-only discovery can resolve missing facts first. Preserve independent section centers and local dimensions. Curved middle sections are controls. Two-sample native round corners do not guarantee hard planar shading.

C06. After acting, compare current native geometry, actual normals and fixed views with that expectation. Identify mismatches, revise locally and remeasure until required goals pass. Keep the original target and reasons for revisions; do not lower gates to claim convergence. At capability/budget limits retain incomplete status and a recoverable next action. Check related impact and actually view required images; setter success or an image path is not acceptance.

C07. Native commit and postprocessing are separate. If a later bind fails, use the original intent's `edit.resume`; do not replay the edit. `task.deliver` saves, reopens, rebinds and rechecks. Session checkpoints expire on reload; retain an explicit named native save when needed. Never roll back unrelated work.

C08. DSH can prune history. Delivery, receipt, comprehension and compliance differ; no permanent context guarantee. Native guards and external task state reduce dependence on prompts.
<!-- core:end -->

Tool update notices: when a result includes `notices`, tell the player the current/target versions and whether the information is stale. Run `sp2model updates guide` for the complete update instructions and actual installation paths; read [updates](references/Updates.md) when needed. `sp2model updates check` explicitly refreshes public GitHub metadata; `updates status` and `guide` stay offline unless `--live --instance ID` is requested. An update/restart notice does not authorize installation or restarting a game. Preserve accepted operation results and never replay a write because a notice/check failed. Wait for player and other Agents to finish and save before any later authorized restart.

For a new reconstruction read the short [semantic workflow](references/Modeling-Semantic-Workflow.md). Prefer its structured operations to writing a Python orchestration script. Blender is optional. Photos and words retain uncertainty; inferred values cannot silently become exact mesh truth. Confirm the installed capabilities, since an older installation may not have this entry.

For wings/controls, mechanics, sphere/dome, native attributes, output/Setter/FT or checkpoints, read the relevant [advanced interface](references/Advanced-Native.md). Read [API signatures](references/API.md) before new calls; check loaded versions.

For part choice or unfamiliar XML/FT, use the [knowledge index](references/Knowledge.md): search purpose first, then read the selected part's field and enum details. Keep template defaults, current values, cached values and source-only fields distinct. Use [FT guidance](references/Knowledge-Funky.md) for input scope, state functions and output bindings. Offline knowledge does not certify writable support or running behavior; refresh the explicitly selected instance when live availability matters. Fetch relevant records/pages, not the entire catalog.

## Short operations

```powershell
sp2model model capabilities
sp2model model help --input-file help.json
sp2model model reference.bind --workspace model-task --input-file reference.json
sp2model model task.create --workspace model-task --input-file task.json --instance <id> --craft "<loaded-name>"
```

`help.json` can contain `{"operation":"model.loft"}`; add `"topic":"/properties/shape/properties/stations"` for nested fields. Use the returned schema rather than guessing field spellings. JSON files avoid shell quoting problems. Live commands require explicit instance and currently loaded craft. Keep `--workspace` unchanged; `task.status` without selectors reads disk and marks native freshness unchecked.

Bind/inspect the correct reference, then `task.create` freezes its feature checks. Preview `model.loft/prism/recess`, inspect native mapping and limits, then `edit.apply` with the exact returned `review_id`. The review ID is also the stable intent ID. Repeating it queries the original operation. `model.move/rotate/scale/patch` similarly preview a current component; uniform group scaling uses an explicit shared pivot.

Run `model.compare`, inspect required local images and act on failed features. Preserve the common frame across views and components; width/height alone cannot detect a bad slope or missing slot. On uncertainty use `task.status`, `edit.resume` with `intent_id`, or query the returned original journal. A postprocessing error can follow a successful native commit.

Use `task.deliver` with `name` and a stable `delivery_id`. Reusing that delivery ID resumes its original save/load. `allow_incomplete:true` preserves a partial candidate but never marks it delivered. Proven whole-craft recentering is recorded separately from local offsets; old metrics cannot certify a new epoch.

Stop at declared success, plateau, underconstraint, representation/evidence/tool limit, budget or changed scene. Record unmet metrics and interventions. Aggregate `transport.commandPostAttempts` separately from native operations, iterations and wall time.

For custom Python use [SDK task workflow](references/Modeling-Workflow.md) and [lifecycle example](examples/modeling_task.py). `sp2model run` injects `session/task_parameters`; assign `result`. It executes trusted Python. Keep project/task/journal files, explicit writable scope, original IDs and current references. SDK and semantic operations share task state.

For MainMenu/offline management, catalog, reference/worker analysis and history read [Runtime/services](references/Services.md). `Runtime.control(...)` needs no fake craft in MainMenu. Discover `sp2model commands list`, `commands schema --command NAME` / `--operation KIND`; `doctor --live` compares installed and loaded versions.

For other published edits use `session.native_plan(operations,writable=[current_parts],variables=[reviewed_names])`, review `.preview()`, then `.apply(token)`. CLI batches need explicit modelScope and a saved preview passed with `--review`. Fit/structure workflows use `session.service(...)` and frozen plans/journals. Worker installation is explicit; discovery never downloads.

Read [precision](references/precision-building.md), [continuous shapes](references/low-part-native-modeling.md) and [build loop](references/build-loop.md) for applicable geometric decisions. Their native semantics remain relevant; current signatures and review rules are in Services/API.
