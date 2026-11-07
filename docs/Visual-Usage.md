# Mesh inspection and analysis images

English · [简体中文](zh-CN/Visual-Usage.md)

Use `visual capture` to inspect native mesh geometry in analysis colors and map image pixels to parts. For paint, decals, glass and game lighting, use [native screenshots](Designer-Screenshots.md).

## Capture parts at a common scale

```powershell
sp2build designer status
sp2build designer selection
sp2build visual capture --craft-session-id SESSION --output-dir .\inspection --timeout 90
sp2build visual resolve --input scope.json
sp2build commands schema --command visual.capture
```

With no groups, the tool captures the current selection. Supply a request file to compare several targets in the same frame. Replace the session, revision and IDs with current values.

```json
{
  "craftSessionId": "SESSION",
  "expectedRevision": 12,
  "groups": [
    {"name": "left", "selector": {"kind": "parts", "partIds": [18, 19]}},
    {"name": "right", "selector": {"kind": "parts", "partIds": [20, 21]}}
  ],
  "views": ["front", "right", "top", "isometric"],
  "resolution": {"width": 640, "height": 640},
  "frame": {"kind": "world"},
  "details": "perGroup"
}
```

```powershell
sp2build visual capture --input capture.json --output-dir .\inspection --timeout 90
```

| Selector | Scope |
| --- | --- |
| `parts` with `partIds` | Exact IDs. List required mirror or connected parts explicitly. |
| `selected` | The part selected at execution time. |
| `craft` | The full craft, including disconnected parts. |
| `assembly` with `rootPartId` | A supported native assembly, such as a wing and its control surfaces. |
| `branch` with `rootPartId` and `stopConnectionKeys` | Connected region with explicit edges treated as boundaries. |
| `neighborhood` with `rootPartId` and `hops` | A connection graph neighborhood with 0 to 10 hops. |

The scope supports up to eight named groups and 2048 parts. Use `includeHidden` to request readable hidden geometry. Detail views may use a different scale from the joint views.

## Frames and images

Use world meters or `{"kind":"part","partId":19}`. A part frame uses the part's position and rotation independently of scale. Front looks along −Z, right along −X, and top along −Y with +Z toward the top. A custom view such as `{"name":"oblique","direction":[-1,-1,-2],"up":[0,1,0]}` uses a viewing direction and a nonparallel up vector.

Supply up to eight distinct views. The defaults are front, right, top and isometric at 640 × 640 each. Explicit image dimensions range from 128 to 1024 pixels per side.

| File | Use |
| --- | --- |
| `overview.png` | Joint overview across the requested views. |
| `front.png` and other named views | Labeled single views with axes and scale. |
| `front.raw.png` and equivalents | Analysis colors without labels. |
| `front.ids.png` and equivalents | Pixel IDs for programmatic part lookup. |
| `g1-front.png` and equivalents | Group detail images, when requested. |
| `manifest.json` | Identity, transforms, coverage, projections, exclusions and hashes. |

Open the PNGs in `recommendedImages`. The CLI downloads and verifies the files. Use `--output-dir` to choose a folder. Pick from a named single view using zero-based coordinates from the top-left corner. A background pixel yields a null ID, and an occluded or subpixel part can be present with zero visible pixels.

```powershell
sp2build visual pick --capture-id CAPTURE_ID --view top --x 320 --y 240
```

Check the live craft identity before editing a part found in an earlier capture.

## Freshness and budgets

```powershell
sp2build visual capture --input capture.json --async
sp2build operation wait --id OPERATION_ID --output-dir .\inspection --timeout 90
```

Keep the operation ID on timeout. Check `geometryStamp`, `complete`, `exclusions` and `staleAtDelivery`, and capture again after editing. The game cache is limited to 15 minutes, three packages or 192 MiB. Downloaded files remain on disk.

A capture has limits of 1.2 million vertices, 500,000 triangles, 16 million output pixels and a 45-second rendering budget. Narrow the scope or reduce resolution, views or group details when needed. The manifest reports unreadable geometry and invalid triangles. Use geometry queries and in-game tests for collision clearance and attachment behavior.

Add `"overlays":{"centers":true}` to a request to show the full craft's mass, lift and thrust markers. [Aircraft centers](Centers-Usage.md)
