"""Bounded idle control after a long run, without forced GC or designer writes.

The exact owned fixture stays open. Sparse host probes separate elapsed-time
growth from continued reconstruction; they do not identify an allocation owner.
"""
import json,os,sys,time,subprocess
from pathlib import Path
from precision_acceptance import Run
from process_memory import memory
from review_restore_state import audit

r=Run(sys.argv[1]);host=Path(sys.argv[2]).resolve();seconds=int(sys.argv[3])
assert 30<=seconds<=600 and seconds%30==0
launch=json.loads((host.parent/'launch.json').read_text(encoding='utf-8-sig'))
assert launch['batchMode'] and str(launch['pid'])==os.environ['SP2BUILD_TEST_INSTANCE']
def call(label,command,args=None,**kw):
    result=r.call(label,command,args,**kw);assert result['success'],result;return result['data']
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab C17' and base['partCount']==874
samples=[];start=time.monotonic()
for elapsed in range(0,seconds+1,30):
    if elapsed:time.sleep(max(0,start+elapsed-time.monotonic()))
    label=f'idle-{elapsed:03}'
    h=call(label+'-heap','acceptance.host',extra_args=('--host',str(host),'--action','heap-inventory',
        '--expected-craft-name',base['name']))['probe']
    assert h['complete'] and not h['timedOut'] and not h['unlockError']
    samples.append({'seconds':time.monotonic()-start,'heap':h,'memory':memory(launch['pid'])})
    (r.root/'samples.json').write_text(json.dumps(samples,indent=2))
end=call('final','craft.snapshot',{'includeXml':True})
a=audit(base['xml'],end['xml']);r.check('complete state unchanged during idle',a['equivalent'],a);assert a['equivalent']
assert end['identity']['craftSessionId']==base['identity']['craftSessionId']
call('final-status','designer.status')
subprocess.run(['powershell.exe','-NoProfile','-File',str(Path(__file__).with_name('process_gpu_memory.ps1')),
    '-GameProcessId',str(launch['pid']),'-OutputPath',str(r.root/'final-gpu-pdh.json')],check=True,timeout=30)
(r.root/'summary.json').write_text(json.dumps({'idleSeconds':seconds,'samples':len(samples),'scope':__doc__,
    'busyHeapDeltaMB':(samples[-1]['heap']['busyBytes']-samples[0]['heap']['busyBytes'])/1e6,
    'privateDeltaMB':(samples[-1]['memory']['privateBytes']-samples[0]['memory']['privateBytes'])/1e6},indent=2))
