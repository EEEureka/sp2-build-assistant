"""Default Win32 heap diagnostics: idle, read-only traffic, then edit/restore.

This is attribution evidence, not a replacement for the uninterrupted T18 run.
All game actions use the global CLI. No GC, heap compaction, OS input or saves.
"""
import json,os,sys,time,uuid,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from precision_acceptance import Run
from review_restore_state import audit
from process_memory import memory
from process_memory_map import sample as memory_map

r=Run(sys.argv[1]);host=Path(sys.argv[2]).resolve();cycles=int(sys.argv[3]);samples=[]
assert 1<=cycles<=50
launch=json.loads((host.parent/'launch.json').read_text(encoding='utf-8-sig'))
assert str(launch['pid'])==os.environ['SP2BUILD_TEST_INSTANCE'] and launch['batchMode'] is True
pid=launch['pid'];name='SP2Build 050 Precision Lab C17'
def call(label,command,args=None,**kw):
    d=r.call(label,command,args,**kw);assert d['success'],d;return d['data']
def guard(s):
    i=s['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def status(label):
    s=call(label,'designer.status')
    assert not s['identity']['stateUncertain'] and s['sceneIntegrity']['status']=='healthy'
    assert s['sceneIntegrity']['aircraftInstanceCount']==1
    return s
def heap(label):
    d=call(label+'-heap','acceptance.host',extra_args=('--host',str(host),'--action','heap-inventory','--expected-craft-name',name))['probe']
    assert d['complete'] and not d['timedOut'] and d['unlockError']==0,d
    return d
def sample(label):
    s=status(label+'-status');m=memory(pid);h=heap(label)
    row={'label':label,'time':time.time(),'memory':m,'heap':h,'runtimeRetention':s['runtimeRetention']}
    samples.append(row);(r.root/'samples.json').write_text(json.dumps(samples,indent=2))
    if label in ('initial','idle-20s','read-19','edit-09','edit-19','edit-29','final'):
        subprocess.run(['powershell.exe','-NoProfile','-File',str(Path(__file__).with_name('process_gpu_memory.ps1')),
            '-GameProcessId',str(pid),'-OutputPath',str(r.root/(label+'-gpu-pdh.json'))],check=True,timeout=30)
    return s
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']==name and base['partCount']==874
# Warm diagnostic DLL/PInvoke metadata before interpreting subsequent deltas.
heap('warmup');s=sample('initial')
cp=call('checkpoint','craft.checkpoint.create',{**guard(s),'requestId':uuid.uuid4().hex,'name':'Heap observation baseline'})['id']
failure=None
try:
    time.sleep(20);s=sample('idle-20s')
    for i in range(20):
        snapshot=call(f'read-{i:02}','craft.snapshot',{'includeXml':True})
        a=audit(base['xml'],snapshot['xml']);r.check(f'read {i} complete state unchanged',a['equivalent'],a);assert a['equivalent']
        if (i+1)%5==0:s=sample(f'read-{i:02}')
    ids=[4,76,77,78,79,129,215,218]
    for i in range(cycles):
        label=f'edit-{i:02}'
        ops=[{'kind':'part.update','partId':p,'changes':[{'path':'Part','attribute':'name','value':f'Heap probe {i:02} {p}'}],'symmetric':False} for p in ids]
        result=call(label,'batch.apply',{**guard(s),'requestId':uuid.uuid4().hex,'operations':ops})
        assert result['rebuildCount']==1
        changed=call(label+'-changed','craft.snapshot',{'includeXml':True})
        expected=ET.fromstring(base['xml'])
        for p in expected.findall('./Assembly/Parts/Part'):
            if int(p.get('id')) in ids:p.set('name',f'Heap probe {i:02} {p.get("id")}')
        a=audit(ET.tostring(expected,encoding='unicode'),changed['xml'])
        r.check(label+' full expected edit',a['equivalent'],a);assert a['equivalent']
        call(label+'-restore','craft.rollback',{**guard(changed),'requestId':uuid.uuid4().hex,'checkpointId':cp})
        restored=call(label+'-restored','craft.snapshot',{'includeXml':True})
        a=audit(base['xml'],restored['xml']);r.check(label+' full restoration',a['equivalent'],a);assert a['equivalent']
        s=sample(label)
        if (i+1)%10==0:(r.root/(label+'-memory-map.json')).write_text(json.dumps(memory_map(pid),indent=2))
except BaseException as exc:
    failure=exc;raise
finally:
    try:
        current=call('cleanup-current','craft.snapshot',{'includeXml':True})
        assert current['identity']['craftSessionId']==base['identity']['craftSessionId'] and current['name']==name,'Changed session: skip stale rollback'
        call('cleanup','craft.rollback',{**guard(current),'requestId':uuid.uuid4().hex,'checkpointId':cp})
        final=call('final','craft.snapshot',{'includeXml':True})
        a=audit(base['xml'],final['xml']);r.check('complete baseline restored',a['equivalent'],a);assert a['equivalent']
        sample('final')
    except BaseException as error:
        (r.root/'cleanup-error.json').write_text(json.dumps({'error':str(error),'originalFailure':str(failure) if failure else None},indent=2))
        if failure is None:raise
(r.root/'summary.json').write_text(json.dumps({'editCycles':cycles,'samples':len(samples),'meaning':__doc__},indent=2))
