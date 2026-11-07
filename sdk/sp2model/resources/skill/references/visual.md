# Visual inspection from 0.3

For native designer appearance and selectable perspective/orthographic scene views, use [designer screenshots](designer-screenshots.md) with DLL 0.4.11+. This page describes the separate mesh-analysis interface. A scoped mesh image does not prove the whole live scene has only one aircraft.

On DLL 0.3.2+, join manifest/resolve `groups[].groupIndex` to `detailStatus[].groupIndex` and `imageRecommendations[].groupIndex`. All are zero-based. `groups[].index` remains an equal legacy alias and can be used for the same join on 0.3.1. There is no need to infer membership from `g1-` filenames (those use one-based display numbering).

DLL 0.3.1 defaults to `details:"auto"`: retain joint overview and add one detail view for each group too small or occluded in every joint view. `perGroup` requests all detail views; `none` disables them. Check loaded `capabilities.visualInspection.detailModes` before explicitly requesting auto on an older DLL. `recommendedImages` includes overview and useful details, with reasons in `imageRecommendations`. `detailStatus` explicitly reports skipped groups, including `budget_exceeded`; a missing detail is not evidence of missing geometry.

Fit changes across captures: even the same explicit `frame` fixes only the axes, not zoom. Geometry bounds can change `pixelsPerMetre`. Use each view's scale or frame-to-pixel transform to compare physical sizes; never compare raw pixel lengths across captures or separate group views. Manifest `scalePolicy` and `comparisonGuidance` make this explicit. Include nearby mounting parts in the scope when checking fit; an isolated detail cannot prove a connection's placement.

Check `sp2model capabilities` on the loaded DLL first. CLI installation alone does not add the game-side feature. All queries operate on the current open craft. Capture is read-only and does not move the player's camera or change materials, visibility, selection or undo history.

1. Read `sp2model craft snapshot` and `designer selection`. Reuse the current `craftSessionId`; include `expectedRevision` when the result must match that revision.
2. Put the request in UTF-8 JSON and run `sp2model visual capture --input request.json --output-dir inspection --timeout 90`. The CLI creates a unique capture subdirectory; JSON returns absolute `manifestPath` and `recommendedImages`. Without output-dir, files go under `~/.sp2build/captures`.
3. **Open the recommended PNG images using the platform's image/attachment tool.** Read the manifest for precise coordinates and omissions. If the harness/model cannot accept images, explain this and use spatial JSON only; do not say the model has inspected the appearance.
4. Use raw views for unobstructed geometry, detail views for small features, and `sp2model visual pick --capture-id ID --view front --x 320 --y 280` to identify a captured surface. Pixel origin is top-left, zero-based. Pick uses the underlying ID image, ignoring text overlays. Re-read current identity before editing captured part IDs.
5. After editing, capture again. A previous package remains an old immutable snapshot.

Example input (replace IDs and session with current values):

```json
{
  "craftSessionId": "CURRENT_SESSION",
  "expectedRevision": 12,
  "groups": [
    {"name":"left-pod","selector":{"kind":"parts","partIds":[101,102]}},
    {"name":"right-pod","selector":{"kind":"parts","partIds":[201,202]}}
  ],
  "views":["front","right","top","isometric"],
  "resolution":{"width":640,"height":640},
  "frame":{"kind":"world"},
  "details":"perGroup"
}
```

Omit groups to inspect the current selection; when nothing is selected, `selection_empty` is expected. Omission does not select the whole aircraft. Use `"groups":[{"name":"craft","selector":{"kind":"craft"}}]` for a whole-craft capture. An explicit empty array is invalid. `selector.kind` supports:

- `parts`: exact partIds; no automatic symmetry or connected-part expansion.
- `selected`: the player-selected part at execution time; empty selection is an error.
- `craft`: all parts of the current craft, including disconnected ones.
- `assembly`: `rootPartId` for a native procedural missile or wing and its owned components. This is visual membership, not a promise that cascading deletion is safe.
- `branch`: `rootPartId` and nonempty `stopConnectionKeys`. Run `visual resolve` with a simple scope first to obtain exact keys in `connections`; those keys include the attachment identities. Cycles across the cut return `scope_ambiguous`. No actual connection is cut.
- `neighborhood`: `rootPartId` and `hops` from 0 to 10. Connectivity is not physical support.

`visual resolve --input scope.json` accepts session, optional revision, groups and maxParts. Groups must be disjoint. Capture supports up to 8 groups, 2048 parts, 500000 triangles, 1200000 vertices, 8 views, 128..1024 pixels per dimension, and 16 million pixels overall including overview/details. Reduce scope, resolution, details or views if a budget is exceeded; never interpret a failed render as an empty craft.

All overview views share metres-per-pixel and preserve the real group transforms. The front camera looks along frame -Z, right along -X, top along -Y with +Z up. Frame defaults to Unity world metres; `{"kind":"part","partId":ID}` uses that part's translation and rotation without its scale. Custom views use `{"name":"oblique","direction":[-1,-1,-2],"up":[0,1,0]}`. `details:"perGroup"` adds independently fitted group images with explicit scales and centers. Never compare pixel distances across detail images as real separation.

Manifest includes frameToWorldRows, per-part transforms, frameToPixelRows, group bounds/center offsets, per-view visible pixel bounds, ID palette, capture identity and geometryStamp. Matrices are rows multiplying column vectors. Center offsets are mesh-bounds center offsets, not attachment distances or surface clearance. An occluded/subpixel part remains in the inventory. Hidden/unreadable/unsupported meshes appear in exclusions; `complete:false` requires reporting the omitted geometry. `includeHidden:true` includes available hidden meshes without unhiding the designer.

Rendering uses copied actual mesh triangles, opaque two-sided surfaces, group colors and flat analysis lighting. Native textures, transparency/alpha cutouts, shader deformation, paint and decals are not faithfully reproduced. Do not infer material appearance, exact collision clearance or load-bearing support from these images. PNG ID files are exact RGB index encodings, not native part IDs; use the manifest palette or visual.pick.

On wait_timeout retain operationId and use `sp2model operation wait --id ID --output-dir inspection --timeout 90`; it downloads completed visual artifacts too. `--async` returns an operation and does not download until wait/result. Game artifacts last up to 15 minutes, 3 captures or 192 MiB and expire on game exit; downloaded files persist. An expired artifact requires a new capture, while a local download failure can be retried using the original operation. A staleAtDelivery result is a coherent older snapshot, not current evidence.
