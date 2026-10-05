"""E2 native mirrored pod, explicit projector targets and local material scope.

Uses the global launcher only. A single native wing remains a frozen independent
reference; this does not certify mirroring a wing and its dependent controls.
"""
import json, math, sys, uuid, xml.etree.ElementTree as ET
from precision_acceptance import Run
from review_restore_state import audit

r=Run(sys.argv[1]); group=[7,8,9,10,11]
def call(label,cmd,args=None,**kw):
    a=r.call(label,cmd,args,**kw);assert a['success'],a;return a['data']
def snap(label):
    d=call(label,'craft.snapshot',{'includeXml':True})
    assert d['name']=='SP2Build 050 Precision Lab F2' and not d['identity']['stateUncertain'];return d
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity']
    return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def write(label,ops):return call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def prop(p,patch,symmetric=False):return {'kind':'properties.set','partId':p,'patch':patch,'symmetric':symmetric}
def poses(s):return {p['id']:p for p in s['parts']}
def norm(q):return [x/math.sqrt(sum(v*v for v in q)) for x in q]
def mul(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def inv(q):return [-q[0],-q[1],-q[2],q[3]]
def rot(q,v):return mul(mul(norm(q),[*v,0]),inv(norm(q)))[:3]
def add(a,b):return [x+y for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def reflect(v):return [-v[0],v[1],v[2]]
def angle(a,b):
    a=norm(a);b=norm(b)
    return math.degrees(4*math.asin(min(1,min(math.dist(a,b),math.dist(a,[-v for v in b]))/2)))
def bindings(s):
    return {int(p.get('id')):[ET.tostring(n,encoding='unicode') for n in p if n.tag in ('Animator.State','InputController.State','PartTargeting.State')] for p in ET.fromstring(s['xml']).findall('./Assembly/Parts/Part')}
def capture(label,ids,views):return call(label,'designer.capture',{**guard(),'focusPartIds':ids,'views':views,'resolution':{'width':1600,'height':1000}},images=True)
base=snap('baseline');assert base['partCount']==11
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'E2 mirror scope baseline'})['id']
try:
    config=call('symmetry-before','symmetry.get')['configuration']
    assert config['mode']=='Mirrored' and config['mirrorPlaneNormal']==[1,0,0] and config['mirrorPlaneDistance']==0
    out=write('mirror-pod',[{'kind':'symmetry.create','partId':p} for p in group])
    peers={a['sourcePartId']:a['createdPartIds'][0] for a in out['actualChanges'] if a['kind']=='symmetry.create'}
    assert len(peers)==5 and all(len(a['createdPartIds'])==1 for a in out['actualChanges'])
    (r.root/'peers.json').write_text(json.dumps(peers,indent=2))
    points=call('connections-after-create','connections.list',{'view':'structured'})['connections']
    existing={frozenset([c['partA'],c['partB']]) for c in points}
    edges=[(peers[7],0,peers[8],0),(peers[8],1,peers[9],0),(peers[9],1,1,1),(peers[10],0,peers[9],0),(peers[11],0,peers[9],0)]
    before=snap('before-mirror-connect')
    write('connect-and-target-mirror',[{'kind':'connection.connect','partA':a,'attachPointA':ap,'partB':b,'attachPointB':bp,'symmetric':False} for a,ap,b,bp in edges if frozenset([a,b]) not in existing]+
          [prop(peers[p],{'PartTargeting[0].customPartIds':[peers[9]]}) for p in (10,11)])
    after=snap('after-mirror-connect');a=poses(before);b=poses(after)
    r.check('mirror connect does not snap any part',all(a[p]['position']==b[p]['position'] and a[p]['rotationQuaternion']==b[p]['rotationQuaternion'] for p in a))
    for p in group:r.check('native mirrored position '+str(p),math.dist(b[peers[p]]['position'],reflect(b[p]['position']))<=.0001)
    frozen_bindings=bindings(after)
    write('symmetric-dimensions',[prop(8,{'JetEngineShroud[0].length':1.12},True),prop(10,{'TextDecal[0].Width':1.15},True),prop(11,{'TextureDecal[0].Width':1.15},True)])
    for p,key,value in ((8,'JetEngineShroud[0].length',1.12),(10,'TextDecal[0].Width',1.15),(11,'TextureDecal[0].Width',1.15)):
        for pid in (p,peers[p]):
            fields=call('fields-'+str(pid),'properties.get',{'id':pid,'fields':[key]+(['PartTargeting[0].customPartIds'] if p!=8 else [])})['parts'][0]['fields']
            values={f['propertyId']:f['value'] for f in fields}
            r.check('symmetric effective dimension '+str(pid),abs(values[key]-value)<=1e-6,values)
            if p!=8:r.check('target stays on its own side '+str(pid),values['PartTargeting[0].customPartIds']==[9 if pid==p else peers[9]],values)
    allids=list(poses(after));old=call('appearance-before','appearance.get',{'partIds':allids})
    pylon=next(p for p in old['parts'] if p['partId']==9);slots=[s['slot'] for s in pylon['slots'] if s['assignable']];material=next(s['materialId'] for s in pylon['slots'] if s['assignable'])
    out=write('color-only-source-pylon',[{'kind':'appearance.set','mode':'clone','materialId':material,'partIds':[9],'slots':slots,'patch':{'name':'E2 local pylon only','style':'SolidColor','colors':[{'index':0,'rgba':[.15,.42,.72,1]}],'metallic':.15,'smoothness':.35}}])
    new=call('appearance-after','appearance.get',{'partIds':allids});byold={p['partId']:p for p in old['parts']};bynew={p['partId']:p for p in new['parts']}
    r.check('material reports only requested part',out['actualChanges'][0]['affectedPartIds']==[9],out['actualChanges'])
    r.check('all other material slots unchanged including mirrored pylon',all(byold[p]['slots']==bynew[p]['slots'] for p in allids if p!=9))
    r.check('global theme unchanged',old['globalCustomThemeFingerprint']==new['globalCustomThemeFingerprint'])
    before=snap('before-rigid-motion');prior=poses(before);q=norm(prior[9]['rotationQuaternion']);origin=prior[9]['position']
    dq=[0,math.sin(math.radians(.2)/2),0,math.cos(math.radians(.2)/2)];pivot=[-1.5,.75,.2];translation=[.005,-.003,.002]
    op={'kind':'transform.apply','partIds':group,'anchorPartId':9,'mode':'delta','frame':{'kind':'custom','position':origin,'rotationQuaternion':q},'pivot':pivot,'translation':translation,'rotationQuaternion':dq,'symmetric':True}
    write('mirrored-local-rigid-motion',[op]);after=snap('after-rigid-motion');post=poses(after)
    world_pivot=add(origin,rot(q,pivot));world_shift=rot(q,translation);world_dq=mul(mul(q,dq),inv(q))
    for p in group:
        expected=add(add(world_pivot,rot(world_dq,sub(prior[p]['position'],world_pivot))),world_shift)
        for pid,target in ((p,expected),(peers[p],reflect(expected))):r.check('external pivot numeric position '+str(pid),math.dist(post[pid]['position'],target)<=.0001,{'actual':post[pid]['position'],'expected':target})
        r.check('source rotation '+str(p),angle(post[p]['rotationQuaternion'],mul(world_dq,prior[p]['rotationQuaternion']))<=.01)
        mdq=[world_dq[0],-world_dq[1],-world_dq[2],world_dq[3]]
        r.check('peer rotation '+str(p),angle(post[peers[p]]['rotationQuaternion'],mul(mdq,prior[peers[p]]['rotationQuaternion']))<=.01)
    mutable=group+list(peers.values())
    r.check('outside motion scope exactly unchanged',all(prior[p]==post[p] for p in prior if p not in mutable))
    r.check('all targeting animation and inputs unchanged',bindings(after)==frozen_bindings)
    for side in (group,list(peers.values())):
        for i,p in enumerate(side):
            for pp in side[i+1:]:r.check('rigid distance '+str(p)+'-'+str(pp),abs(math.dist(prior[p]['position'],prior[pp]['position'])-math.dist(post[p]['position'],post[pp]['position']))<=.0001)
    capture('joint-mirrored',list(range(4,12))+list(peers.values()),[{'view':'front','projection':'orthographic'},{'view':'top','projection':'orthographic'},{'view':'isometric','projection':'perspective'}])
    capture('source-detail',group,[{'view':'left','projection':'orthographic'},{'view':'custom','azimuthDegrees':-65,'elevationDegrees':12,'projection':'perspective'}])
    capture('peer-detail',list(peers.values()),[{'view':'right','projection':'orthographic'},{'view':'custom','azimuthDegrees':65,'elevationDegrees':12,'projection':'perspective'}])
finally:
    call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
    end=snap('restored');review=audit(base['xml'],end['xml']);(r.root/'restore-audit.json').write_text(json.dumps(review,indent=2))
    r.check('full baseline restored by independent audit',review['equivalent'],review)
    status=call('status','designer.status');r.check('one healthy scene',status['sceneIntegrity']['status']=='healthy' and status['sceneIntegrity']['aircraftInstanceCount']==1)
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
