"""Same fixed C17 start per sample, original old/new binaries, common native loader.

Native-load preparation timings are separate from measured edits. Every sample
and full-state comparison is retained, including any failure. No old rollback
implementation or monkeypatch of its edit logic is used to reset the baseline.
"""
import json,math,statistics,sys,time,uuid,xml.etree.ElementTree as ET
from pathlib import Path
from precision_acceptance import Run
from review_restore_state import audit
from process_memory import memory
r=Run(sys.argv[1]);version=sys.argv[2];host=sys.argv[3];count=int(sys.argv[4]) if len(sys.argv)>4 else 30
identity=None;samples=[];fixture='SP2Build 050 Precision Lab C17'
def call(n,c,a=None,**kw):
    global identity
    x=r.call(n,c,a,**kw);assert x['success'],x
    if x['data'].get('identity'):identity=x['data']['identity']
    return x['data']
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def reset(label):
    call(label+'-load','acceptance.host',extra_args=['--host',host,'--action','load','--fixture','C17','--expected-craft-name',fixture])
    limit=time.monotonic()+90
    while True:
        state=call(label+'-host-'+str(len(r.calls)),'acceptance.host',extra_args=['--host',host])
        if state['phase']=='ready':break
        assert state['phase']!='failed' and time.monotonic()<limit,state
        time.sleep(.2)
    return call(label+'-baseline','craft.snapshot',{'includeXml':True})
status=call('loaded','designer.status');assert status['pluginVersion']==version
pid=json.loads((r.root/'loaded.json').read_text())['instancePid']
host_info=json.loads((Path(host)/'host.json').read_text(encoding='utf-8-sig'))
assert host_info['pid']==pid and host_info['batchMode'] is True
base=call('initial','craft.snapshot',{'includeXml':True});assert base['name']==fixture and base['partCount']==874
ids=[4,76,77,78,79,129,215,218]
try:
    for i in range(count):
        tag=f'sample-{i:02}'
        before=reset(tag)
        restored=audit(base['xml'],before['xml']);r.check(tag+' fixed native baseline',restored['equivalent'],restored);assert restored['equivalent'],restored
        names={p:f'Raw benchmark {i:02} {p}' for p in ids}
        out=call(tag+'-edit','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,
            'operations':[{'kind':'part.update','partId':p,'changes':[{'path':'Part','attribute':'name','value':names[p]}],'symmetric':False} for p in ids]})
        elapsed=r.calls[-1]['seconds']
        after=call(tag+'-after','craft.snapshot',{'includeXml':True})
        expected=ET.fromstring(base['xml'])
        for p in expected.findall('./Assembly/Parts/Part'):
            if int(p.get('id')) in names:p.set('name',names[int(p.get('id'))])
        checked=audit(ET.tostring(expected,encoding='unicode'),after['xml'])
        r.check(tag+' full changed state',checked['equivalent'],checked)
        state=call(tag+'-status','designer.status')
        healthy=not state['identity']['stateUncertain'] and state['sceneIntegrity']['aircraftInstanceCount']==1
        r.check(tag+' healthy single instance',healthy)
        samples.append({'iteration':i,'seconds':elapsed,'rebuildCount':out.get('rebuildCount'),'fullStatePassed':checked['equivalent'],
            'healthy':healthy,'stageTimings':out.get('stageTimings'),'memory':memory(pid)})
        (r.root/'samples.json').write_text(json.dumps(samples,indent=2))
        assert healthy,'Stop ordinary writes; retain failure and recover with native fixture reload.'
finally:
    final=reset('cleanup');checked=audit(base['xml'],final['xml']);r.check('full baseline restored',checked['equivalent'],checked)
values=sorted(s['seconds'] for s in samples)
report={'loadedVersion':version,'samples':len(values),'medianSeconds':statistics.median(values),'p95Seconds':values[math.ceil(.95*len(values))-1],
    'maxSeconds':max(values),'allFullStatePassed':all(s['fullStatePassed'] and s['healthy'] for s in samples),
    'eligibleForThirtySampleGate':len(values)>=30 and all(s['fullStatePassed'] and s['healthy'] for s in samples),
    'preparation':'Identical native saved-fixture reload before each sample; preparation excluded from edit timing.',
    'workload':'Same eight raw part.update renames, same IDs/order/value sequence, all samples included.',
    'environment':'Real Unity batch-mode game with graphics; common isolated host suppresses native saved-file writes. No bridge methods patched, no desktop inputs.'}
(r.root/'performance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
