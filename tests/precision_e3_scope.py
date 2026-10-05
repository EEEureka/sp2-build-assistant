"""Mechanical mirrored assembly and explicit mounting/target scope acceptance."""
import json,math,sys,uuid,xml.etree.ElementTree as ET
from precision_acceptance import Run,ROOT
from review_restore_state import audit
r=Run(sys.argv[1]);gold=ROOT/sys.argv[2];ids=[4,5,6,7,8]
def call(n,c,a=None,**kw):
 x=r.call(n,c,a,**kw);assert x['success'],x;return x['data']
def guard():
 i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def write(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def snap(n):return call(n,'craft.snapshot',{'includeXml':True})
def props(p,patch,sym=False):return {'kind':'properties.set','partId':p,'patch':patch,'symmetric':sym}
def bindings(s):return {int(p.get('id')):[ET.tostring(n,encoding='unicode') for n in p if n.tag in ('Animator.State','InputController.State','PartTargeting.State')] for p in ET.fromstring(s['xml']).findall('./Assembly/Parts/Part')}
cp=json.loads((gold/'fixture.json').read_text())['checkpointId']
call('restore-gold','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});base=snap('baseline');assert base['partCount']==8
try:
 config=call('symmetry','symmetry.get')['configuration'];assert config['mode']=='Mirrored' and config['mirrorPlaneNormal']==[1,0,0] and config['mirrorPlaneDistance']==0
 result=write('mirror',[{'kind':'symmetry.create','partId':p} for p in ids]);peers={x['sourcePartId']:x['createdPartIds'][0] for x in result['actualChanges']};assert set(peers)==set(ids)
 (r.root/'peers.json').write_text(json.dumps(peers,indent=2))
 graph=call('graph','connections.list',{'view':'structured'})['connections'];exists={frozenset([c['partA'],c['partB']]) for c in graph}
 edges=[(peers[4],0,1,1),(peers[7],0,peers[4],4),(peers[5],0,peers[7],1),(peers[6],0,peers[5],1),(peers[8],1,peers[4],4)]
 write('mount-and-target',[{'kind':'connection.connect','partA':a,'attachPointA':ap,'partB':b,'attachPointB':bp,'symmetric':False} for a,ap,b,bp in edges if frozenset([a,b]) not in exists]+[props(peers[7],{'PartTargeting[0].customPartIds':[peers[4]]})])
 mounted=snap('mounted');by={p['id']:p for p in mounted['parts']}
 for p in ids:r.check('mirrored native mount '+str(p),math.dist(by[peers[p]]['position'],[-by[p]['position'][0],*by[p]['position'][1:]])<=.0001,{'source':by[p]['position'],'peer':by[peers[p]]['position']})
 frozen=bindings(mounted)
 changes={5:{'GearLeg[0].torqueLinkLength':.14},6:{'JWheelAssembly[0].width':.95},7:{'GearBay[0].doorThickness':.035},8:{'Piston[0].range':.35}}
 write('symmetric-properties',[props(p,patch,True) for p,patch in changes.items()])
 for p,patch in changes.items():
  for pid in (p,peers[p]):
   fs=call('read-'+str(pid),'properties.get',{'id':pid,'fields':list(patch)})['parts'][0]['fields'];r.check('symmetric property '+str(pid),all(abs(f['value']-patch[f['propertyId']])<=1e-6 for f in fs),fs)
 before=snap('before-motion');a={p['id']:p for p in before['parts']};delta=[.003,-.002,.004]
 write('symmetric-rigid-motion',[{'kind':'transform.apply','partIds':ids,'mode':'delta','translation':delta,'symmetric':True}]);after=snap('after-motion');b={p['id']:p for p in after['parts']}
 for p in ids:
  for pid,d in ((p,delta),(peers[p],[-delta[0],*delta[1:]])):
   e=math.dist(b[pid]['position'],[v+x for v,x in zip(a[pid]['position'],d)]);r.check('rigid delta '+str(pid),e<=.0001,e)
 r.check('all animation inputs targeting preserved',bindings(after)==frozen)
 r.check('outside group snapshot unchanged',all(a[p]==b[p] for p in (1,2,3)))
 for side in (ids,list(peers.values())):
  for i,p in enumerate(side):
   for q in side[i+1:]:r.check('pair distance '+str((p,q)),abs(math.dist(a[p]['position'],a[q]['position'])-math.dist(b[p]['position'],b[q]['position']))<=.0001)
 for label,scope in (('joint',ids+list(peers.values())),('source',ids),('peer',list(peers.values()))):
  call(label+'-views','designer.capture',{**guard(),'focusPartIds':scope,'views':[{'view':'front','projection':'orthographic'},{'view':'custom','azimuthDegrees':45,'elevationDegrees':-20,'projection':'perspective'}],'resolution':{'width':1600,'height':1000}},images=True)
finally:
 call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});end=snap('restored');result=audit(base['xml'],end['xml']);r.check('full reference restored',result['equivalent'],result)
 status=call('status','designer.status');r.check('scene healthy',status['sceneIntegrity']['status']=='healthy' and status['sceneIntegrity']['aircraftInstanceCount']==1)
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
