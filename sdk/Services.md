# sp2model Runtime and services (0.7.8a1 development)

This is the public migration interface. It operates directly through the native
bridge and SDK-owned services. The retired tool's launcher/main is not called.
The installed version and native functional coverage are separate facts.

0.7.8 adds [GitHub updates](Updates.md): `Runtime.updates.check/status/guide` and
`sp2model updates check/status/guide`. Status/guide stay local unless `--live
--instance ID` explicitly requests capabilities; check reads public release
metadata. Installed live tool hosts schedule a bounded hidden worker and attach
cached `notices`, without delaying native operations or installing/restarting.
The guide describes the selected installation; old global tools are separate.

## Offline and MainMenu

0.7.7 adds the [versioned part/XML knowledge index](Knowledge.md) and
[Funky Trees explanations](Knowledge-Funky.md). `knowledge status/search/get/export`
work offline without discovering an instance or creating journals. Only explicit
`knowledge refresh --instance ID` reads the live directory/context; it never
evaluates FT or modifies the craft. Static source claims and live compatibility
are reported separately.

```powershell
sp2model version
sp2model instances list
sp2model commands list
sp2model commands schema --command designer.control
sp2model commands schema --operation connection.connect
sp2model build prepare --task-kind complete
sp2model build guide --topic precision --page 0
sp2model doctor
sp2model doctor --live --instance <id>
sp2model catalog search --instance <id> --query Engine
```

The CLI returns `{ok,result,error,transport}`. Native/service result data is in
`result`, not the old CLI's `data`. `--output FILE` writes the result itself;
stdout reports its path/hash. It never replays a write if saving output fails.
No game is needed for version/help/contracts/knowledge/guidance/worker doctor.
`doctor --live` also reports the actual loaded plugin and capability contract.
Neither doctor nor imports download dependencies. Select an instance explicitly
when multiple games are running.

```python
from sp2model import Runtime
runtime = Runtime(instance=instance_id, journal_dir="runtime-journals")
state = runtime.status()
entered = runtime.control("enter")  # valid in MainMenu; no fake craft
# After entry, inspect the actual name/session before replacing anything.
state = runtime.status()
blank = runtime.control("new", expected_craft=state["identity"]["craftSessionId"],
                        discardCurrent=True)
state = runtime.status()
session = runtime.session(state["identity"]["craftSessionId"], project_path="model.json")
```

`control(action, expected_craft=None, **native_options)` supports enter, load,
select, save, new, delete, menu and quit. Designer/Terrain require the intended
current craft; new/load/menu/quit also require explicit `discardCurrent=True`.
Delete additionally needs `craftId`, `expectedSavedName` and
`expectedSavedModifiedUtc` from `designer.crafts`. Save/reopen through Session or
task remains preferable for modeling, since it returns updated object context.
The CLI `designer control --input FILE` requires requestId and the native
scene/session/revision/name guards from `designer status`.

## Native query and editing

`runtime.call(command, arguments=None)` supports published native reads,
offline knowledge, reference engineering and operation lifecycle. Discover full
input/output contracts with commands schema. For craft queries,
`session.read(command, **arguments)` adds its captured identity where supported.
It does not auto-rebase stale selections. Native shape, mechanics, FT, outputs,
resource discovery and typed modeling APIs from API/Advanced-Native continue.

```python
part = session.inspect().part(id=part_id)
before = session.read("connections.points", part=part.id)
plan = session.native_plan([
    {"kind": "symmetry.enable", "partId": part.id, "enabled": False}
], writable=[part])
preview = plan.preview()  # review report and all direct/indirect effects
receipt = plan.apply(preview.token)
after = session.read("symmetry.get", part=part.id)
```

NativePlan accepts all 33 published operation kinds, with the same native
scope/identity/readback/durable recovery guards as Plan. Existing targets must
be explicitly writable; use `[]` for creation only. Setter operations require
`variables=[...]`. Shared paint additionally requires `material_ids=[...]` and
all current users in writable; other palette entries remain protected. Whole-craft
refresh requires every current part explicitly reviewed. It doesn't infer semantic names for raw temporary IDs; select
created objects using the verified receipt/native readback and track explicitly.
Use constructors for modeling and typed FT/mechanical edits when available.

CLI batches: supply `craftSessionId`, `expectedRevision`, `operations` and
`modelScope: {writablePartIds:[...],variableNames:[...]}`. Run `sp2model batch
preview --input plan.json --output review.json --instance ID`, inspect the
result, then `sp2model batch apply --input plan.json --review review.json
--instance ID`. A copied/repeated review resumes its original execution rather
than applying relative edits twice. An altered plan/baseline needs a new review.

`session.scope(parts,boundary=(),owner_id=...)` captures native collaboration
protection, with `.inspect()`, `.preview(operations)`,
`.apply(operations,preview_token=...,chunk_size=1,wait=True)` and `.release()`.
Review its preview before apply. Unrelated global revisions do not recapture or
expand native scope; conflicting content/dependencies still stop chunks.
`wait=False` returns a durable Runtime journal for original-operation queries. Chunks
may remain on later conflict/cancel; no implicit whole-craft rollback occurs.
`session.undo_preview()` and `undo(token,accept_whole_craft=True)` review current
history before native undo. Checkpoints/diff/restore use the documented Session
and task methods; exact, partial and uncertain outcomes keep their native meaning.

## Reference, analysis and existing build loops

```python
runtime.call("reference.create", {"project": "reference.json", "name": "Photo target"})
runtime.call("image.inspect", {"path": "reference.png"})
runtime.call("reference.doctor")
# Explicit installation only. Supply the distribution's verified wheelhouse.
runtime.call("feature.setup", {"python": base_python, "offline": True,
                              "wheelhouse": wheelhouse_path})
runtime.call("mesh.inspect", {"path": "reference.obj"})
session.service("build.loop.status", journalPath="existing-loop.jsonl")
```

Image/mesh/Blender providers, reference source/annotation/calibration/constraints/
projection/binding/freezing/three-way merge/render/compare, bounded fit,
representation/quality/regional review and structure plans are SDK-owned services.
Use commands schema for exact command parameters; each service retains its
existing frozen camera/reference/shape limits and artifact hashes. Blender is
optional. Numerical operations run a one-request isolated CPU worker and never
write the game. Worker processes exit on completion and are killed on timeout.

`session.service(command, **arguments)` supplies the live callback for guarded
fit/structure/build-loop workflows. Old frozen formats and append-only journals
stay compatible; ownership, stale evidence, goals, budgets and restore boundaries
are retained. Native subrequests are durably journaled before submission. Use
the same loop/task paths when linking evidence; calling a service doesn't mark
any ModelingTask metric passed automatically. Modeling uses `session.task` as
the primary workflow; old build-loop documents retain their original denominators.

The worker uses `SP2MODEL_HOME` (default shared `.sp2build`) and its own
`workers/sp2model-reference-cpu` environment. It does not fall back to the old
worker. `SP2MODEL_REFERENCE_PYTHON` is an explicit absolute-path override for
diagnosis; clear it before managed installation. Locked dependencies are bundled
separately from the standard-library SDK; missing dependencies have a concrete
doctor reason. User projects in shared `.sp2build` are retained.

## Async, artifact and historical recovery

`runtime.operation(id,action="status"|"wait"|"result"|"cancel")` queries the
original ID. Cancellation is a request; only terminal native status proves it
took effect. CLI native reads/control support `--async`. Modeling apply timeout
retains a Session journal; resume that known execution rather than rerun scripts.
`runtime.artifacts(result,directory)` downloads authenticated hash-verified files.
CLI captures accept `--output-dir DIR`. Open actual images before visual claims.

`runtime.history(path,reconcile=False)` / `sp2model history inspect --path FILE`
reads original JSON or verifies an old hash-chain journal. `history reconcile`
queries original pending request/operation IDs without changing source records.
Unsupported formats stay read-only with their original path. SDK execution uses
`session.resume(path)`; Runtime control/orchestration uses `runtime.resume(path)`
or `sp2model runtime resume --journal FILE --instance ID`. Query against the
original instance; an unavailable or expired result doesn't authorize replay.

Skill/core hashes describe delivered resources. An assistant can later prune context;
permanent retention, comprehension and compliance are not guaranteed.

