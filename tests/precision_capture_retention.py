"""Read-only repeated capture control, preserving the native craft and camera."""
import json,os,sys,subprocess
from pathlib import Path
from precision_acceptance import Run
from process_memory import memory
from review_restore_state import audit

r=Run(sys.argv[1]);count=int(sys.argv[2]);host=Path(sys.argv[3]).resolve()
pid=int(os.environ['SP2BUILD_TEST_INSTANCE']);assert 10<=count<=100
def call(label,command,args=None,**kw):
    x=r.call(label,command,args,**kw);assert x['success'],x;return x['data']
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab C17' and base['partCount']==874
i=base['identity'];guard={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
samples=[]
def sample(label):
    s=call(label+'-status','designer.status')
    row={'label':label,'memory':memory(pid),'runtimeRetention':s['runtimeRetention']}
    samples.append(row);(r.root/'samples.json').write_text(json.dumps(samples,indent=2))
def inventory(label):
    h=call(label+'-heap','acceptance.host',extra_args=('--host',str(host),'--action','heap-inventory','--expected-craft-name',base['name']))['probe']
    assert h['complete'] and not h['timedOut'] and not h['unlockError']
    subprocess.run(['powershell.exe','-NoProfile','-File',str(Path(__file__).with_name('process_gpu_memory.ps1')),'-GameProcessId',str(pid),'-OutputPath',str(r.root/(label+'-gpu.json'))],check=True,timeout=30)
sample('initial');inventory('initial')
for n in range(count):
    label=f'capture-{n:03}'
    c=call(label,'designer.capture',{**guard,'views':[{'view':'isometric','projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True)
    r.check(label+' restored camera',c['cameraRestored'])
    sample(label)
inventory('final')
final=call('final','craft.snapshot',{'includeXml':True});a=audit(base['xml'],final['xml'])
r.check('complete state unchanged',a['equivalent'],a);assert a['equivalent']
(r.root/'summary.json').write_text(json.dumps({'captures':count,'privateDeltaMB':(samples[-1]['memory']['privateBytes']-samples[0]['memory']['privateBytes'])/1e6,'scope':__doc__},indent=2))
