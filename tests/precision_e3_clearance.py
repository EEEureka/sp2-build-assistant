"""Correct E3 mounting from measured retracted native mesh extents.

Initial wheel min-X 2.3425 lies outside bay min-X 2.95; support min-Y
5.3177 intersects closed door Y=5.40..5.4303. Move the complete native
leg/wheel pair +0.7 X/+0.15 Y, then recheck both UI endpoints.
"""
import json,sys,uuid
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1]);old=ROOT/sys.argv[2]
def call(label,cmd,args=None,**kw):
 x=r.call(label,cmd,args,**kw);assert x['success'],x;return x['data']
def guard():
 i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
cp=json.loads((old/'fixture.json').read_text())['checkpointId']
call('restore-reference','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
call('mount-correction','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{'kind':'transform.apply','partIds':[5,6],'mode':'delta','translation':[.7,.15,0],'symmetric':False}]})
s=call('gold','craft.snapshot',{'includeXml':True});assert s['name']=='SP2Build 050 Precision Lab F2' and s['partCount']==8
call('native-mesh','geometry.section',{**guard(),'partIds':[4,5,6,7,8],'frame':{'kind':'world'},'plane':{'origin':[0,0,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True)
call('native-views','designer.capture',{**guard(),'focusPartIds':[4,5,6,7,8],'views':[{'view':'right','projection':'orthographic'},{'view':'bottom','projection':'orthographic'},{'view':'custom','azimuthDegrees':45,'elevationDegrees':-25,'projection':'perspective'}],'resolution':{'width':1600,'height':1000}},images=True)
for pid in range(5,9):
 call('gold-ap-'+str(pid),'connections.points',{'part':pid});call('gold-geometry-'+str(pid),'parts.geometry',{'id':pid})
cp2=call('gold-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'E3 mounting corrected reference'})['id']
pub=json.loads((old/'public-target.json').read_text());pub['anchor']['position']=next(p['position'] for p in s['parts'] if p['id']==5)
(r.root/'public-target.json').write_text(json.dumps(pub,indent=2))
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp2,'partIds':[4,5,6,7,8],'nativeUiReference':sys.argv[2],'provenance':'Same six native UI property targets; leg/wheel +0.7X,+0.15Y from observed retracted extents. Both corrected endpoints still require verification.'},indent=2))
