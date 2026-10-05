# Native designer screenshots (DLL 0.4.11+)

Use `sp2build designer capture` for the actual designer scene, native paint/materials and background, or to investigate a discrepancy between the player's view and isolated mesh analysis. It renders with the native designer scene camera; it does not composite screen-space menus/cursor or the separate gizmo camera. It includes all scene objects visible to that camera, including extra aircraft instances. An inconsistent `sceneIntegrity` is reported but does not block this diagnostic capture.

Native scene helpers such as selection outlines and window cutting volumes can remain in the image. From 0.5.0, includesGizmos=null and gizmoPolicy describe this unclassified presence; null does not mean a clean modeling view. For image comparisons, keep selection/helper visibility consistent or exclude those overlays from the measurement ROI.

Use `visual capture` for isolated groups, analysis colors, ID picking and center overlays. `visual pick` cannot identify pixels in a native screenshot. For full desktop UI evidence use the harness's window screenshot capability if available.

For mechanical alignment, cross-check geometry and live attach points rather than judging screenshot pixels alone. DLL 0.4.11+ reports `positionSource` and `definitionLocalPosition`; `localPosition/worldPosition` prefer live handles because dynamic gearbox/exhaust handles may move independently of their native definitions. A definition fallback is explicitly marked and does not prove current physical alignment.

1. Read `designer status` for the **loaded** DLL version and current identity. Write a UTF-8 request file with `craftSessionId` and preferably `expectedRevision`.
2. Run `sp2build designer capture --input camera.json --output-dir inspection --json`. Open the returned `recommendedImages` with the harness image tool. They include every requested view. `overview.png` is a copy of the first view, not a multi-view contact sheet.
3. Check `cameraRestored`, `sceneIntegrity`, and each `views[].camera` in the output/manifest. The camera pose/settings are temporarily used in a synchronous render and restored before the command completes; capture does not add an undo step or edit the aircraft. Switching projection or framing does not persist a player camera change.

Current player viewpoint (omitting views has the same effect):

```json
{"craftSessionId":"SESSION","expectedRevision":12,"views":["current"]}
```

Three orthographic directions and a custom perspective view:

```json
{
  "craftSessionId":"SESSION",
  "expectedRevision":12,
  "views":[
    {"view":"front","projection":"orthographic"},
    {"view":"right","projection":"orthographic"},
    {"view":"top","projection":"orthographic"},
    {"name":"wing-oblique","view":"custom","projection":"perspective",
     "azimuthDegrees":45,"elevationDegrees":25,"fieldOfViewDegrees":45}
  ],
  "resolution":{"width":1280,"height":800}
}
```

Named directions are `front/back/right/left/top/bottom/isometric` in Unity world axes. Front places the camera on +Z looking toward −Z; right is +X; top is +Y with +Z at the top of the image. They do not infer the aircraft's nose direction. Custom azimuth 0 is +Z, +90 is +X; positive elevation looks from above. Elevation is −89.9..89.9 degrees; exact vertical uses top/bottom. Optional roll is −180..180 degrees.

Named/custom views auto-fit all current craft parts. `focusPartIds:[31,32,33,34,35,36,37]` frames a subset **without hiding** other parts or the surrounding scene. Optional per-view `target:[x,y,z]` is in world metres, `distance` is metres, `fieldOfViewDegrees` is vertical perspective FOV, and `orthographicSize` is orthographic half-height in metres. Explicit target/distance/angles are not accepted for `view:current`; choose named/custom instead. Current view retains its pose when only projection is overridden.

For comparisons use identical explicit target, angles, distance and FOV (perspective), or identical target, angles and orthographicSize (orthographic), plus resolution. Auto-fit may change image scale; do not infer physical size from raw pixels. A later native recenter changes world coordinates: re-read poses and use relative offsets.

Omitted resolution preserves the current viewport aspect with the longest edge at most 1280 px. Explicit resolution requires both width and height, each 128..2048. Up to 8 distinct named views and 16 million pixels including the overview copy are allowed. Files share the visual artifact cache (15 minutes, 3 captures, 192 MiB); downloaded files persist. Use `commands schema --command designer.capture` for complete input/output fields. New CLI with an old running DLL returns `unsupported_bridge_feature` before submission.
