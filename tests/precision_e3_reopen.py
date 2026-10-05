"""Freeze the saved, currently open E3 reference in its new session."""
import json,sys,uuid
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1]);old=ROOT/sys.argv[2]
def call(n,c,a=None,**kw):
 x=r.call(n,c,a,**kw);assert x['success'],x;return x['data']
s=call('gold','craft.snapshot',{'includeXml':True});assert s['name']=='SP2Build 050 Precision Lab E3' and s['partCount']==8
i=s['identity'];guard={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
pub=json.loads((old/'public-target.json').read_text());pub['anchor']['position']=next(p['position'] for p in s['parts'] if p['id']==5)
for pid,values in pub['fields'].items():
 fs=call('reopen-properties-'+pid,'properties.get',{'id':int(pid),'fields':list(values)})['parts'][0]['fields']
 for f in fs:
  a,b=f['value'],values[f['propertyId']]
  assert abs(a-b)<1e-6 if isinstance(a,(int,float)) and not isinstance(a,bool) else a==b,(pid,f)
call('native-mesh','geometry.section',{**guard,'partIds':[4,5,6,7,8],'frame':{'kind':'world'},'plane':{'origin':[0,0,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True)
call('native-views','designer.capture',{**guard,'focusPartIds':[4,5,6,7,8],'views':[{'view':'right','projection':'orthographic'},{'view':'bottom','projection':'orthographic'},{'view':'custom','azimuthDegrees':45,'elevationDegrees':-25,'projection':'perspective'}],'resolution':{'width':1600,'height':1000}},images=True)
for pid in range(5,9):call('gold-ap-'+str(pid),'connections.points',{'part':pid});call('gold-geometry-'+str(pid),'parts.geometry',{'id':pid})
cp=call('gold-checkpoint','craft.checkpoint.create',{**guard,'requestId':uuid.uuid4().hex,'name':'E3 reopened native reference'})['id']
(r.root/'public-target.json').write_text(json.dumps(pub,indent=2));(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp,'nativeUiReference':sys.argv[2],'provenance':'Native saved E3 reopened; all public property targets checked unchanged. World anchor resampled to account for native AutoRecenter.'},indent=2))
call('status','designer.status')
