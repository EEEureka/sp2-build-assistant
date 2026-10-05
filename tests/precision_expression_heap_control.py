"""Native reload A/B with the game's existing ForceFunk switch, test host only.

The switch is restored in a finally block around synchronous native LoadXml.
This diagnoses compiler-associated retention; it does not certify expression
semantic equivalence or authorize shipping an interpreter-mode change.
"""
import json,os,sys,time,subprocess
from pathlib import Path
from precision_acceptance import Run
from review_restore_state import audit
from process_memory import memory

r=Run(sys.argv[1]);host=Path(sys.argv[2]).resolve();count=int(sys.argv[3])
assert 10<=count<=30
launch=json.loads((host.parent/'launch.json').read_text(encoding='utf-8-sig'))
assert launch['batchMode'] and str(launch['pid'])==os.environ['SP2BUILD_TEST_INSTANCE']
name='SP2Build 050 Precision Lab C17';samples=[]
def call(n,c,a=None,**kw):
    x=r.call(n,c,a,**kw);assert x['success'],x;return x['data']
def native(n,action,expected=name):
    return call(n,'acceptance.host',extra_args=('--host',str(host),'--action',action,'--fixture','C17','--expected-craft-name',expected))
def load(n,action,expected=name):
    d=native(n,action,expected);end=time.monotonic()+30;i=0
    while d['phase']!='ready':
        assert d['phase']!='failed' and time.monotonic()<end,d
        time.sleep(.3);i+=1;d=native(n+'-ready-'+str(i),'status')
    assert d['craftName']==name
def sample(n):
    h=native(n,'heap-inventory')['probe'];assert h['complete'] and not h['unlockError']
    samples.append({'label':n,'heap':h,'memory':memory(launch['pid'])})
    (r.root/'samples.json').write_text(json.dumps(samples,indent=2))
b=call('starting-copy','craft.snapshot',{'includeXml':True})
assert b['name'] in (name,'SP2Build 050 Precision Lab F2')
load('initial','load',b['name']);base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']==name and base['partCount']==874
for phase,action in [('compiled-a','load'),('function-tree-a','load-function-tree-control'),('compiled-b','load'),('function-tree-b','load-function-tree-control')]:
    load(phase+'-warmup',action);sample(phase+'-before')
    for n in range(count):
        load(phase+'-'+str(n),action)
        if (n+1)%5==0:sample(phase+'-'+str(n+1))
    final=call(phase+'-state','craft.snapshot',{'includeXml':True});a=audit(base['xml'],final['xml'])
    r.check(phase+' full state',a['equivalent'],a);assert a['equivalent'],a
load('restore-default','load')
final=call('final','craft.snapshot',{'includeXml':True});a=audit(base['xml'],final['xml']);r.check('native default state restored',a['equivalent'],a);assert a['equivalent']
summary=[]
for phase in ('compiled-a','function-tree-a','compiled-b','function-tree-b'):
    rows=[x for x in samples if x['label'].startswith(phase)]
    summary.append({'phase':phase,'loads':count,'busyDeltaMB':(rows[-1]['heap']['busyBytes']-rows[0]['heap']['busyBytes'])/1e6,'busyBlocksDelta':rows[-1]['heap']['busyBlocks']-rows[0]['heap']['busyBlocks']})
(r.root/'summary.json').write_text(json.dumps({'scope':__doc__,'phases':summary},indent=2))
print(json.dumps(summary))
