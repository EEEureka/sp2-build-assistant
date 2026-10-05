"""F3 retention observation beyond native Undo's 250-transition capacity.

This supplements, not replaces, the four-view/measurement performance suite.
Every rebuild uses the actual 874-part native craft. No collection is forced.
"""
import json,sys,time,uuid,xml.etree.ElementTree as ET,shutil
from pathlib import Path
from precision_acceptance import Run
from review_restore_state import audit
from process_memory import memory
from process_memory_map import sample as memory_map

r=Run(sys.argv[1]);count=int(sys.argv[2]);samples=[]
assert count>=150,'Observe both capacity fill and subsequent cycles'
def call(n,c,a=None,images=False):
    x=r.call(n,c,a,images=images);assert x['success'],x;return x['data']
def guard(s):
    i=s['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def status(n):
    s=call(n,'designer.status')
    assert not s['identity']['stateUncertain'] and s['sceneIntegrity']['status']=='healthy',s
    assert s['sceneIntegrity']['aircraftInstanceCount']==1
    return s
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab C17' and base['partCount']==874
s=status('initial-status')
assert s['registryVersion'] in ('0.5.0-dev15','0.5.0-dev16','0.5.0-dev20','0.5.0-dev21','0.5.0-dev22','0.5.0-dev23','0.5.0-dev24')
pid=json.loads((r.root/'initial-status.json').read_text(encoding='utf-8-sig'))['instancePid']
cp=call('checkpoint','craft.checkpoint.create',{**guard(s),'requestId':uuid.uuid4().hex,'name':'F3 retention baseline'})['id']
ids=[4,76,77,78,79,129,215,218]
def sample(index,s):
    row={'cycle':index,'memory':memory(pid),'runtimeRetention':s['runtimeRetention'],'identity':s['identity']}
    samples.append(row);(r.root/'samples.json').write_text(json.dumps(samples,indent=2))
def capture(label,s):
    call(label,'designer.capture',{**guard(s),'views':[{'view':'isometric','projection':'perspective'}],
        'resolution':{'width':1280,'height':800}},images=True)

def inventory(label):
    if len(sys.argv)<4:return
    config=Path(sys.argv[3]);request=config/'sp2build.acceptance-inventory.json'
    assert not request.exists()
    request.write_text(json.dumps({'label':label}))
    call(label+'-inventory-status','designer.status')
    assert not request.exists()
    shutil.copyfile(config/'sp2build.acceptance-inventory.result.json',r.root/(label+'-inventory.json'))
    (r.root/(label+'-memory-map.json')).write_text(json.dumps(memory_map(pid),indent=2))
    if len(sys.argv)>4:
        h=r.call(label+'-default-heap','acceptance.host',extra_args=('--host',str(Path(sys.argv[4]).resolve()),
            '--action','heap-inventory','--expected-craft-name',base['name']))
        assert h['success'] and h['data']['probe']['complete'] and not h['data']['probe']['timedOut'],h

sample(-1,s);capture('initial-view',s)
inventory('initial')
failure=None
try:
    for iteration in range(count):
        tag=f'cycle-{iteration:03}'
        ops=[{'kind':'part.update','partId':p,'changes':[{'path':'Part','attribute':'name','value':f'Retention {iteration:03} {p}'}],'symmetric':False} for p in ids]
        result=call(tag+'-edit','batch.apply',{**guard(s),'requestId':uuid.uuid4().hex,'operations':ops})
        assert result.get('rebuildCount')==1,result.get('rebuildCount')
        changed=call(tag+'-changed','craft.snapshot',{'includeXml':True})
        expected=ET.fromstring(base['xml'])
        for p in expected.findall('./Assembly/Parts/Part'):
            if int(p.get('id')) in ids:p.set('name',f'Retention {iteration:03} {p.get("id")}')
        a=audit(ET.tostring(expected,encoding='unicode'),changed['xml'])
        r.check(tag+' complete edited state',a['equivalent'],a);assert a['equivalent'],a
        call(tag+'-rollback','craft.rollback',{**guard(changed),'requestId':uuid.uuid4().hex,'checkpointId':cp})
        restored=call(tag+'-restored','craft.snapshot',{'includeXml':True})
        a=audit(base['xml'],restored['xml']);r.check(tag+' complete restored state',a['equivalent'],a);assert a['equivalent'],a
        s=status(tag+'-status');sample(iteration,s)
        retention=s['runtimeRetention']
        native=retention['nativeUndo']
        lifetime=retention.get('nativeMeshLifetime')
        if lifetime:
            assert lifetime['installed'] and lifetime['conversions']>0 and lifetime['conversions']==lifetime['releases'],lifetime
        expression=retention.get('expressionLifetime')
        if expression:
            t=expression['templates']
            assert expression['installed'] and t['count']<=t['limit'] and t['fallbacks']==0 and t['evictions']==0,expression
        r.check(tag+' bounded histories and one instance',retention['checkpointCount']<=64 and retention['rotationSnapshotCount']<=128 and native['count']<=native.get('maximumRetainedStates',native['maximum']+1) and retention['operationResults']['compressedBytes']<=67108864)
        if (iteration+1)%20==0:capture(tag+'-view',s)
        if (iteration+1)%25==0:inventory(tag)
except BaseException as exc:
    failure=exc
    (r.root/'interruption.json').write_text(json.dumps({'error':str(exc),'completedCycles':len(samples)-1,
        'plannedCycles':count,'passed':False},indent=2),encoding='utf-8')
    raise
finally:
    try:
        s=status('cleanup-status')
        current=call('cleanup-current','craft.snapshot',{'includeXml':True})
        same_session=current['identity']['craftSessionId']==base['identity']['craftSessionId'] and current['name']==base['name']
        if not same_session:
            r.check('cleanup original session still active',False,{'action':'Skipped stale checkpoint rollback','identity':current['identity']})
            raise RuntimeError('Designer session changed; original checkpoint must not be applied to replacement session')
        call('cleanup','craft.rollback',{**guard(s),'requestId':uuid.uuid4().hex,'checkpointId':cp})
        final=call('final','craft.snapshot',{'includeXml':True})
        a=audit(base['xml'],final['xml']);r.check('final full baseline restored',a['equivalent'],a)
        assert a['equivalent'],a
        s=status('final-status');sample(count,s)
        inventory('final')
    except BaseException as cleanup_error:
        (r.root/'cleanup-error.json').write_text(json.dumps({'error':str(cleanup_error),'originalFailure':str(failure) if failure else None},indent=2),encoding='utf-8')
        if failure is None:raise
cap=[x for x in samples if 0<=x['cycle']<count and x['runtimeRetention']['nativeUndo']['count']==x['runtimeRetention']['nativeUndo'].get('maximumRetainedStates',x['runtimeRetention']['nativeUndo']['maximum']+1)]
r.check('observed at least 30 cycles at native Undo capacity',len(cap)>=30,{'sampleCount':len(cap)})
(r.root/'summary.json').write_text(json.dumps({'cycles':count,'capacitySamples':len(cap),'initial':samples[0],'final':samples[-1],
    'meaning':'Full state and retention limits checked; memory trend requires separate analysis. Not a proof of global leak freedom.'},indent=2))
