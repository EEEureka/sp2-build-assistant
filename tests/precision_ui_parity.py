"""Replay an already observed native UI target from an explicit fixture baseline.

This is developer UI parity, not blind agent target fitting. The native target
must have been produced through real UI actions before launching this script.
"""
import json,math,sys,uuid
from pathlib import Path
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1]);pid=int(sys.argv[2]);prep=ROOT/sys.argv[3]
mesh_ids=list(map(int,sys.argv[4].split(','))) if len(sys.argv)>4 else [pid]
baseline=json.loads((prep/'prepared.json').read_text(encoding='utf-8-sig'))['data']
fixture=json.loads((prep/'fixture.json').read_text(encoding='utf-8-sig')) if (prep/'fixture.json').exists() else {}
base_fields=json.loads((prep/('properties-'+str(pid)+'.json')).read_text(encoding='utf-8-sig'))['data']['parts'][0]['fields']
def snap(label):
 x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
 assert x['data']['name']=='SP2Build 050 Precision Lab F2';return x['data']
def guard():
 i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,patch):
 # Match the native UI sequence: disable automatic axes before editing their
 # conditional manual poses. Keep both steps in the same atomic batch.
 remaining=dict(patch);operations=[]
 auto_key='GearBay[0].autoHingeAxis'
 if remaining.get(auto_key) is False and any(k in remaining for k in ('GearBay[0].hingeAxisPose','GearBay[0].hingeAxisPose2')):
  operations.append({'kind':'properties.set','partId':pid,'patch':{auto_key:remaining.pop(auto_key)},'symmetric':False})
 if remaining:operations.append({'kind':'properties.set','partId':pid,'patch':remaining,'symmetric':False})
 x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':operations});assert x['success'],x
 return x
def restore(label,patch):
 cpfile=prep/'fixture.json'
 cp=json.loads(cpfile.read_text(encoding='utf-8-sig')).get('checkpointId') if cpfile.exists() else None
 if cp:
  x=r.call(label,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert x['success'],x
 else:apply(label,patch)
def capture(label,views=None):
 x=r.call(label,'designer.capture',{**guard(),'focusPartIds':mesh_ids,'views':views or [{'view':'front','projection':'orthographic'},{'view':'right','projection':'orthographic'},{'view':'custom','azimuthDegrees':35,'elevationDegrees':20,'projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True);assert x['success'],x
 return x['data']
def meshes(label):
 x=r.call(label,'geometry.section',{**guard(),'partIds':mesh_ids,'frame':{'kind':'world'},'plane':{'origin':[0,0,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True);assert x['success'],x
 f=next((r.root/label).rglob('meshes.json'));return json.loads(f.read_text(encoding='utf-8-sig'))
def rays(label):
 result=[]
 for index,query in enumerate(fixture.get('parityRays',[])):
  x=r.call(label+'-'+str(index),'designer.raycast',query);assert x['success'],x;result.append(x['data']['hits'])
 return result
gold=snap('native-target')
native=r.call('native-properties','properties.get',{'id':pid,'limit':1000})['data']['parts'][0]['fields']
old={f['propertyId']:f['value'] for f in base_fields if f['writeOperation']=='properties.set' and f['valueAvailable']}
new={f['propertyId']:f['value'] for f in native if f['propertyId'] in old and f['valueAvailable']}
patch={k:v for k,v in new.items() if v!=old[k]};reset={k:old[k] for k in patch}
# Automatic hinge poses are callback outputs, not edits performed in the UI.
# They remain included in the complete XML and mesh comparisons below.
derived={}
if new.get('GearBay[0].autoHingeAxis') is True:
 for key in ('GearBay[0].hingeAxisPose','GearBay[0].hingeAxisPose2'):
  if key in patch:derived[key]=patch.pop(key);reset.pop(key)
assert patch,'No native UI change observed'
(r.root/'observed-ui-changes.json').write_text(json.dumps({'target':patch,'baseline':reset,'nativeDerivedValuesComparedButNotAssigned':derived},indent=2),encoding='utf-8')
views=[{'view':'back','projection':'orthographic'},{'view':'right','projection':'orthographic'},{'view':'custom','azimuthDegrees':215,'elevationDegrees':20,'projection':'perspective'}] if 'GearBay[0].autoHingeAxis' in new else None
views=fixture.get('views',views)
gold_views=capture('native-views',views);gold_mesh=meshes('native-mesh')
gold_rays=rays('native-rays')
restore('reset-fields',reset)
r.check('reset to complete fixture baseline',snap('reset-baseline')['xml']==baseline['xml'])
rays('baseline-rays')
apply('replay-native-target',patch)
actual=snap('cli-target')
r.check('complete native UI target XML parity',gold['xml']==actual['xml'])
actual_mesh=meshes('cli-mesh')
a=gold_mesh['meshes'];b=actual_mesh['meshes']
topology=len(a)==len(b) and all(x['indices']==y['indices'] and x['partId']==y['partId'] and len(x['vertices'])==len(y['vertices']) for x,y in zip(a,b))
error=max((math.dist(v,w) for x,y in zip(a,b) for v,w in zip(x['vertices'],y['vertices'])),default=float('inf')) if topology else float('inf')
r.check('full native mesh matches within 0.1mm',topology and error<=.0001,{'sameTopology':topology,'maxVertexErrorMetres':error,'exclusionsNative':gold_mesh['exclusions'],'exclusionsCli':actual_mesh['exclusions']})
actual_rays=rays('cli-rays')
if gold_rays:r.check('native UI and CLI ray hits exactly match',gold_rays==actual_rays,{'native':gold_rays,'cli':actual_rays})
capture('cli-views',gold_views['repeatableViews'])
r.call('cli-geometry','parts.geometry',{'id':pid})
restore('restore-fixture-fields',reset)
r.check('complete fixture restored',snap('restored')['xml']==baseline['xml'])
r.call('final-status','designer.status')
