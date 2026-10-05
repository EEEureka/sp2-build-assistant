"""Check real 0.4.4 S03 stale-cache and propagation readbacks, offline."""
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

root=Path(__file__).parents[1]
source=Path('D:/codeSpace/sp2_craft_edit/staged-build/S03/retest-0.4.4/stale-segment2')
load=lambda name:json.loads((source/name).read_text(encoding='utf-8-sig'))
checks=[]
def check(name,value):checks.append({'name':name,'pass':bool(value)})
def near(a,b,tol=1e-5):return len(a)==len(b) and all(abs(x-y)<tol for x,y in zip(a,b))
spec=importlib.util.spec_from_file_location('runtime_contracts',root/'cli/contracts.py')
contracts=importlib.util.module_from_spec(spec);spec.loader.exec_module(contracts)
for name,cmd in [('symmetry-read1.json','symmetry.get'),('symmetry-read2-before-create.json','symmetry.get'),('part-8.json','parts.get'),('centers-connected.json','craft.centers'),('batch-create-first.response.json','batch.apply')]:
    j=load(name);check(name+' schema',not list(Draft202012Validator(contracts.output_schema(cmd)).iter_errors(j)))
before=load('symmetry-read1.json')['data']; second=load('symmetry-read2-before-create.json')['data']; config=second['configuration']
check('Stale cache observed twice without query mutation',before==second and config['nativeCacheStale'])
check('Effective plane differs from native old plane',abs(config['mirrorPlaneDistance']-config['nativeCachedFrame']['mirrorPlaneDistance'])>2)
original=load('part-7.json')['data']['part']; peer=load('part-8.json')['data']['part']
n=config['mirrorPlaneNormal']; p=original['position']; dot=sum(a*b for a,b in zip(n,p))+config['mirrorPlaneDistance']
expected=[x-2*dot*y for x,y in zip(p,n)]
check('First copy reflects current plane',near(peer['position'],expected))
old_dot=sum(a*b for a,b in zip(n,p))+config['nativeCachedFrame']['mirrorPlaneDistance']
check('First copy does not reflect stale plane',not near(peer['position'],[x-2*old_dot*y for x,y in zip(p,n)],.1))
request=load('batch-create-first.json'); response=load('batch-create-first.response.json')
check('No preparatory mutation in first create batch',len(request['operations'])==1 and request['operations'][0]['kind']=='symmetry.create' and request['expectedRevision']==second['identity']['revision'])
check('Creation succeeded with one commit',response['success'] and response['data']['identity']['revision']==request['expectedRevision']+1)
after=load('symmetry-after-create.json')['data']
check('Write refreshed native cache',not after['configuration']['nativeCacheStale'] and near(after['configuration']['radialOrigin'],config['radialOrigin']))
for phase,values in [('t1',(3.15,3.15)),('t1b',(3.1,3.1)),('t2b',(3.15,3.1)),('t2c',(3.1,3.1))]:
    rows=[load(f'shape-{i}-{phase}.json')['data'] for i in [7,8]]
    check(phase+' independent shapes share identity',rows[0]['identity']==rows[1]['identity'])
    check(phase+' independent root chords',near([r['shape']['configuration']['sections'][0]['chord'] for r in rows],values))
for name,enabled in [('symmetry-t2-disabled.json',False),('symmetry-t3-reenabled.json',True)]:
    groups=load(name)['data']['groups']
    check(name+' independently read enabled state',len(groups)==1 and {p['id'] for p in groups[0]['parts']}=={7,8} and all(p['enabled']==enabled for p in groups[0]['parts']))
centers=load('centers-connected.json')['data']
check('Native CoM caveat identifies flipped wing',any(w['code']=='native_flipped_wing_com_y_zeroed' and w['relatedPartIds']==[8] for w in centers['warnings']))
snapshot=load('snapshot-connected.json')['data']; cs=load('connections-connected.json')['data']['connections']; seen={3}
while True:
    added={n for c in cs if c['partA'] in seen or c['partB'] in seen for n in [c['partA'],c['partB']]}-seen
    if not added:break
    seen.update(added)
check('Explicit connection restores 8-part connected craft',snapshot['partCount']==8 and len(cs)==7 and seen=={p['id'] for p in snapshot['parts']})
rollback=load('rollback-response.json')
finalsource=source.parent/'after-rollback'
final=json.loads((finalsource/'snapshot.json').read_text(encoding='utf-8-sig'))['data']
initial=json.loads((source.parent/'snapshot-rev1.json').read_text(encoding='utf-8-sig'))['data']
check('Rollback independently restores full initial fingerprint',rollback['success'] and rollback['data']['validation']['restorationVerified'] and final['identity']['fingerprint']==initial['identity']['fingerprint'])
check('Rollback retains original eight-part poses and types',final['partCount']==8 and {p['id']:(p['type'],p['position'],p['rotationEulerDegrees'],p['symmetryId']) for p in final['parts']}=={p['id']:(p['type'],p['position'],p['rotationEulerDegrees'],p['symmetryId']) for p in initial['parts']})
for path in sorted(finalsource.glob('*.json')):
    j=json.loads(path.read_text(encoding='utf-8-sig'))
    if j.get('success') is not True:continue
    check(path.name+' final same revision',j['data'].get('identity')==final['identity'])
report={'source':str(source),'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks,'boundary':'Real loaded 0.4.4 readbacks including final rollback; no flight or stability verification. Final overview opened separately.'}
out=root/'tests/artifacts/staged-build/S03-review/runtime-0.4.4-review.json';out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[c for c in checks if not c['pass']]}))
raise SystemExit(any(not c['pass'] for c in checks))
