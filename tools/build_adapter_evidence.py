"""Index exact native-reference evidence without certifying untested types."""
import json,re
from pathlib import Path

project=Path(__file__).resolve().parents[1]
root=project/'tests/artifacts/precision-0.5.0'
source=(project/'bridge/NativePropertyAdapter.cs').read_text(encoding='utf-8').split('internal static void Configure')[0]
required=[f'{family}[0].{member.lstrip("_")}' for family,members in re.findall(r'\["([\w]+)"\]="([^"]+)"',source) for member in members.split()]
fields={key:{'propertyId':key,'positiveCases':[],'negativeCases':[]} for key in required}
runs=['dev19-native-field-matrix','dev20-complex-field-matrix','dev20-integer-field-retest-b',
      'dev21-complex-retest','dev21-gear-style-matrix']
run_reports=[]
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def rel(path):return str(path.relative_to(project)).replace('\\','/')
for name in runs:
    folder=root/name;report=read(folder/'checks.json');checks=report['checks']
    run_reports.append({'run':name,'checks':len(checks),'passed':sum(c['status']=='pass' for c in checks),
        'failures':[c['check'] for c in checks if c['status']!='pass'],'evidence':rel(folder/'checks.json')})
    for inp in sorted(folder.glob('*-public.input.json')):
        tag=inp.name.removesuffix('-public.input.json')
        matches=[c for c in checks if c['check'].startswith(tag+' ')]
        if tag=='mixed':matches=[c for c in checks if c['check']=='style plus size patch binds replacement modifier']
        if not matches or any(c['status']!='pass' for c in matches):continue
        actual=folder/(tag+'-actual.json');target=folder/(tag+'-target.json')
        if not actual.exists() or not target.exists():continue
        parts={p['id']:p['type'] for p in read(actual)['data']['parts']}
        request=read(inp)
        for op in request['operations']:
            if op['kind']!='properties.set':continue
            for key,value in op['patch'].items():
                if key not in fields:continue
                fields[key]['positiveCases'].append({'run':name,'case':tag,'partType':parts[op['partId']],
                    'value':value,'checks':[c['check'] for c in matches],
                    'evidence':[rel(inp),rel(target),rel(actual),rel(folder/'checks.json')]})
negative=root/'dev20-field-rejections';denominator=read(negative/'denominator.json');checks=read(negative/'checks.json')['checks']
for i,row in enumerate(denominator):
    key=row['propertyId'];prefix=f'f{i:03}-'
    fields[key]['negativeCases']=[c['check'] for c in checks if c['status']=='pass' and
        (c['check'].startswith(prefix) or c['check']==key+' absent modifier rejected')]
    fields[key]['negativeEvidence']=rel(negative/'checks.json')
catalog=read(root/'dev7-catalog/coverage.json')
multiple=[]
for template in catalog['entries']:
    if not template['success']:continue
    for part in template['parts']:
        for field in part['fields']:
            match=re.search(r'\[(\d+)\]',field['propertyId'])
            if field.get('writeOperation')=='properties.set' and match and int(match[1])>0:
                multiple.append({'templateId':template['template']['id'],'partType':part['partType'],'propertyId':field['propertyId']})
report={'status':'representative_adapter_matrix_executed','gameVersion':catalog['gameVersion'],
    'requiredAdapterFields':len(fields),'positiveCovered':sum(bool(x['positiveCases']) for x in fields.values()),
    'negativeCovered':sum(bool(x['negativeCases']) for x in fields.values()),
    'scope':'Each allowlisted adapter field has exact native-reference and public-CLI evidence on the listed representative fixtures. Not every catalog type, dynamic combination, resource image or animation trajectory.',
    'omissionEvidence':'Whole-aircraft target/actual comparisons cover unpatched fields as well as the requested field. Individual tests retain full XML and recovery checks.',
    'nativeReference':'Actual native property panel callbacks, Overload panel, or pose-tool Done callback in a real game. Does not substitute for mouse hit-testing or slider quantization.',
    'multipleModifierInstances':{'catalogPositiveCandidates':multiple,'positiveStatus':'not_applicable_to_sampled_native_catalog' if not multiple else 'requires_review',
        'catalogEvidence':rel(root/'dev7-catalog/coverage.json'),'catalogRegistryVersion':'historical dev7 sample; exact game version above',
        'negativeStatus':'index 99 rejected for all discovered index-zero adapter fields'},
    'fullyCertifiedCatalogTypePropertyPairs':0,'runs':run_reports,'fields':list(fields.values())}
sync_runs=['dev21-gear-modifier-symmetry','dev22-gear-modifier-symmetry']
report['modifierSymmetryRegression']=[{'run':name,'evidence':rel(root/name/'checks.json'),
    'checks':len(read(root/name/'checks.json')['checks']),
    'failures':[c['check'] for c in read(root/name/'checks.json')['checks'] if c['status']!='pass']} for name in sync_runs]
assert report['requiredAdapterFields']==report['positiveCovered']==report['negativeCovered'],report
out=project/'knowledge/native-adapter-evidence.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('fields','runs')},ensure_ascii=False,indent=2))
