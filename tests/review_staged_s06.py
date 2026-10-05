"""Audit S06 saved observations; a passing audit does not pass input binding."""
import json
from pathlib import Path

root = Path(__file__).parents[1]
source = Path('D:/codeSpace/sp2_craft_edit/staged-build/S06')
load = lambda n: json.loads((source/n).read_text(encoding='utf-8-sig'))
checks = []
def check(name, result): checks.append({'name': name, 'pass': bool(result)})
def near(a, b, tolerance=1e-5): return len(a)==len(b) and all(abs(x-y)<tolerance for x,y in zip(a,b))
def nodes(part): return {n['element']:n['attributes'] for n in part['state']['children']}

final = load('snapshot-rev19.json')['data']; identity = final['identity']
parts = {p['id']:p for p in final['parts']}
start = {p['id']:p for p in load('parts-list-start.json')['data']['listing']['items']}
check('Only two permanent control surfaces added',len(parts)==16 and set(parts)-set(start)=={15,16})
for i, old in start.items():
    check(f'Original part {i} pose/type/material/group preserved', all(parts[i][k]==old[k] for k in ['type','position','rotationEulerDegrees','scale','materialIds','symmetryId']))
for name in ['connections-rev19.json','symmetry-after-restore.json','centers-rev19.json','capabilities-final.json']:
    check(name+' final identity',load(name)['success'] and load(name)['data']['identity']==identity)
connections = load('connections-rev19.json')['data']['connections']; seen={3}
if isinstance(connections, dict):
    connections=[{k:int(v) if k in ('partA','partB') else [int(i) for i in v.split(',')] for k,v in n['attributes'].items()} for n in connections['children']]
while True:
    extra={p for c in connections if c['partA'] in seen or c['partB'] in seen for p in [c['partA'],c['partB']]}-seen
    if not extra: break
    seen.update(extra)
check('All sixteen parts connected with fifteen edges',seen==set(parts) and len(connections)==15)
def link(a,b,ap,bp):
    return any((c['partA'],c['partB'],c['attachPointsA'],c['attachPointsB']) in [(a,b,[ap],[bp]),(b,a,[bp],[ap])] for c in connections)
check('Wing roots preserved and controls use surface receivers',link(7,1,0,3) and link(8,1,0,5) and link(15,7,0,1) and link(16,8,0,1))
for i, wing in [(15,7),(16,8)]:
    p=load(f'part-{i}-sync-restored20.json')['data']; n=nodes(p['part'])
    check(f'Part {i} final readback is rev19',p['identity']==identity)
    check(f'Part {i} binding remains Pitch: S06 NOT complete',n['InputController.State']['input']=='Pitch' and n['InputController.State']['invert']=='false')
    check(f'Part {i} final range and deflection',n['ControlSurfacePart.State']['range']=='3.5,5.5' and n['ControlSurfacePart.State']['maxDeflection']=='20')
    shp=load(f'shape-{i}-after-link.json')['data']
    check(f'Part {i} rev17 shape matches restored fingerprint',shp['identity']['fingerprint']==identity['fingerprint'] and near(shp['shape']['chordFraction'],[.25,.25]) and shp['shape']['wingPartId']==wing)
    for suffix,revision,value in [('before',17,'20'),('after18',18,'18'),('restored20',19,'20')]:
        data=load(f'part-{i}-sync-{suffix}.json')['data']
        check(f'Part {i} independent sync readback at {revision}',data['identity']['revision']==revision and nodes(data['part'])['ControlSurfacePart.State']['maxDeflection']==value)
groups=load('symmetry-after-restore.json')['data']['groups']
check('All four exact symmetry groups enabled',{g['id']:sorted(p['id'] for p in g['parts']) for g in groups}=={1:[9,11],2:[7,8],3:[10,12],4:[15,16]} and all(p['enabled'] for g in groups for p in g['parts']))
for name in ['batch-4-sync-20-to-18.response.json','batch-5-restore-20.response.json']:
    change=load(name)['data']['actualChanges'][0]
    check(name+' changed only requested pair',change['partId']==15 and change['synchronizedPartIds']==[16] and change['affectedPartIds']==[15,16])
failed=load('batch-2-left-aileron-and-axes.response.json')
check('Input editing failure is real missing metadata',not failed['success'] and failed['error']['code']=='unsupported_property' and 'attribute input' in failed['error']['message'])
check('Failed input edit recovered exact rev16 snapshot',failed['rollbackResult']['restored'] and failed['rollbackResult']['fingerprintIdentical'] and failed['identity']==load('batch-1-add-aileron-right.response.json')['data']['identity'])
check('Parameter round trip restores rev17 fingerprint',identity['fingerprint']==load('batch-3-left-aileron-and-link.response.json')['data']['identity']['fingerprint'])
r=load('geometry-15-after-link.json')['data']['geometry']['renderers'][0]['bounds']
l=load('geometry-16-after-link.json')['data']['geometry']['renderers'][0]['bounds']
check('Control meshes mirror with equal size',near(r['size'],l['size']) and near([-r['center'][0],r['center'][1],r['center'][2]],l['center']))
for prefix,expected in [('R1',[15]),('R2',[16]),('R3',[15,7]),('R4',[16,8]),('R5',[15]),('R6',[7]),('R7',[15]),('R8',[7])]:
    paths=[p for p in source.glob('ray-'+prefix+'-*.json') if not p.name.endswith('-input.json')]
    assert len(paths)==1, paths
    ray=load(paths[0].name)['data']
    check(prefix+' geometry intersection ordering',ray['identity']==identity and [h['partId'] for h in ray['hits']]==expected)
centers=load('centers-rev19.json')['data']
rows=load('centers-rev19-mass-page0.json')['data']['contributors']['items']+load('centers-rev19-mass-page20.json')['data']['contributors']['items']
check('Sixteen unique mass contributors',len(rows)==16 and {r['part']['id'] for r in rows}==set(parts))
total=sum(r['massKg'] for r in rows)
check('Mass reconstructed from contributors',abs(total-centers['centers']['com']['massKg'])<1e-6)
com=[sum(r['massKg']*r['positionWorldMeters'][i] for r in rows)/total for i in range(3)]
check('CoM reconstructed from float-serialized contributor positions',near(com,centers['centers']['com']['positionWorldMeters'],1e-7))
oldcenters=json.loads((source.parent/'S05/centers-final15.json').read_text(encoding='utf-8-sig'))['data']
oldmass={r['part']['id']:r['massKg'] for r in oldcenters['contributors']['items'] if r['metric']=='mass'}
delta={r['part']['id']:r['massKg']-oldmass.get(r['part']['id'],0) for r in rows}
check('Mass changes restricted to wings and new panels',{i for i,v in delta.items() if abs(v)>1e-6}=={7,8,15,16} and delta[7]<0 and delta[8]<0 and delta[15]>0 and delta[16]>0)
check('Lift proxy unchanged with five sources',centers['centers']['col']==oldcenters['centers']['col'] and centers['centers']['col']['sourceCount']==5)
check('No thrust; stability explicitly not assessed',centers['centers']['cot']['reasonCodes']==['no_sources'] and all(v['status']=='not_assessed' for v in centers['assessment'].values()))
for name in ['capture-craft-envelope.json','capture-details-envelope.json']:
    capture=load(name)['data']
    check(name+' final nonstale capture',capture['identity']==identity and capture['complete'] and not capture['staleAtDelivery'])
    check(name+' recommended artifacts exist',all(Path(p).is_file() for p in capture['recommendedImages']))
report={'identity':identity,'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks,
        'stageStatus':'pending_input_binding_fix_0.4.8',
        'boundary':'Evidence audit only; both new panels still use Pitch. Whole-aircraft and both wing detail images opened separately. No flight/control-effectiveness assessment.'}
out=root/'tests/artifacts/staged-build/S06-review/independent-review.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[c for c in checks if not c['pass']]}))
raise SystemExit(any(not c['pass'] for c in checks))
