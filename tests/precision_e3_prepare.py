"""Create a compact E3 discovery fixture in the explicitly opened F2 test copy.

The native GL-Wing template supplies real Start/End animation. Do not replace
Animator state to invent test motion. This phase leaves the fixture for review.
"""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def call(label,cmd,args=None,**kw):
    x=r.call(label,cmd,args,**kw);assert x['success'],x;return x['data']
def snap(label):return call(label,'craft.snapshot',{'includeXml':True})
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def write(label,ops):return call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
base=snap('baseline');assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'Before E3 fixture'})['id']
templates=[('host','tpl-f748657136c8ca1a',[4,6,0]),('gear','tpl-15efcc98ec77cf43',[4,5.7,0]),('bay','tpl-0e1d278f1dc91cf6',[4,5.39,0]),('piston','tpl-c2ea68c52a8d3473',[4.3,5.3,.7])]
try:
    for key,tid,_ in templates:call('template-'+key,'catalog.get',{'id':tid})
    out=write('add-fixture',[{'kind':'part.add','templateId':tid,'temporaryId':key,'position':pos} for key,tid,pos in templates]);ids=out['temporaryIds']
    write('size-host',[{'kind':'shape.update','partId':ids['host'],'symmetric':False,'patch':{'autoResize':False,'length':3.5,'sections':[{'index':i,'width':1.8,'height':1.2,'smoothing':False,'syncAdjacent':False} for i in (0,1)]}}])
    s=snap('prepared');added=[p['id'] for p in s['parts'] if p['id'] not in (1,2,3)]
    for p in added:
        call('properties-'+str(p),'properties.get',{'id':p,'limit':1000})
        call('mounts-'+str(p),'connections.points',{'part':p})
        call('geometry-'+str(p),'parts.geometry',{'id':p})
    call('connections','connections.list',{'view':'structured'})
    (r.root/'fixture.json').write_text(json.dumps({'baselineCheckpointId':cp,'ids':ids,'added':added,'provenance':'CLI primitives; native GL-Wing animator preserved; pending mount review and native UI target'},indent=2))
except BaseException:
    call('failed-prepare-restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});raise
