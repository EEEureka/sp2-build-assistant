"""Prepare a native UI parity fixture; intentionally leave it open for UI edits.
Use the recorded original checkpoint to remove all fixtures when finished.
"""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
base=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert base['name']=='SP2Build 050 Precision Lab F2' and len(base['parts'])==3
i=base['identity'];guard={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
cp=r.call('original-checkpoint','craft.checkpoint.create',{**guard,'requestId':uuid.uuid4().hex,'name':'F2 before mechanical parity'})['data']['id']
fixtures=[('piston','tpl-c2ea68c52a8d3473',[0,4.5,0]),('hinge','tpl-33195a9c4cfc6ff1',[0,1,0]),('engine','tpl-1a5ee3557bbab375',[4,4,0]),('gear','tpl-86c024231d5edb41',[-4,4,0]),('bay','tpl-0e1d278f1dc91cf6',[0,2.25,-2])]
x=r.call('add-fixtures','batch.apply',{**guard,'requestId':uuid.uuid4().hex,'operations':[{'kind':'part.add','templateId':t,'temporaryId':key,'position':pos} for key,t,pos in fixtures]})
assert x['success'],x
after=r.call('prepared','craft.snapshot',{'includeXml':True})['data']
for part in after['parts']:
 if part['id'] not in (1,2,3):r.call('properties-'+str(part['id']),'properties.get',{'id':part['id'],'limit':1000})
(r.root/'fixture.json').write_text(json.dumps({'originalCheckpointId':cp,'identity':after['identity'],'temporaryIds':x['data']['temporaryIds']},indent=2),encoding='utf-8')
r.call('prepared-status','designer.status')
