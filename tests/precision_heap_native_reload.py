"""Native saved-fixture reload control for heap attribution, no bridge writes.

Same native C17 test copy loaded repeatedly by the isolated host. This measures
one native construction per iteration, versus two for edit/rollback diagnostics.
No forced GC/compaction, desktop input or save-file writes.
"""
import json,os,sys,time,subprocess
from pathlib import Path
from precision_acceptance import Run
from review_restore_state import audit
from process_memory import memory

r=Run(sys.argv[1]);host=Path(sys.argv[2]).resolve();count=int(sys.argv[3]);samples=[]
host_only='--host-only' in sys.argv[4:]
assert 1<=count<=30
launch=json.loads((host.parent/'launch.json').read_text(encoding='utf-8-sig'))
assert launch['batchMode'] and str(launch['pid'])==os.environ['SP2BUILD_TEST_INSTANCE']
pid=launch['pid'];name='SP2Build 050 Precision Lab C17'
def call(label,command,args=None,**kw):
    d=r.call(label,command,args,**kw);assert d['success'],d;return d['data']
def native(label,action):
    return call(label,'acceptance.host',extra_args=('--host',str(host),'--action',action,'--fixture','C17','--expected-craft-name',name))
def load(label):
    d=native(label,'load');deadline=time.monotonic()+30;i=0
    while d['phase']!='ready':
        assert d['phase']!='failed' and time.monotonic()<deadline,d
        time.sleep(.3);i+=1;d=native(label+f'-ready-{i}','status')
    assert d['craftName']==name
def snapshot(label):
    d=call(label,'craft.snapshot',{'includeXml':True});assert d['name']==name and d['partCount']==874
    return d
def sample(label):
    s=None if host_only else call(label+'-status','designer.status')
    h=native(label+'-heap','heap-inventory')['probe']
    assert h['complete'] and not h['timedOut'] and h['unlockError']==0,h
    if s is not None:assert s['sceneIntegrity']['status']=='healthy' and s['sceneIntegrity']['aircraftInstanceCount']==1
    samples.append({'label':label,'memory':memory(pid),'runtimeRetention':None if s is None else s['runtimeRetention'],'heap':h})
    (r.root/'samples.json').write_text(json.dumps(samples,indent=2))
if host_only:assert native('guard-open-copy','status')['craftName']==name
else:snapshot('guard-open-copy')
load('initial-native-load');base=None if host_only else snapshot('baseline');sample('initial')
for i in range(count):
    label=f'native-{i:02}';load(label+'-load')
    if not host_only:
        d=snapshot(label+'-snapshot')
        comparison=audit(base['xml'],d['xml']);r.check(label+' full native baseline',comparison['equivalent'],comparison)
        assert comparison['equivalent'],comparison
        assert d['identity']['craftSessionId']!=base['identity']['craftSessionId']
    sample(label)
subprocess.run(['powershell.exe','-NoProfile','-File',str(Path(__file__).with_name('process_gpu_memory.ps1')),
    '-GameProcessId',str(pid),'-OutputPath',str(r.root/'final-gpu-pdh.json')],check=True,timeout=30)
(r.root/'summary.json').write_text(json.dumps({'nativeLoads':count,'hostOnly':host_only,'bridgeReadCalls':0 if host_only else 'snapshot and status per iteration','meaning':__doc__},indent=2))
