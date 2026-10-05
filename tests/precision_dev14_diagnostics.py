"""Live connection diagnostics, memory counters and one-millimetre diff."""
import json,sys,uuid,math
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1])
def call(n,c,a=None):
    x=r.call(n,c,a);assert x['success'],x;return x['data']
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def snap(n):return call(n,'craft.snapshot',{'includeXml':True})
def write(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def attempt(n,op):return r.call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[op]})
def connect(a,ap,b,bp):return {'kind':'connection.connect','partA':a,'attachPointA':ap,'partB':b,'attachPointB':bp,'symmetric':False}
def restored(n,old):
    proof=audit(old['xml'],snap(n)['xml']);r.check(n+' full state',proof['equivalent'],proof)
base=snap('baseline');assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'dev14 diagnostics baseline'})['id']
try:
    d=call('loaded','designer.status');assert d['registryVersion']=='0.5.0-dev14'
    r.check('native undo diagnostic matches native history',d['runtimeRetention']['nativeUndo']['count']==len(call('history','craft.history')['nativeSteps']) and d['runtimeRetention']['nativeUndo']['xmlBytes']>0)
    r.check('Unity counters available in this build',all(v>0 for v in d['runtimeRetention']['unityMemory'].values()))
    out=write('add-wing',[{'kind':'part.add','templateId':'tpl-1bdb332430679d47','temporaryId':'w','position':[3,2.25,0]}]);root=out['temporaryIds']['w']
    parts=snap('added')['parts'];ids=[p['id'] for p in parts if p['id'] not in [1,2,3]]
    control=next(i for i in ids if i!=root)
    write('disconnect-control',[{'kind':'connection.disconnect','partA':control,'partB':root,'symmetric':False}])
    before=snap('unconnected')
    x=attempt('wrong-direction',connect(root,1,control,0));detail=x.get('error',{}).get('details',{})
    r.check('wrong direction explained',not x['success'] and x['error']['code']=='invalid_connection' and 'target_cannot_receive_source' in detail.get('reasons',[]) and detail.get('reverseDirectionCompatible') is True,detail)
    r.check('both endpoints identify actual parts and mounts',detail.get('source',{}).get('part',{}).get('id')==root and detail.get('target',{}).get('part',{}).get('id')==control and detail.get('source',{}).get('point',{}).get('id')==1,detail)
    restored('wrong-direction-restored',before)
    write('correct-direction',[connect(control,0,root,1)])
    write('mount-valid',[connect(root,0,1,1)])
    before=snap('reconnected')
    for label,op,reason in [('missing-source',connect(root,999,1,1),'source_attach_point_missing'),('missing-target',connect(root,0,1,999),'target_attach_point_missing'),('occupied-target',connect(3,0,root,0),'target_attach_point_occupied')]:
        x=attempt(label,op);detail=x.get('error',{}).get('details',{})
        r.check(label+' detailed rejection',not x['success'] and reason in detail.get('reasons',[]),x.get('error'))
        restored(label+'-restored',before)
    before=snap('before-mm');move=write('one-millimetre',[{'kind':'transform.apply','partIds':ids,'mode':'delta','translation':[.001,0,0],'symmetric':False}])
    delta=call('one-mm-diff','craft.diff',{'checkpointId':move['beforeCheckpointId']});after=snap('after-mm')
    old={p['id']:p for p in before['parts']};now={p['id']:p for p in after['parts']}
    r.check('one millimetre retained in actual positions',all(math.dist(now[i]['position'],[old[i]['position'][0]+.001,*old[i]['position'][1:]])<=.0001 for i in ids))
    (r.root/'diff-inspection.json').write_text(json.dumps(delta,indent=2))
    changes=delta['diff']['changes']
    r.check('diff contains precisely every one-millimetre position',not delta['diff']['truncated'] and len(changes)==len(ids) and
        {c['path'] for c in changes}=={'Aircraft/Assembly[0]/Parts[0]/Part[id='+str(i)+']/@position' for i in ids} and
        all(abs(float(c['after'].split(',')[0])-float(c['before'].split(',')[0])-.001)<=1e-6 for c in changes),changes)
finally:
    call('restore-original','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});restored('final',base)
    d=call('final-status','designer.status');r.check('healthy one aircraft',d['sceneIntegrity']['status']=='healthy' and d['sceneIntegrity']['aircraftInstanceCount']==1)
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
