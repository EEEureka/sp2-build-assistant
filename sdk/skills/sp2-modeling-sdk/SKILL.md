---
name: sp2-modeling-sdk
description: Build and revise SimplePlanes 2 vehicles with route 1 semantic operations or custom Python SDK, durable tasks and native geometry evidence.
---

# SP2 modeling SDK

Before modeling actions, persist a concrete expected result: dimensions, features, hard/soft edges, tolerances, allowed tradeoffs, protected parts and completion checks. Use read-only discovery to fill missing facts. After each bounded change, compare actual geometry/normals and fixed native views with the target, locate mismatches and revise until required goals pass. Do not reduce targets to claim convergence; if capability or budget prevents completion, retain incomplete status and a recoverable next step. For hard faces read [hard-surface construction and verification](../../Hard-Surfaces.md).

Start with `sp2model model capabilities` and operation-level help. Read the short [semantic workflow](../../Modeling-Semantic-Workflow.md) for reconstruction; use one persistent `--workspace`. `reference.bind/inspect` freezes source/selection/frame/features; `task.create` freezes checks; shape operations produce a reviewed plan, then `edit.apply` accepts its exact `review_id`. Python is optional for this flow. Blender is optional; photo/verbal uncertainty remains explicit.

Use the installed `sp2model` launcher with the intended instance/craft, persistent `--project` and `--journal-dir`. `run` injects session/task_parameters; assign result. Code is trusted Python, not a sandbox. Host success is not acceptance. Consult [API](../../API.md) before new calls and [advanced interfaces](../../Advanced-Native.md) for wings, mechanics, native attributes, logic and checkpoints. Leave DSH and player XML untouched.

Use `model.compare` and inspect required images; bounds alone cannot certify slopes, recesses or relative placement. Read `help` with `operation` and a JSON-pointer `topic` for nested geometry. A preview does not edit the craft. A failed postprocessing step may follow a successful native commit: use `edit.resume` with the original `intent_id`, never replay a relative edit.

Use `task.deliver` with explicit `name` and stable `delivery_id`; it saves/reopens/rebinds/rechecks. Retrying the same ID queries the original save/load. `allow_incomplete:true` preserves partial work but returns delivered:false. A common recentering transform needs whole-craft evidence, not per-part fitting. After context loss query `task.status`; an offline summary explicitly lacks current native freshness.

For custom code read [SDK modeling workflow](../../Modeling-Workflow.md) and [runnable lifecycle example](../../examples/modeling_task.py). `session.task(path)` retains references/metrics/candidates and links `task.apply` to its original journal; explicit bind/check remain available. On interruption call `task.resume()`. Saving/reopening returns a new session; old handles and measurements remain historical.

`keep_best` creates a whole-craft checkpoint in the current epoch; loading/restarting can expire it. For cross-session retention use an explicit named native save. Review `restore_preview` before `restore(token, accept_whole_craft=True)`; the review token survives script restarts, but cannot extend the native checkpoint's lifetime. After exact restore explicitly rebind from_best and remeasure. Never overwrite concurrent changes implicitly.

Use explicit writable parts and current handles, metres/declared units and xyzw quaternions. Freeze tolerances, frames, protection, required coverage and budgets. Compare native continuous shapes first, measure complete required profiles/surfaces and inspect required images. Unsupported evaluators remain incomplete; averages/extents cannot hide missing features. Retain task files and fitting evidence; stop honestly at limits. External records do not guarantee DSH prompt retention or comprehension.
