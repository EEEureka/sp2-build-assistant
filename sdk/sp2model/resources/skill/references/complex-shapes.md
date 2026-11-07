# Complex shapes, selection and symmetry (0.2)

Use `sp2model designer selection` for the player's primary selected part. Use `shape get --id ID` for current configuration and related wing controls or neighbouring fuselage sections. Use `shape schema --family fuselage|wing|controlSurface` for exact fields and limits. `knowledge complex --family FAMILY` provides versioned native catalog and serializer evidence for 11 families; inventory fields are not a writable allowlist. Unmapped parts return grouped native state and property metadata.

All examples below are operation objects inside the existing guarded `batch apply` envelope. Shortcut commands (such as `sp2model shape update --input edit.json`) use the same identity/requestId with a singular `operation` object instead of `operations`.

```json
{"kind":"shape.update","partId":123,"patch":{"length":4,"sections":[{"index":0,"width":1.2,"height":1.5,"cornerRadius":{"topLeft":0.2},"cornerStretch":{"topLeft":false},"edgeCurvature":{"top":0.25},"cutting":{"top":0.64,"bottom":0,"left":null,"right":null},"smoothing":true,"syncAdjacent":true}]}}
```

Directions are part-local +Y top, +X right. Length changes the absolute Z separation while retaining lateral offsets and the sign of Z; full offset and length are mutually exclusive. Sections are indexed patches, not replacement lists. Corner radius is metres unless that corner stretches, when it is dimensionless (0..1); inspect cornerRadiusNativeMax for the geometry-specific limit. Cutting uses fractions, null=automatic; opposite sides must sum <1. Legacy thickness units cannot be written as thicknessFraction. Curved intermediate sections have no cutting/smoothing/sync; cone tips have cutting only. Enabled adjacent end faces receive section patches when both faces permit sync. `fuselage.match` with partId and sectionIndex explicitly copies the connected neighbour's section and enables smoothing; it does not move the part or propagate a symmetry group.

Before connecting a manually dimensioned fuselage/cone, set `autoResize:false` explicitly. Templates can start with it true; shape edits preserve its current value unless patched. When true, native connection callbacks can replace sections and length with neighbour-derived values and align the part, then set it false. This is an exception to the absence of general connection snapping. Read back shape/pose after connecting. Save/AutoRecenter is a separate possible whole-aircraft translation; compare same-revision geometry and relative positions.

```json
{"kind":"shape.update","partId":200,"patch":{"sections":[{"index":0,"chord":3,"airfoil":"NACA2412"},{"index":1,"spanPosition":4,"chord":1.5,"offset":-0.5,"airfoil":"NACA0012","bendDegrees":5}],"wingtip":{"stretch":1.2}}}
{"kind":"wing.control.add","wingPartId":200,"style":"StandardFlap","temporaryId":"aileron","patch":{"spanRange":[1,3],"chordFraction":[0.25,0.3],"maxDeflectionDegrees":20}}
```

Wing `replaceSections` replaces the complete section list (2..32); use it to add/remove stations. Positions start at zero and strictly increase. Root/tip chord and offset are required; root airfoil is required. Other null airfoil definitions use native interpolation/inheritance, interior null chord/offset values interpolate. The native airfoil parser validates names; do not assume all NACA variants work. `wingtip:null` removes the rounded tip.

Control surfaces are separate parts. Read the wing's controlSurfaces list, edit an existing control with shape.update and delete with part.delete. Add supports StandardFlap, FowlerFlap, BrakeFlap and Slat, automatically creating/connecting the native template. It adds to the specified wing only; add/link peers explicitly. spanRange is metres along the source stations; chordFraction is the fraction of local chord at the two ends (0.05..0.8, or 0.05..0.4 for Slat). Overlap on the same wing edge and requests requiring native clamping are rejected. Spoiler/SplitFlap are inventory/read-only in the typed editor.

DLL 0.4.6 attaches `wing.control.add` to a compatible native wing **surface receiver**, reserving its structural root for the host. The result reports `controlAttachPointId`, `wingAttachPointId`, and `attachmentBasis`. No compatible surface receiver produces an error and batch rollback; it does not fall back to consuming the root. Earlier DLLs could consume a free root if a control was added before connecting the wing to its host, independent of whether the wing was flipped. Read the actual point's `available/seekType/receiveType/surface` before explicit connections; do not trial an already unavailable or incompatible point.

The helper uses a standalone native control-surface template, reported as `templateId` from DLL 0.4.6. It does not inherit paint/materials from the wing or another control. A flap included in a Horizontal Stabilizer template may have different material IDs from a separately added Standard Flap; identical type/style/shape alone does not imply identical appearance. `symmetry.link` links existing parts without copying their settings. Compare current `materialIds` explicitly when appearance matters; analysis captures do not show native paint/materials.

CLI 0.4.1 exposes supported styles and per-style patch fields directly in `commands schema --operation wing.control.add` (and the CLI shortcut schema). `shape.update.patch` contains named family/style branches with bounds, mutually exclusive fields, and nested section keys. Actual-part constraints such as slice count, wing overlap, airfoil parsing and native clamping still require runtime validation. `shape schema --family` takes exactly fuselage, wing or controlSurface; it does not take PartTypeId names. Fuselage has no replaceSections patch; use existing section indices or additional fuselage parts for more segments.

```json
{"kind":"symmetry.link","partIds":[123,124]}
{"kind":"symmetry.enable","partId":123,"enabled":false}
{"kind":"symmetry.unlink","partId":123}
{"kind":"symmetry.create","partId":123}
```

These are alternatives, not a suggested sequence. Link checks native type and mirror/radial transforms. Enable affects the whole group. Unlink removes the group without deleting parts. Create uses the designer's current symmetry mode, creates linked copies, and does not clone connections. shape.update follows enabled groups by default, mirroring local geometry correctly; symmetric:false is a deliberate single-side edit. Raw part.update only propagates when symmetric:true, and does not support raw pose propagation. A symmetry_geometry_mismatch requires inspecting the actual group/plane; do not blindly retry.

After geometric edits check validation.geometryRefreshed and re-read shape/geometry. `sp2model parts geometry --id ID` separates render, collider and editor-cache bounds; `sp2model designer raycast --origin '[x,y,z]' --direction '[x,y,z]'` tests actual part hits. `{"kind":"craft.refresh"}` explicitly rebuilds the open craft through the same guarded transaction. Do not work around stale geometry by editing a saved file. Restart is necessary to load a new DLL, not for normal aircraft edits.
