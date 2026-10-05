# Aircraft centers and layout (CLI / loaded DLL 0.4.0+)

Use the global `sp2build` entrypoint. Read the currently open designer craft only.

```powershell
sp2build craft centers
sp2build craft centers --detail contributors --metric mass --limit 20
sp2build craft centers --detail contributors --focus selected
sp2build craft centers --images --timeout 120 --output-dir ./centers-view
sp2build craft centers --output before-centers.json
# After the player's requested guarded edits:
sp2build craft centers --baseline before-centers.json --output after-centers.json
sp2build commands schema --command craft.centers
```

Read `data.centers.com/col/cot`, `data.relations.colFromCom/cotFromCom/cotFromCol`, `basis`, `frame`, `scope`, `warnings`. A relation is the first center minus the second. Positions and offsets use metres in the declared frame. +X/+Y/+Z mean right/up/forward by coordinate convention; verify +Z is the aircraft's nose direction before describing forward/aft on the aircraft. `frame:{kind:part,partId:ID}` uses rigid reference axes, ignoring scale; it does not change the native world +Y lift projection.

Default `detail=summary` deliberately returns `contributors.requested=false`, `returned=0`, and empty `items`, while `total` still counts matching sources. This does not mean the aircraft has no sources. Request rows with `--detail contributors`; `--metric mass|lift|thrust` only filters the metric, and `--contributors` is not a flag. CLI 0.4.5 makes this distinction explicit in help/input/output schema as well.

`status:unavailable` has null position, never a valid origin. `partial` omits unsupported/invalid sources and is not full native marker parity. Modern procedural wings are supported; legacy/unknown Mod wing getters are excluded until verified read-only. Mass uses current LoadedMass in kg; native EmptyMass is not fuel-empty mass. Lift is projected area × LiftScale, not simulated lift or the neutral point. Thrust is a mixture of native scalar weights; propeller/legacy weights are proxies, not universally newtons. CoT-to-CoM distance is not the thrust line moment arm. Never infer thrust-to-weight, torque, trim, static margin, static/dynamic stability, or hover feasibility solely from these centers. Assessments explicitly remain not_assessed.

Contributors carry `part:{id,type,typeName,name}`, sourceId and inclusion reasons. `massFraction/nativeWeightFraction` use whole-aircraft covered totals even with focus or pagination. `massMomentAboutComKgM` is kg·m, not torque. Sorting is fixed: metric mass/lift/thrust, then decreasing mass-moment magnitude or native weight. Follow nextOffset; a page is not the complete contribution set. `focus:selected` with no current selection returns empty focus rows but retains whole-aircraft centers.

For game 0.7.8.103, DLL 0.4.4 warns `native_flipped_wing_com_y_zeroed` when connected flipped procedural wings are present, with affected part IDs. Native WingBuilder uses `y -= y` for their local mass center, setting that component to zero. Geometrically mirrored wings can therefore have different world vertical mass centers. These reports preserve the game's actual mass calculation; do not replace CoM with a visually inferred mirror or claim that the plugin fixes native physics. The warning is version-specific, not a conclusion about other game versions.

For explicit focus, use a JSON request with `focusSelector:{kind:parts,partIds:[...]}` or `{kind:assembly,rootPartId:ID}` instead of `focus`. Native assembly means procedural missile children or wing controls; arbitrary connected components are not ownership. Focus highlights/filtering do not alter centers. Whole-aircraft scope follows native connected sources plus the documented legacy VTOL hierarchy exception; inspect mixed propulsion and scope warnings.

With images, open `data.visual.recommendedImages` through the harness's actual image reader. The gray mesh, green focus, COM circle, COL triangle and COT diamond share real coordinates. Overlay leaders are not structural connections. Dashed center lines are projected separations; signed XYZ labels are frame vectors. Detail images can have different pixelsPerMetre. Check manifest centersDetailStatus and any omissions, staleAtDelivery, identity and geometryStamp. ID/raw images and visual pick continue to identify mesh surfaces behind annotations. Existing visual capture accepts `overlays:{centers:true}` and returns data.centersReport, still whole-aircraft even for subset visual groups.

Baseline must be the full successful report saved to the --output file, not stdout's saved-output receipt, an async job receipt, or an aircraft XML. CLI loads at most 8 MiB and sends data in the same task; --async and operation wait/result work, including nested image downloads. If status is not_comparable, report its reason and use current data; do not align recycled reference IDs or cross-session crafts yourself. Use comparison.relativeChanges (including distanceChangeMeters) for geometry changes, avoiding false improvement from common aircraft translation. Partial sources remain partial in comparisons. Current images contain only current centers. Observed deltas are not automatic causal attribution or stability scores.

CLI/DLL installation does not reload the running game. Old loaded DLLs reject centers before submission. No game launch or restart is implied by a centers query. If images hit render/no-geometry limits, request numeric data separately. First release 0.4.0 has offline verification; native in-game parity and no-side-effect checks remain pending in its verification record.
