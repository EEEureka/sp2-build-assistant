"""Add a connected, explicitly targeted substrate for real gear-door UI parity."""
import sys, uuid, json
from precision_acceptance import Run
r=Run(sys.argv[1])
def snap(label):
 x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
 assert x['data']['name']=='SP2Build 050 Precision Lab F2'
 return x['data']
def guard():
 i=snap('guard-'+str(len(r.calls)))['identity']
 return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex}
def apply(label,ops):
 x=r.call(label,'batch.apply',{**guard(),'operations':ops});assert x['success'],x
 return x['data']
base=snap('baseline');assert len(base['parts'])==10
cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'name':'Before gear bay substrate'})['data']['id']
host=apply('add-host',[{'kind':'part.add','templateId':'tpl-f748657136c8ca1a','temporaryId':'host','position':[0,2.25,-1.5]}])['temporaryIds']['host']
apply('prepare-host',[
 {'kind':'shape.update','partId':host,'symmetric':False,'patch':{'length':1,'autoResize':False,'sections':[{'index':i,'width':1.4,'height':2.4,'smoothing':False,'syncAdjacent':False} for i in (0,1)]}},
 {'kind':'connection.connect','partA':host,'partB':1,'attachPointA':0,'attachPointB':1,'symmetric':False},
 {'kind':'connection.connect','partA':10,'partB':host,'attachPointA':0,'attachPointB':1,'symmetric':False},
 {'kind':'part.update','partId':10,'changes':[{'path':'Part','attribute':'position','value':'0,2.25,-2.01'}]},
 {'kind':'properties.set','partId':10,'patch':{'PartTargeting[0].targetMode':'Custom'},'symmetric':False},
 {'kind':'properties.set','partId':10,'patch':{'PartTargeting[0].customPartIds':[host]},'symmetric':False}])
snap('prepared')
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp,'hostId':host}),encoding='utf-8')
r.call('bay-properties','properties.get',{'id':10,'limit':1000})
r.call('status','designer.status')
