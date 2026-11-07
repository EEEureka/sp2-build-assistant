# Native designer screenshots

English · [简体中文](zh-CN/Designer-Screenshots.md)

`sp2build designer capture` renders a PNG through the game's native designer camera. It shows the native model, materials, lighting and background. It restores the camera after capture and leaves the craft and undo history intact.

| What you want to see | Use |
| --- | --- |
| The scene, native materials or a scene integrity problem | `designer capture` |
| A part or assembly in analysis colors, with pixel-to-part picking | [Mesh inspection](Visual-Usage.md) |
| Mass, lift and thrust centers on the same sample | [Aircraft centers](Centers-Usage.md) |
| Menus, pointer and UI overlays | Your agent platform's window capture |

Native captures render the main scene camera. They omit the screen UI, pointer and separate gizmo camera. `focusPartIds` changes framing while other geometry remains visible and can still occlude the target. A scene integrity issue may remain visible in the capture.

## Capture current and fixed views

Read the current craft identity and supply it in a UTF-8 request file.

```powershell
sp2build designer status --json
sp2build commands schema --command designer.capture --json
sp2build designer capture --input camera.json --output-dir inspection --json
```

For the current player view, use this request.

```json
{"craftSessionId":"SESSION","expectedRevision":12,"views":["current"]}
```

This request captures three orthographic views and one perspective view.

```json
{
  "craftSessionId":"SESSION",
  "expectedRevision":12,
  "views":[
    {"view":"front","projection":"orthographic"},
    {"view":"right","projection":"orthographic"},
    {"view":"top","projection":"orthographic"},
    {"name":"front-quarter","view":"custom","projection":"perspective",
     "azimuthDegrees":45,"elevationDegrees":25,"fieldOfViewDegrees":45}
  ],
  "resolution":{"width":1280,"height":800}
}
```

## Camera parameters

| Parameter | Meaning |
| --- | --- |
| `view` | `current`, `front`, `back`, `right`, `left`, `top`, `bottom`, `isometric` or `custom` |
| `projection` | `current`, `perspective` or `orthographic`. Defaults to the active projection. |
| `target` | World-space point `[x,y,z]` in meters. Defaults to the framed renderer bounds center. |
| `azimuthDegrees` | Custom view required. 0° is from +Z and +90° is from +X. Range −360° to 360°. |
| `elevationDegrees` | Custom view required. Positive is above the target. Range −89.9° to 89.9°. Use `top` for a vertical top view. |
| `rollDegrees` | Rotation around the viewing direction, −180° to 180°. |
| `distance` | Distance to the target, 0.05 to 10,000 m. Omit for automatic framing. |
| `fieldOfViewDegrees` | Vertical perspective field of view, 5° to 140°. |
| `orthographicSize` | Orthographic half-height, 0.01 to 10,000 m. Omit for automatic framing. |

Preset views use world axes. The front camera is on +Z, the right camera on +X, and the top camera on +Y with +Z toward the top of the image. `current` uses the player's existing pose and accepts no target, distance or angle override.

## Read the result

Open the PNGs listed in `recommendedImages`. The manifest records the capture identity, scene integrity, camera restoration, per-view camera settings and file hashes. Keep the same target, projection, orientation, framing and resolution when comparing edits. Reuse `repeatableViews` and `repeatableResolution` when returned.

A request can contain up to eight named views. Set both width and height when supplying a resolution, from 128 to 2048 pixels per side. The total pixel budget is 16 million, including the overview copy. `overview.png` is a copy of the first view.

The CLI downloads the capture files and checks their SHA-256 hashes. Use `--output-dir` to choose a local folder. Use `--async` and query the existing operation with `operation wait` or `operation result` for longer captures.
