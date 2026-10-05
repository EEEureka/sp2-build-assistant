"""Build an honest union of ALL sampled template fields, with evidence links.

Discovery denominator is independent of the writable adapter allowlist.
Native UI parity for one fixture does not certify an entire family/type.
"""
import collections
import json
import sys
from pathlib import Path

project=Path(__file__).resolve().parents[1]
root=project/'tests/artifacts/precision-0.5.0'
audit=root/(sys.argv[1] if len(sys.argv)>1 else 'dev7-catalog')
source=json.loads((audit/'coverage.json').read_text(encoding='utf-8-sig'))
negative=json.loads((root/'dev5-negative-properties/checks.json').read_text(encoding='utf-8-sig'))
negative_fields=json.loads((root/'dev5-negative-properties/denominator.json').read_text(encoding='utf-8-sig'))
negative_parts={p['id']:p['type'] for p in json.loads((root/'dev5-negative-properties/baseline.json').read_text(encoding='utf-8-sig'))['data']['parts']}
negative_types={f['propertyId']:negative_parts[f['partId']] for f in negative_fields}
negative_by_field=collections.defaultdict(list)
for check in negative['checks']:
    field=check['check'].split(' ')[0]
    if check['status']=='pass' and '[' in field:
        negative_by_field[field].append(check['check'])
window_ui={'ProceduralWindow[0].'+x for x in ('height','depth','topWidth','topOffset','bottomWidth','bottomOffset','cornerRadius','penetration','hideGlass')}
window_ui.add('Transparency[0].opacity')

# Attach exact-field historical evidence, never infer family-wide coverage from
# a passing fixture. Keep rejected/partial runs visible and separate from pass.
ui_by_field=collections.defaultdict(list)
ui_runs=[]
for observed in sorted(root.glob('*/observed-ui-changes.json')):
    folder=observed.parent
    files=[folder/'checks.json', folder/'native-target.json']
    if not all(f.exists() for f in files):continue
    run=json.loads(files[0].read_text(encoding='utf-8-sig'))
    checks=run.get('checks',[])
    target=json.loads(files[1].read_text(encoding='utf-8-sig'))['data']
    part_types={str(p['id']):p['type'] for p in target['parts']}
    observed_changes=json.loads(observed.read_text(encoding='utf-8-sig'))
    if 'target' in observed_changes:
        input_file=folder/'native-properties.input.json'
        if not input_file.exists():continue
        pid=str(json.loads(input_file.read_text(encoding='utf-8-sig'))['id'])
        patches={pid:observed_changes['target']}
    else:patches=observed_changes
    evidence=[str(f.relative_to(project)).replace('\\','/') for f in [observed,*files]]
    image_audit=folder/'independent-image-state-audit.json'
    images_equal=None
    if image_audit.exists():
        image_data=json.loads(image_audit.read_text(encoding='utf-8-sig'))
        images_equal=bool(image_data.get('imagePairs')) and all(p['identicalPixels'] for p in image_data['imagePairs'])
        evidence.append(str(image_audit.relative_to(project)).replace('\\','/'))
    passed=bool(checks) and all(c['status']=='pass' for c in checks)
    # Some runs deliberately retain exact-XML failures alongside a later
    # independent audit. Do not silently promote those reports here.
    entry={'run':folder.name,'status':'passed_recorded_checks' if passed else 'partial_or_failed_recorded_checks',
        'pixelIdentical':images_equal,'manualImageInspection':'see docs/Execution-0.5.0.md',
        'scope':'Only the listed native UI values on this fixture; not all bounds, conditions, or instances.',
        'evidence':evidence}
    ui_runs.append(entry)
    for pid,patch in patches.items():
        for key,value in patch.items():
            ui_by_field[(part_types[pid],key)].append({**entry,'nativeTargetValue':value})
types={};template_members=0;all_rows=0;errors=[];version=None
for entry in source['entries']:
    if not entry['success']:
        errors.append({'templateId':entry['template']['id'],'error':entry['error']});continue
    for part in entry['parts']:
        template_members+=1;all_rows+=len(part['fields'])
        assert part['offset']==0 and len(part['fields'])==part['total'], 'Page the missing fields before building coverage'
        rows=types.setdefault(part['partType'],{})
        for field in part['fields']:
            key=field['propertyId']
            description={k:field[k] for k in ('propertyId','family','label','type','unit','source','editability','writeOperation','condition','limits','verification','reason') if k in field}
            row=rows.setdefault(key,{'propertyId':key,'variants':[],'templateIds':set()})
            if description not in row['variants']:row['variants'].append(description)
            row['templateIds'].add(entry['template']['id'])
for name,rows in types.items():
    for key,row in rows.items():
        row['templateIds']=sorted(row['templateIds'])
        checks=negative_by_field.get(key,[]) if negative_types.get(key)==name else []
        row['acceptance']={'status':'pending_full_matrix','negativeChecks':checks,
            'negativeEvidence':'tests/artifacts/precision-0.5.0/dev5-negative-properties/checks.json' if checks else None,
            'nativeUiParity':None,'nativeUiFieldRuns':ui_by_field.get((name,key),[])}
        if name=='ModifierWindow-1' and key in window_ui:
            row['acceptance']['nativeUiParity']={
                'status':'passed_one_fixture','scope':'Single rounded body, one window; common values and hideGlass. Bounds, two shells, targets and symmetry remain pending.',
                'evidence':['tests/artifacts/precision-0.5.0/dev7-window-cli-parity-verify/independent-parity.json',
                            'tests/artifacts/precision-0.5.0/dev7-window-hide-parity/independent-image-audit.json']}
sample=json.loads((audit/'template-000.json').read_text(encoding='utf-8-sig'))['data']
unique_rows=[r for rs in types.values() for r in rs.values()]
report={'gameVersion':source['gameVersion'],'registryVersion':sample['registryVersion'],'status':'development_pending_native_acceptance',
 'coveragePolicy':'Discovery and partial evidence only; no field is fully certified by this file. Query live properties.describe for active constraints.',
 'denominator':'Union of (partType, propertyId) across every member of every runtime catalog template; UI fields plus serialized attributes plus overload metadata. XML aliases are counted separately. Dynamic hidden widget fields not exposed by these sources are excluded and not declared supported.',
 'discoveredTemplates':source['templateCount'],'templateMembers':template_members,'templateFieldRows':all_rows,'discoveredTypes':len(types),'uniqueTypePropertyPairs':len(unique_rows),
 'editabilityCounts':dict(collections.Counter('|'.join(sorted(set(v['editability'] for v in row['variants']))) for row in unique_rows)),
 'nativeUiCommonValueTypePropertyPairs':sum(row['acceptance']['nativeUiParity'] is not None or any(e['status']=='passed_recorded_checks' for e in row['acceptance']['nativeUiFieldRuns']) for row in unique_rows),
 'nativeUiRunIndex':ui_runs,
 'fullyCertifiedTypePropertyPairs':0,'errors':errors,
 'representativeAdapterEvidence':'native-adapter-evidence.json',
 'types':{name:{'fields':list(rows.values())} for name,rows in sorted(types.items())}}
destination=project/'knowledge/editable-coverage.json'
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='types'},ensure_ascii=False,indent=2))
