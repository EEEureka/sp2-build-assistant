"""Observe a real UI reload of the SAME saved F2; never open a save via API."""
import json, sys, uuid
from precision_acceptance import Run, ROOT
from review_restore_state import audit

r=Run(sys.argv[2])
s=r.call('snapshot','craft.snapshot',{'includeXml':True})['data']
assert s['name']=='SP2Build 050 Precision Lab F2' and s['partCount']==3
i=s['identity'];g={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
assert not i['stateUncertain']
if sys.argv[1]=='prepare':
    cp=r.call('checkpoint','craft.checkpoint.create',{**g,'requestId':uuid.uuid4().hex,'name':'same saved craft reload boundary'})
    assert cp['success'],cp
else:
    old=ROOT/sys.argv[3]
    b=json.loads((old/'snapshot.json').read_text(encoding='utf-8-sig'))['data']
    cp=json.loads((old/'checkpoint.json').read_text(encoding='utf-8-sig'))['data']['id']
    r.check('native reload restores saved baseline',audit(b['xml'],s['xml'])['equivalent'])
    r.check('same craft reload starts a new session',i['craftSessionId']!=b['identity']['craftSessionId'])
    cps=r.call('checkpoints','craft.checkpoint.list')['data']['checkpoints']
    r.check('previous session checkpoint is unavailable',all(x['id']!=cp for x in cps))
    old_guard={'craftSessionId':b['identity']['craftSessionId'],'expectedRevision':b['identity']['revision']}
    x=r.call('stale-session','batch.apply',{**old_guard,'requestId':uuid.uuid4().hex,'operations':[
        {'kind':'shape.update','partId':1,'symmetric':False,'patch':{'length':1.1}}]})
    r.check('old session cannot edit reloaded craft',not x['success'] and x.get('error',{}).get('code')=='session_conflict',x.get('error'))
    x=r.call('expired-checkpoint','craft.rollback',{**g,'requestId':uuid.uuid4().hex,'checkpointId':cp})
    r.check('expired checkpoint cannot restore into new session',not x['success'] and x.get('error',{}).get('code')=='checkpoint_not_found',x.get('error'))
    after=r.call('after-rejections','craft.snapshot',{'includeXml':True})['data']
    r.check('all rejections leave reloaded craft untouched',s['xml']==after['xml'])
