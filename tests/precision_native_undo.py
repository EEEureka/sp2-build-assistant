"""Stage a public CLI edit, then independently verify the real UI Undo button."""
import json, sys, uuid
from precision_acceptance import Run, ROOT
from review_restore_state import audit

r=Run(sys.argv[2])
def snap(label):
    x=r.call(label,'craft.snapshot',{'includeXml':True}); assert x['success'],x
    assert x['data']['name']=='SP2Build 050 Precision Lab F2'
    assert not x['data']['identity']['stateUncertain']
    return x['data']
def guard(s):
    i=s['identity']; return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def capture(label,s,views=None):
    x=r.call(label,'designer.capture',{**guard(s),'focusPartIds':[4,5,6],
        'views':views or [{'view':'back','projection':'orthographic'},{'view':'custom','azimuthDegrees':-145,'elevationDegrees':25,'projection':'perspective'}],
        'resolution':{'width':1280,'height':800}},images=True); assert x['success'],x
    return x['data']

if sys.argv[1]=='prepare':
    s=snap('baseline'); assert s['partCount']==6
    cp=r.call('checkpoint','craft.checkpoint.create',{**guard(s),'requestId':uuid.uuid4().hex,'name':'before real UI undo'})
    assert cp['success'],cp
    (r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp['data']['id']}))
    r.call('history-before','craft.history')
    views=capture('baseline-views',s)['repeatableViews']
    x=r.call('edit','batch.apply',{**guard(s),'requestId':uuid.uuid4().hex,'operations':[
        {'kind':'shape.update','partId':4,'symmetric':False,'patch':{'length':2.1}},
        {'kind':'appearance.set','mode':'shared','materialId':20,'patch':{'colors':[{'index':0,'rgba':[.9,.15,.1,1]}]}}]})
    assert x['success'],x
    changed=snap('changed');r.check('edit changes state',changed['xml']!=s['xml'])
    capture('changed-views',changed,views)
    r.call('history-after-edit','craft.history')
else:
    prep=ROOT/sys.argv[3]
    b=json.loads((prep/('changed.json' if sys.argv[1]=='verify-redo' else 'baseline.json')).read_text(encoding='utf-8-sig'))['data']
    s=snap('after-native-undo'); result=audit(b['xml'],s['xml'])
    (r.root/'independent-restore.json').write_text(json.dumps(result,indent=2))
    r.check('native history restores expected complete state',result['equivalent'],result)
    assert result['equivalent'],result
    r.check('native history keeps open craft session',s['identity']['craftSessionId']==b['identity']['craftSessionId'])
    r.check('native history advances revision',s['identity']['revision']>b['identity']['revision'])
    cp=json.loads((prep/'fixture.json').read_text())['checkpointId']
    cps=r.call('checkpoints-after-native-history','craft.checkpoint.list')['data']['checkpoints']
    r.check('pre-existing checkpoint survives native history',any(x['id']==cp for x in cps))
    stale=r.call('reject-pre-history-revision','batch.apply',{**guard(b),'requestId':uuid.uuid4().hex,'operations':[
        {'kind':'shape.update','partId':4,'symmetric':False,'patch':{'length':1.7}}]})
    r.check('pre-history revision is rejected',not stale['success'] and stale.get('error',{}).get('code')=='revision_conflict',stale.get('error'))
    r.check('stale request leaves full state unchanged',snap('after-stale-rejection')['xml']==s['xml'])
    if sys.argv[1] in ('observe-undo','verify-redo'):sys.exit(0)
    views=json.loads((prep/'baseline-views.json').read_text(encoding='utf-8-sig'))['data']['repeatableViews']
    capture('restored-views',s,views)
    r.call('history-after-native-undo','craft.history')
    d=r.call('status','designer.status')['data']
    r.check('one healthy aircraft after native Undo',d['sceneIntegrity']['status']=='healthy' and d['sceneIntegrity']['aircraftInstanceCount']==1)
    # Demonstrate further editing is safe, then recover that one new edit.
    x=r.call('next-edit','batch.apply',{**guard(s),'requestId':uuid.uuid4().hex,'operations':[
        {'kind':'shape.update','partId':4,'symmetric':False,'patch':{'length':1.1}}]});assert x['success'],x
    r.check('next edit succeeds',True)
    x=r.call('recover-next-edit','craft.undo',{**guard(x['data']),'requestId':uuid.uuid4().hex});assert x['success'],x
    r.check('further edit undo restores full state',audit(b['xml'],snap('final')['xml'])['equivalent'])
    s=snap('before-checkpoint-restore')
    x=r.call('rollback-pre-native-checkpoint','craft.rollback',{**guard(s),'requestId':uuid.uuid4().hex,'checkpointId':cp})
    r.check('checkpoint created before native Undo still works',x['success'],x.get('error'))
    assert x['success'],x
