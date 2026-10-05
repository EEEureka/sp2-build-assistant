"""Freeze E3 native UI targets and independently replay those changes via CLI."""
import json,math,sys,uuid
from precision_acceptance import Run,ROOT
from precision_diff import compare
r=Run(sys.argv[1]);prep=ROOT/sys.argv[2];identity=None
def call(label,cmd,args=None,**kw):
 x=r.call(label,cmd,args,**kw);assert x['success'],x;return x['data']
def snap(label):
 global identity
 s=call(label,'craft.snapshot',{'includeXml':True});identity=s['identity'];assert s['name']=='SP2Build 050 Precision Lab F2' and s['partCount']==8;return s
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def capture(label,views=None):return call(label,'designer.capture',{**guard(),'focusPartIds':[4,5,6,7,8],'views':views or [{'view':'right','projection':'orthographic'},{'view':'bottom','projection':'orthographic'},{'view':'custom','azimuthDegrees':45,'elevationDegrees':-25,'projection':'perspective'}],'resolution':{'width':1600,'height':1000}},images=True)
def mesh(label):
 call(label,'geometry.section',{**guard(),'partIds':[4,5,6,7,8],'frame':{'kind':'world'},'plane':{'origin':[0,0,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True)
 return json.loads(next((r.root/label).rglob('meshes.json')).read_text())
target=snap('native-target');operations=[];patches={};public={}
for pid in [5,6,7,8]:
 fields=call('native-properties-'+str(pid),'properties.get',{'id':pid,'limit':1000})['parts'][0]['fields']
 old=json.loads((prep/f'properties-{pid}.json').read_text())['data']['parts'][0]['fields'];old={f['propertyId']:f['value'] for f in old if f.get('valueAvailable')}
 editable={f['propertyId']:f['value'] for f in fields if f.get('writeOperation')=='properties.set' and f.get('valueAvailable')}
 patch={k:v for k,v in editable.items() if k in old and old[k]!=v and k not in ['GearBay[0].hingeAxisPose','GearBay[0].hingeAxisPose2']}
 if patch:operations.append({'kind':'properties.set','partId':pid,'patch':patch,'symmetric':False});patches[pid]=patch
 public[pid]=editable
assert set(patches)=={5,6,7},patches
(r.root/'observed-ui-changes.json').write_text(json.dumps(patches,indent=2))
gold_mesh=mesh('native-mesh');gold_views=capture('native-views')
cp=json.loads((prep/'fixture.json').read_text())['checkpointId']
call('reset','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});reset=snap('reset-baseline')
r.check('complete configured baseline restored',reset['xml']==json.loads((prep/'prepared.json').read_text())['data']['xml'])
call('replay-native-changes','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':operations});actual=snap('cli-target')
diff=compare(target['xml'],actual['xml']);r.check('native UI target state parity',not diff,diff)
am=mesh('cli-mesh');a=gold_mesh['meshes'];b=am['meshes']
top=len(a)==len(b) and all(x['partId']==y['partId'] and x['indices']==y['indices'] and len(x['vertices'])==len(y['vertices']) for x,y in zip(a,b))
error=max((math.dist(v,w) for x,y in zip(a,b) for v,w in zip(x['vertices'],y['vertices'])),default=0) if top else float('inf')
r.check('all actual target mesh vertices and indices',top and error<.0001,{'sameTopology':top,'maxMetres':error})
capture('cli-views',gold_views['repeatableViews'])
for pid in [5,6,7,8]:
 call('gold-ap-'+str(pid),'connections.points',{'part':pid});call('gold-geometry-'+str(pid),'parts.geometry',{'id':pid})
gold=snap('gold');cp2=call('gold-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'E3 gold'})['id']
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp2,'partIds':[4,5,6,7,8],'provenance':'Native templates plus CLI mounted fixture; actual native UI sets door thickness/height, gear support strut and torque-link length, wheel rim and friction. Developer-controlled sample, not blind agent test.'},indent=2))
(r.root/'public-target.json').write_text(json.dumps({'fields':public,'anchor':{'partId':5,'position':next(p['position'] for p in gold['parts'] if p['id']==5)},'tolerances':{'positionMetres':.0001,'scalar':1e-6,'rotationDegrees':.01}},indent=2))
