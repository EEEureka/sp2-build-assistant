# SP2 Build Assistant development

- This directory is the independent plugin repository. Read `docs/SESSION-HANDOFF.md` and `docs/Verification-0.5.0.md` for the current baseline before continuing older work.
- The parent workspace's `Game` directory is read-only decompiled reference. Do not modify or commit game assemblies, game source, player aircraft files, instance tokens, or test runtime copies.
- Use the globally installed `sp2build` command to interact with the game. Do not substitute direct Python CLI invocation in agent-facing instructions. Editing applies only to the aircraft currently loaded in the designer.
- The user does not want computer use, foreground activation, desktop keyboard/mouse automation, or DSH delegation. Use plugin APIs for loading, entering the designer, selecting, capturing, and quitting. A hidden local process bootstrap is allowed when a task authorizes starting the game.
- Verify current craft/session/revision before writes; use checkpoints and inspect final state. Live destructive acceptance runs belong on explicitly named native test copies, never the player's original C17. No new live edit is authorized merely by reading this handoff.
- `tests/artifacts/` contains valuable local-only evidence, player-derived snapshots, tokens and runtimes with junctions into the installed game. Never recursively delete or move these runtimes. Keep historical failures; do not rewrite them as passes.
- Run appropriate tests and distinguish compilation, deployment, loaded-module verification, native functional checks, visual inspection, and user aesthetic approval. A successful setter or screenshot path is not visual acceptance. Keep the frozen acceptance scope and limitations explicit.
- Ship without `-AcceptanceHooks`. Test host binaries and game dependencies must not enter release archives. DLL updates require a game restart; hot replacement is not implemented.
