# SP2 Build Assistant 0.7.8

English · [简体中文](zh-CN/Release-0.7.8.md)

Released on November 7, 2026. This package contains **plugin 0.7.8** and **Python SDK 0.7.8a1** for agents working in the SimplePlanes 2 designer.

Download [sp2build-0.7.8.zip](https://github.com/EEEureka/sp2-build-assistant/releases/download/v0.7.8/sp2build-0.7.8.zip) and the [SHA-256 file](https://github.com/EEEureka/sp2-build-assistant/releases/download/v0.7.8/sp2build-0.7.8.sha256), then follow the [installation guide](SDK-0.7.8.md). The complete ZIP includes the plugin, SDK, agent skill and offline reference-worker dependencies.

## Included capabilities

- Native part inspection, scoped modeling and editing, logical part bindings, task journals and explicit recovery through the `sp2model` interface.
- Fuselage and wing modeling, supported mechanisms and controls, hard-surface refinement, native measurements and designer views.
- A curated native-parts and Funky Trees knowledge index. Effective properties and write conditions remain available from the selected game instance.
- Public GitHub release checks through `updates check`, local version and component reporting through `updates status`, and installation-specific instructions through `updates guide`.
- English and Chinese installation instructions and project documentation.

## Installation requirements

Use Windows x64, BepInEx 5 for Mono and 64-bit Python 3.12. The installer verifies the selected game's `Game.dll` against the package manifest. Use a matching package when the game has changed.

The SDK retains its `0.7.8a1` package version. Keep it paired with plugin `0.7.8` as shipped in this archive. Update checks report available versions. Installation and game restart are explicit user actions.

## Validation and scope

The plugin and SDK code match the previously validated 0.7.8 package. The release preparation changes user documentation and package contents while preserving the plugin DLL, SDK wheel and locked worker wheels. Package hashes, installation in a separate test directory, command discovery and the knowledge resources were checked.

Some advanced knowledge explanations remain incomplete. Query the native effective properties before editing a specific part. Confirm appearance, mechanism motion and flight behavior through the relevant in-game checks.

The [v0.7.8 source tag](https://github.com/EEEureka/sp2-build-assistant/tree/v0.7.8) contains the versioned product sources. `release-sources.json` records the validated source inputs and artifact hashes. Packaging wrappers use portable paths and include user-facing documentation.
