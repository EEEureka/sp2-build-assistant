# SP2 Build Assistant

English · [简体中文](README.zh-CN.md)

SP2 Build Assistant gives AI agents a native interface to the **SimplePlanes 2 aircraft designer on Windows**. You describe the aircraft or the change you want. Your agent inspects the open design, builds or revises it in the game, and reports what it measured so you can review the result.

## How an agent uses it

1. **Set up the agent.** Install the BepInEx plugin and its matching command-line tools, then give your local agent the bundled `sp2-build-assistant` skill. The skill tells the agent how to inspect, edit and verify a design.
2. **Open a craft and describe the goal.** Start the game, open a craft or a working copy in the designer, and tell the agent what to build, what to preserve, and how you will judge the result.
3. **Let the agent build in the designer.** The agent calls `sp2build` or the newer `sp2model` entry point. The in-game plugin reads and edits the craft through native designer APIs and returns structured results for the agent to inspect.
4. **Review the result.** Ask for matching before-and-after views, dimensions and a change summary. The agent can revise a local area and check it again. You review the design and test its behavior in the game.

> Refine the join between the two fuselage sections in the open aircraft. Keep the windows and the rest of the fuselage in place. Measure the seam, make a local edit, then show the same side view and report the remaining gap.

## What the agent can do

- **Understand the open design.** Read parts, geometry, positions, attachment points, connections, materials, and control bindings. Search the game's part catalog and check which properties the selected parts support.
- **Build and refine assemblies.** Add, position, mirror, connect and edit parts. Shape fuselage sections and wings, work with control surfaces, and adjust supported materials and mechanisms in scoped edits.
- **Configure aircraft logic.** Inspect variables and part outputs, edit supported bindings, and check Funky Trees expressions before in-game testing.
- **Verify and iterate.** Capture native designer views, inspect meshes and cross-sections, measure gaps and seams, compare checkpoints, and recover from an unsuccessful edit. Read the designer's mass, lift and thrust centers to review layout.

## Get started

1. [Download v0.7.8](https://github.com/EEEureka/sp2-build-assistant/releases/tag/v0.7.8) and [install the SDK and plugin](docs/SDK-0.7.8.md)
2. [Run your first agent-assisted build task](docs/SDK-0.7.8.md#run-a-modeling-task)
3. Read the API and workflow references included in the release package.

For specific workflows, see [precision editing](docs/Precision-Workflow.md), [native screenshots](docs/Designer-Screenshots.md), [mesh inspection](docs/Visual-Usage.md), and [aircraft centers](docs/Centers-Usage.md).

The latest release is **0.7.8**, with plugin 0.7.8 and Python SDK 0.7.8a1. The release includes the complete Windows package and its SHA-256 file. [Release notes](docs/Release-0.7.8.md)

Versioned product sources are available under the [v0.7.8 tag](https://github.com/EEEureka/sp2-build-assistant/tree/v0.7.8). The [0.5.0 CLI documentation](docs/Installation.md) remains available for existing installations.
