"""Independently validate recorded native-camera and dynamic-point results."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
from jsonschema import Draft202012Validator

ROOT=Path(__file__).parents[1]
BASE=ROOT/'tests/artifacts/staged-build/direct-0.4.11'
spec=importlib.util.spec_from_file_location('cli',ROOT/'cli/sp2build.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
checks=[]
def load(name):return json.loads((BASE/name).read_text(encoding='utf-8'))
def check(name,condition,detail=None):checks.append({'name':name,'pass':bool(condition),'detail':detail})
captures=['current-before','named-orthographic','custom-projections','focus-engine','current-after-invalid','async-wait','cancel-wait','current-after-async']
view_count=0
for name in captures:
    data=load(name+'.json')['data'];path=Path(data['outputDirectory']);m=json.loads(Path(data['manifestPath']).read_text())
    check(name+' native output schema',Draft202012Validator(cli.contracts_module().output_schema('designer.capture')).is_valid(load(name+'.json')))
    check(name+' camera restoration independent',m['cameraBefore']==m['cameraAfter'])
    check(name+' file hash independent',all(hashlib.sha256((path/f['name']).read_bytes()).hexdigest()==f['sha256'] for f in data['files']))
    check(name+' PNG size independent',all(struct.unpack('>II',(path/v['file']).read_bytes()[16:24])==(v['width'],v['height']) for v in data['views']))
    check(name+' overview copies first image',(path/'overview.png').read_bytes()==(path/data['views'][0]['file']).read_bytes())
    view_count+=len(data['views'])
fronts={v['name']:v['camera'] for v in load('named-orthographic.json')['data']['views']}
for name,forward in {'front':[0,0,-1],'right':[-1,0,0],'top':[0,-1,0],'back':[0,0,1],'left':[1,0,0],'bottom':[0,1,0]}.items():
    check(name+' world direction',math.dist(fronts[name]['forwardWorld'],forward)<1e-5 and fronts[name]['projection']=='orthographic')
custom=load('custom-projections.json')['data']['views']
for v,az,el in [(custom[0],45,25),(custom[1],45,25),(custom[2],-35,-10)]:
    expected=[-math.sin(math.radians(az))*math.cos(math.radians(el)),-math.sin(math.radians(el)),-math.cos(math.radians(az))*math.cos(math.radians(el))]
    check(v['name']+' angles',math.dist(expected,v['camera']['forwardWorld'])<1e-5)
check('perspective and orthographic differ',custom[0]['camera']['projectionRows']!=custom[1]['camera']['projectionRows'])
v=load('focus-engine.json')['data']['views'][1]['camera']
check('explicit half height',v['orthographicSize']==2)
check('explicit camera distance',abs(math.dist(v['positionWorld'],v['targetWorld'])-10)<1e-5)
check('explicit target',math.dist(v['targetWorld'],[2.6,3.45,1.05])<1e-5)
current=[load(name+'.json')['data'] for name in ['current-before','current-after-invalid','current-after-async']]
blobs=[Path(x['recommendedImages'][0]).read_bytes() for x in current]
check('current screenshots byte-identical after all captures/rejections',blobs[0]==blobs[1]==blobs[2])
point_count=0
for id in [33,35,36,40,42,43]:
    p=load('part-'+str(id)+'.json')['data']['part'];g=load('geometry-'+str(id)+'.json')['data']['geometry']
    colliders=[x['bounds']['center'] for x in g['colliders'] if x['name']=='AttachPoint']
    for ap in p['attachPoints']:
        check('actual point %d.%d'%(id,ap['id']),min(math.dist(ap['worldPosition'],c) for c in colliders)<1e-6)
        point_count+=1
    check('two point APIs same '+str(id),p['attachPoints']==load('points-corrected-'+str(id)+'.json')['data']['points'])
gear=load('part-35.json')['data']['part']['attachPoints'][1];prop=load('part-36.json')['data']['part']['attachPoints'][0]
check('old stale definition distinguished',math.dist(gear['localPosition'],gear['definitionLocalPosition'])>.11)
check('gearbox prop separation retained',abs(math.dist(gear['worldPosition'],prop['worldPosition'])-.002518)<1e-6)
for kind in ('snapshot','history','selection'):
    check('final '+kind+' unchanged',load('baseline-'+kind+'.json')['data']==load('final-async-'+kind+'.json')['data'])
status=load('final-async-status.json')['data']
check('final one aircraft and 42 parts',status['sceneIntegrity']['aircraftInstanceCount']==1 and status['sceneIntegrity']['instances'][0]['partCount']==42)
contracts=[]
for line in (BASE/'calls.jsonl').read_text().splitlines():
    record=json.loads(line);v=load(record['file']);schema=cli.contracts_module().output_schema(record['command'])
    # These two recorded invocations supplied --async; acknowledgement has its own documented schema.
    if record.get('outputMode')=='asyncOutputSchema' or record['file'] in ('async-submit.json','cancel-submit.json'):
        schema=cli.contracts_module().auxiliary_schemas()['asyncOutputSchema']
    errors=list(Draft202012Validator(schema).iter_errors(v));contracts.append({'file':record['file'],'pass':not errors,'errors':[str(e)[:400] for e in errors[:2]]})
check('all recorded output contracts',all(c['pass'] for c in contracts),[c for c in contracts if not c['pass']])
report={'checksPassed':sum(c['pass'] for c in checks),'checksTotal':len(checks),'viewCount':view_count,'livePointCount':point_count,
        'recordedOutputCount':len(contracts),'identity':status['identity'],'buildId':status['buildId'],
        'cancelOutcome':load('cancel-request.json')['data']['state'],'cancellationDuringRenderVerified':False,
        'notCovered':['Forced renderer exceptions','Cancellation during active rendering (request arrived after completion)','Artificially inconsistent scene screenshots'],
        'checks':checks,'contracts':contracts}
(BASE/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('checks','contracts','identity')},ensure_ascii=False))
if not all(c['pass'] for c in checks):print(json.dumps([c for c in checks if not c['pass']],ensure_ascii=False));raise SystemExit(1)
