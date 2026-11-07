# Aircraft mass, lift and thrust centers

English · [简体中文](zh-CN/Centers-Usage.md)

`sp2build craft centers` reads the design's center of mass (CoM), center of lift (CoL) and center of thrust (CoT). It can show contributing parts, compare reports and annotate views from the same sample.

```powershell
sp2build craft centers
sp2build craft centers --detail contributors --metric mass --limit 20
sp2build craft centers --detail contributors --focus selected
sp2build craft centers --images --timeout 120 --output-dir .\centers-view
sp2build commands schema --command craft.centers
```

## Scope and output

| Input | Behavior |
| --- | --- |
| `detail` | `summary` or `contributors`. Both include the craft summary. |
| `metric` | `all`, `mass`, `lift` or `thrust`. Filters the contributor page. |
| `focus` or `focusSelector` | Limits detail to the selection, parts or a supported assembly. Center positions and contribution denominators still use the full sample. |
| `limit` and `offset` | Pagination. Defaults to 20 rows at offset zero. |
| `frame` | World or part frame. Part scale is ignored. Native lift projection still uses world +Y. |
| `images` and `resolution` | Reads geometry and centers together and generates annotated side, top and front views. Image dimensions range from 384 to 1024 pixels. |
| `baseline` | Compares with a full report file up to 8 MiB. |
| `craftSessionId` and `expectedRevision` | Optional guards. The tool records the identity at sampling time. |

```json
{
  "detail": "contributors",
  "metric": "mass",
  "focusSelector": {"kind": "parts", "partIds": [214, 215]},
  "frame": {"kind": "part", "partId": 1},
  "images": true
}
```

## Interpret the report

- `centers.com`, `centers.col` and `centers.cot` contain positions in meters, methods and coverage marked `valid`, `partial` or `unavailable`. An unavailable position is null.
- `relations.colFromCom`, `cotFromCom` and `cotFromCol` report the first position minus the second. They include XYZ offsets and straight-line distance. Confirm the actual craft orientation before interpreting forward or aft. The 0.001 m threshold only controls alignment labels.
- `contributors.items` identifies sources, weight, inclusion, exclusions and location. Mass moments are in kg·m. CoT weights use different native formulas by propulsion type, so their sum has no single thrust unit.
- `basis`, `scope`, `warnings` and `assessment` describe the sample and its limits. CoL is a designer position weighted by projected area and lift scale. Test static stability, trim and thrust torque separately.

## Compare an edit and view the sample

```powershell
sp2build craft centers --output before-centers.json
# Apply a scoped edit.
sp2build craft centers --baseline before-centers.json --output after-centers.json
```

Use the full JSON report as the baseline. Check `comparison.status` before reading the differences. Comparable reports include before, after and delta values. A shared translation changes absolute coordinates while preserving relative offsets. A different session, calculation basis or frame can make the reports incomparable.

Open the PNGs in `data.visual.recommendedImages`. The images and center report share a geometry stamp. Review stale or incomplete samples before drawing a conclusion. Red circles mark CoM, blue triangles CoL and yellow diamonds CoT. Green marks focus parts. The manifest records each image's scale.

Add `"overlays":{"centers":true}` to an existing mesh capture. The center calculation retains full craft scope even when the image shows only selected parts. [Mesh inspection](Visual-Usage.md)
