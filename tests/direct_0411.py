"""Live read-only acceptance for 0.4.11, via installed global sp2build only.

Run phases separately so returned images can actually be inspected between phases.
"""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).parent/'artifacts/staged-build/direct-0.4.11'
ROOT.mkdir(parents=True,exist_ok=True)
CLI=shutil.which('sp2build');assert CLI,'Global sp2build is required'
CHECKS=ROOT/'checks.json'
checks=json.loads(CHECKS.read_text()) if CHECKS.exists() else []
def check(name,passed,detail=None):
    checks.append({'name':name,'pass':bool(passed),'detail':detail})
    CHECKS.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(('PASS ' if passed else 'FAIL ')+name,flush=True)
def call(label,command,args=None,extra=()):
    options=[CLI,*command.split('.'),'--json','--timeout','60']
    if args is not None:
        path=ROOT/(label+'-input.json');path.write_text(json.dumps(args),encoding='utf-8');options+=['--input',str(path)]
    options+=list(extra)
    p=subprocess.run(options,capture_output=True,encoding='utf-8',timeout=90)
    value=json.loads(p.stdout);(ROOT/(label+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    with (ROOT/'calls.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'file':label+'.json','command':command,'exitCode':p.returncode,'outputMode':'asyncOutputSchema' if '--async' in extra else 'outputSchema'})+'\n')
    print(label+': '+str(value.get('success'))+' '+str(value.get('error',{}).get('code','')),flush=True)
    return value
def status(label):return call(label,'designer.status')['data']
def capture(label,**args):
    s=status(label+'-status')
    payload={'craftSessionId':s['identity']['craftSessionId'],'expectedRevision':s['identity']['revision'],**args}
    result=call(label,'designer.capture',payload,('--output-dir',str(ROOT/'images')))
    check(label+' success',result['success'])
    if result['success']:
        data=result['data'];manifest=json.loads(Path(data['manifestPath']).read_text(encoding='utf-8'))
        check(label+' camera restored',manifest['cameraBefore']==manifest['cameraAfter'] and data['cameraRestored'])
        check(label+' identity retained',data['identity']==s['identity'])
        check(label+' files intact',all(hashlib.sha256((Path(data['outputDirectory'])/f['name']).read_bytes()).hexdigest()==f['sha256'] for f in data['files']))
        check(label+' all views recommended',len(data['recommendedImages'])==len(data['views']))
        print(json.dumps({'recommendedImages':data['recommendedImages']}),flush=True)
    return result
phase=sys.argv[1]
if phase=='baseline':
    s=status('baseline-status');check('loaded 0.4.11',s['pluginVersion']=='0.4.11')
    check('single scene instance',s['sceneIntegrity']['aircraftInstanceCount']==1 and s['sceneIntegrity']['status']=='healthy')
    call('baseline-snapshot','craft.snapshot',{'includeXml':True})
    call('baseline-history','craft.history');call('baseline-selection','designer.selection')
    capture('current-before')
elif phase=='views':
    capture('named-orthographic',views=[{'view':v,'projection':'orthographic'} for v in ['front','right','top','back','left','bottom','isometric']],resolution={'width':1024,'height':640})
    capture('custom-projections',views=[
        {'name':'perspective-angle','view':'custom','projection':'perspective','azimuthDegrees':45,'elevationDegrees':25,'fieldOfViewDegrees':45},
        {'name':'orthographic-angle','view':'custom','projection':'orthographic','azimuthDegrees':45,'elevationDegrees':25},
        {'name':'rolled-angle','view':'custom','projection':'perspective','azimuthDegrees':-35,'elevationDegrees':-10,'rollDegrees':30,'distance':25,'fieldOfViewDegrees':50},
        {'name':'current-orthographic','view':'current','projection':'orthographic'}],resolution={'width':1024,'height':640})
elif phase=='focus':
    capture('focus-engine',focusPartIds=[31,32,33,34,35,36,37],views=[
        {'name':'engine-angle','view':'custom','azimuthDegrees':40,'elevationDegrees':20,'projection':'perspective','fieldOfViewDegrees':40},
        {'name':'engine-right','view':'right','projection':'orthographic','target':[2.6,3.45,1.05],'orthographicSize':2,'distance':10}],resolution={'width':1280,'height':800})
elif phase=='invalid':
    s=status('invalid-status');base={'craftSessionId':s['identity']['craftSessionId'],'expectedRevision':s['identity']['revision']}
    cases=[('bad-projection',{'views':[{'projection':'invalid'}]},'invalid_input'),
           ('missing-angle',{'views':[{'view':'custom','azimuthDegrees':20}]},'invalid_input'),
           ('current-distance',{'views':[{'view':'current','distance':10}]},'invalid_input'),
           ('duplicate-view',{'views':['front','front']},'invalid_input'),
           ('missing-part',{'focusPartIds':[999999]},'part_not_found'),
           ('resolution-budget',{'views':['front','right','top'],'resolution':{'width':2048,'height':2048}},'render_budget'),
           ('stale-session',{'craftSessionId':'expired-session'},'session_conflict'),
           ('stale-revision',{'expectedRevision':s['identity']['revision']+999},'revision_conflict')]
    for name,args,code in cases:
        r=call(name,'designer.capture',{**base,**args});check(name+' rejected',not r['success'] and r.get('error',{}).get('code')==code,r.get('error'))
    capture('current-after-invalid')
elif phase=='points':
    for id in [33,35,36,40,42,43]:
        p=call('part-'+str(id),'parts.get',{'id':id})['data']['part']
        g=call('geometry-'+str(id),'parts.geometry',{'id':id})['data']
        call('points-'+str(id),'connections.points',{'part':id})
        check('live point source '+str(id),all(x.get('positionSource')=='live_attach_point_transform' for x in p['attachPoints']))
elif phase=='points-api':
    for id in [33,35,36,40,42,43]:
        r=call('points-corrected-'+str(id),'connections.points',{'part':id})
        p=json.loads((ROOT/('part-'+str(id)+'.json')).read_text())['data']['part']
        check('connections.points matches part '+str(id),r['success'] and r['data']['points']==p['attachPoints'])
elif phase=='async':
    s=status('async-status');base={'craftSessionId':s['identity']['craftSessionId'],'expectedRevision':s['identity']['revision']}
    request={**base,'views':[{'view':'custom','name':'aircraft-oblique','projection':'perspective','azimuthDegrees':45,'elevationDegrees':25,'distance':19,'fieldOfViewDegrees':45}],'resolution':{'width':1600,'height':1000}}
    r=call('async-submit','designer.capture',request,('--async',))
    if r['success']:
        op=r['data']['operationId']
        v=call('async-wait','operation.wait',extra=('--id',op,'--output-dir',str(ROOT/'images')))
        check('async wait downloads capture',v['success'] and Path(v['data'].get('manifestPath','missing')).is_file())
        if v['success']:print(json.dumps({'recommendedImages':v['data']['recommendedImages']}),flush=True)
    request={**base,'views':[{'view':'custom','name':'cancel-'+str(i),'projection':'perspective','azimuthDegrees':i*45,'elevationDegrees':20} for i in range(8)],'resolution':{'width':1440,'height':960}}
    r=call('cancel-submit','designer.capture',request,('--async',))
    if r['success']:
        op=r['data']['operationId']
        call('cancel-request','operation.cancel',extra=('--id',op))
        v=call('cancel-wait','operation.wait',extra=('--id',op,'--output-dir',str(ROOT/'images')))
        check('cancel outcome known',v['success'] or v.get('error',{}).get('code')=='cancelled',v.get('error',{}))
        if v['success']:print('Cancellation arrived after completion; no cancelled-render claim.',flush=True)
    capture('current-after-async')
elif phase in ('finish','finish-after-async'):
    prefix='final' if phase=='finish' else 'final-async'
    snapshot=call(prefix+'-snapshot','craft.snapshot',{'includeXml':True})
    history=call(prefix+'-history','craft.history');selection=call(prefix+'-selection','designer.selection');s=status(prefix+'-status')
    before=json.loads((ROOT/'baseline-snapshot.json').read_text())
    check('serialized craft unchanged',before['data']==snapshot['data'])
    old=json.loads((ROOT/'baseline-history.json').read_text());check('undo history unchanged',old['data']==history['data'])
    old=json.loads((ROOT/'baseline-selection.json').read_text());check('selection unchanged',old['data']==selection['data'])
    check('scene remains one instance',s['sceneIntegrity']['aircraftInstanceCount']==1 and s['sceneIntegrity']['status']=='healthy')
else:raise ValueError(phase)
