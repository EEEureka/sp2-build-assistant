"""Same 8 raw renames on actual loaded 0.4.11/0.5.0, through global CLI.

All 30 samples count. Compare full resulting XML except the declared names and
the previously frozen Euler/generated-target restore policy. No new commands
are used, so the old DLL can execute the same workload with the new CLI.
"""
import json,math,statistics,sys,uuid,xml.etree.ElementTree as ET
from precision_acceptance import Run
from review_restore_state import audit
from process_memory import memory
r=Run(sys.argv[1]);version=sys.argv[2];times=[]
count=int(sys.argv[3]) if len(sys.argv)>3 else 30
assert count>=2
def call(n,c,a=None):
 x=r.call(n,c,a);assert x['success'],x;return x['data']
def guard(i):return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
s=call('loaded','designer.status');assert s['pluginVersion']==version,s['pluginVersion']
pid=json.loads((r.root/'loaded.json').read_text(encoding='utf-8-sig'))['instancePid']
(r.root/'initial-memory.json').write_text(json.dumps(memory(pid),indent=2))
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab C17' and base['partCount']==874
ids=[4,76,77,78,79,129,215,218]
cp=call('checkpoint','craft.checkpoint.create',{**guard(base['identity']),'requestId':uuid.uuid4().hex,'name':'Same eight raw edits benchmark'})['id']
identity=base['identity']
try:
 for iteration in range(count):
  names={p:f'Raw benchmark {iteration:02} {p}' for p in ids}
  ops=[{'kind':'part.update','partId':p,'changes':[{'path':'Part','attribute':'name','value':name}],'symmetric':False} for p,name in names.items()]
  result=call(f'edit-{iteration:02}','batch.apply',{**guard(identity),'requestId':uuid.uuid4().hex,'operations':ops})
  seconds=r.calls[-1]['seconds'];snapshot=call(f'state-{iteration:02}','craft.snapshot',{'includeXml':True});identity=snapshot['identity']
  expected=ET.fromstring(base['xml'])
  for part in expected.findall('./Assembly/Parts/Part'):
   if int(part.get('id')) in names:part.set('name',names[int(part.get('id'))])
  checked=audit(ET.tostring(expected,encoding='unicode'),snapshot['xml'])
  r.check(f'full state {iteration:02}',checked['equivalent'],checked)
  assert checked['equivalent'],checked
  if version=='0.5.0':r.check(f'one merged rebuild {iteration:02}',result.get('rebuildCount')==1,result.get('rebuildCount'))
  status=call(f'diagnostics-{iteration:02}','designer.status')
  r.check(f'healthy single instance {iteration:02}',not status['identity']['stateUncertain'] and status['sceneIntegrity']['aircraftInstanceCount']==1)
  times.append({'iteration':iteration,'seconds':seconds,'rebuildCount':result.get('rebuildCount'),'stageTimings':result.get('stageTimings'),'memory':memory(pid),'runtimeRetention':status.get('runtimeRetention')})
  (r.root/'samples.json').write_text(json.dumps(times,indent=2))
finally:
 s=call('cleanup-status','designer.status')
 assert not s['identity']['stateUncertain'],'Unsafe state: preserve evidence, no ordinary writes'
 call('cleanup','craft.rollback',{**guard(s['identity']),'requestId':uuid.uuid4().hex,'checkpointId':cp})
 final=call('final','craft.snapshot',{'includeXml':True});checked=audit(base['xml'],final['xml'])
 r.check('full baseline restored',checked['equivalent'],checked)
 call('final-status','designer.status')
values=sorted(x['seconds'] for x in times)
report={'loadedVersion':version,'samples':len(values),'medianSeconds':statistics.median(values),'p95Seconds':values[math.ceil(.95*len(values))-1],'maxSeconds':max(values),'eligibleForThirtySampleGate':len(values)>=30,'workload':f'8 raw part.update renames, exact same IDs/values/order, {count} calls, all samples included'}
(r.root/'performance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
