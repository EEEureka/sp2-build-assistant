# Your first agent-assisted task

English · [简体中文](zh-CN/Quickstart.md)

For the latest [v0.7.8 release](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.7.8), use the [SDK task workflow](SDK-0.7.8.md#run-a-modeling-task). The commands below apply to legacy 0.5.0 installations.

Install the matching plugin, CLI and `sp2-build-assistant` skill. Give the skill to an agent that can run commands on the Windows machine where the game is running. Open a test craft or a working copy in the designer.

## Give the agent a concrete task

Start with a small area and a result you can compare. Try a task like this.

> Check the seam between the two fuselage sections in the open craft. Locate both parts, measure the gap, and tell me what you intend to change. Keep the surrounding geometry in place. After editing, show the same view and report the remaining gap.

## What the agent does

1. **Confirm the target.** Read `sp2build designer status` and `sp2build designer selection`. Use `sp2build parts get --id 42` with the actual part ID. Use `sp2build catalog categories` to explore part templates and `sp2build craft snapshot --output baseline.json` to capture the current designer state.
2. **Choose how to inspect the result.** Use [native screenshots](Designer-Screenshots.md) for paint, transparency and occlusion. Use the geometry commands in the [precision guide](Precision-Workflow.md) to measure a gap, cross-section or positional difference.
3. **Apply a scoped edit.** Read the relevant schema in the [CLI reference](CLI-Usage.md), fill in the current `craftSessionId`, `expectedRevision` and a fresh `requestId`, and create a checkpoint. Validate the request with `sp2build batch preview --input batch.json --request-id PREVIEW_REQUEST_ID`, then apply it with `sp2build batch apply --input batch.json`. Replace the preview ID with a unique ID distinct from the apply request.
4. **Compare and iterate.** Read back the affected parts and connections, capture the same view and repeat the measurement. Restore the checkpoint if the change misses the target. Obtain a fresh craft session and checkpoint after opening another craft or restarting the game.

If a command times out, query the original operation or request ID before submitting further edits. A new request ID can cause the same operation to run again.

Use the game's save flow when you want to retain a design. The JSON snapshot records designer state for inspection. For Funky Trees, begin with `sp2build funky describe --name clamp`, then test the validated expression in the game under the relevant inputs.
