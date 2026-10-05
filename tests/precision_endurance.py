"""Thirty live F3 cycles, using the installed CLI and native-UI test copy."""
import json
import statistics
import uuid
from precision_acceptance import Run

r=Run('dev4-endurance-30')
base=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert base['name'].startswith('SP2Build 050 Precision Lab') and base['partCount']==874
ids=[4,76,77,78,79,129,215,218]
samples=[]
for i in range(30):
    tag=f'cycle-{i:02}'
    before=r.call(tag+'-state','designer.status')['data']
    assert not before['identity']['stateUncertain'] and before['sceneIntegrity']['status']=='healthy'
    identity=before['identity']
    guard={'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
    query=r.call(tag+'-query','properties.get',{'id':76,'limit':1000})
    assert query['success']
    operations=[{'kind':'properties.set','partId':76,'patch':{'ProceduralWindow[0].height':.721+i*.00001},'symmetric':False}]
    operations += [{'kind':'part.update','partId':pid,'changes':[{'path':'Part','attribute':'name','value':f'Endurance {i} {pid}'}],'symmetric':False} for pid in ids if pid!=76]
    edited=r.call(tag+'-edit','batch.apply',{**guard,'requestId':uuid.uuid4().hex,'operations':operations})
    assert edited['success'], edited
    identity=edited['data']['identity']
    guard={'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
    images=r.call(tag+'-capture','designer.capture',{**guard,'focusPartIds':ids,'views':[{'view':v,'projection':'orthographic' if v!='isometric' else 'perspective'} for v in ('front','right','top','isometric')],'resolution':{'width':1280,'height':800}},images=True)
    r.check(tag+' capture',images['success'],images.get('error'))
    geom=r.call(tag+'-geometry','geometry.measure',{**guard,'partIdsA':[76],'partIdsB':[77]})
    r.check(tag+' measurement',geom['success'],geom.get('error'))
    restored=r.call(tag+'-restore','craft.rollback',{**guard,'requestId':uuid.uuid4().hex,'checkpointId':edited['data']['beforeCheckpointId']})
    assert restored['success'],restored
    after=r.call(tag+'-restored','designer.status')['data']
    assert not after['identity']['stateUncertain'] and after['sceneIntegrity']['status']=='healthy'
    assert after['identity']['fingerprint']==base['identity']['fingerprint']
    r.check(tag+' baseline fingerprint and one aircraft',True)
    samples.append({'cycle':i,'identity':after['identity'],'sceneIntegrity':after['sceneIntegrity'],'timings':{c['command']:c['seconds'] for c in r.calls if c['label'].startswith(tag)},'stageTimings':edited['data'].get('stageTimings'),'rebuildCount':edited['data'].get('rebuildCount')})
    (r.root/'samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
summary={}
for command in ['properties.get','batch.apply','designer.capture','geometry.measure','craft.rollback']:
    values=sorted(row['timings'][command] for row in samples)
    summary[command]={'count':len(values),'p50':statistics.median(values),'p95':values[28],'max':max(values)}
(r.root/'performance.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
r.call('final','craft.snapshot',{'includeXml':True})
print(json.dumps(summary),flush=True)
