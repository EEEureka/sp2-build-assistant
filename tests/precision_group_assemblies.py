"""Live native assemblies with independent rigid-pose and mesh oracles.

Runs on the disposable F2 fixture and restores it in finally. No UI gold claim.
"""
import json, math, sys, uuid, xml.etree.ElementTree as ET
from precision_acceptance import Run

r=Run(sys.argv[1])
def snap(label):
    a=r.call(label,'craft.snapshot',{'includeXml':True});assert a['success'],a
    assert a['data']['name']=='SP2Build 050 Precision Lab F2'
    return a['data']
def guard():
    i=snap('guard-'+str(len(r.calls)))['identity']
    return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops):
    a=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert a['success'],a
    return a['data']
def qm(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def rotate(q,v):return qm(qm(q,[*v,0]),[-q[0],-q[1],-q[2],q[3]])[:3]
def qa(a,b):
    a=[v/math.sqrt(sum(x*x for x in a)) for v in a];b=[v/math.sqrt(sum(x*x for x in b)) for v in b]
    return math.degrees(4*math.asin(min(1,min(math.dist(a,b),math.dist(a,[-v for v in b]))/2)))
def frozen(xml):
    root=ET.fromstring(xml)
    return {p.attrib['id']:[ET.tostring(x,encoding='unicode') for x in p if x.tag in ('Animator.State','InputController.State')]
            for p in root.findall('./Assembly/Parts/Part')}
def mesh(label,ids):
    a=r.call(label,'geometry.section',{**guard(),'partIds':ids,'plane':{'origin':[0,2,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True);assert a['success'],a
    return json.loads(next((r.root/label).rglob('meshes.json')).read_text(encoding='utf-8-sig'))['meshes']

baseline=snap('baseline');assert baseline['partCount']==3
cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'native groups original'})['data']['id']
try:
    fixtures={}
    for name,tpl,pos in [('wing','tpl-1bdb332430679d47',[4,2.25,0]),('engine','tpl-1a5ee3557bbab375',[4,0,-3]),('gear','tpl-86c024231d5edb41',[-4,2,0])]:
        before=snap(name+'-before-add');previous={p['id'] for p in before['parts']}
        a=apply(name+'-add',[{'kind':'part.add','templateId':tpl,'position':pos,'temporaryId':name}])
        after=snap(name+'-added');ids=sorted(p['id'] for p in after['parts'] if p['id'] not in previous)
        root=a['temporaryIds'][name];fixtures[name]={'ids':ids,'root':root}
        mounts=[]
        for pid in ids:
            points=r.call(name+'-mounts-'+str(pid),'connections.points',{'part':pid});assert points['success'],points
            def normal(p):
                if 'seekTypes' in p:return 'Normal' in p['seekTypes']
                value=p['seekType']
                return bool(int(value)&1) if value.isdecimal() else 'Normal' in value.split(', ')
            mounts.extend((pid,p['id']) for p in points['data']['points'] if (p['available'] or p['allowMultiple']) and p['allowManualConnection'] and normal(p))
        assert mounts, 'No reported available Normal mounting point for '+name
        pid,ap=mounts[0]
        apply(name+'-connect',[{'kind':'connection.connect','partA':pid,'partB':1,'attachPointA':ap,'attachPointB':1,'symmetric':False}])
    for name,f in fixtures.items():
        ids=f['ids'];root=f['root'];before=snap(name+'-before');by={p['id']:p for p in before['parts']}
        resolved=r.call(name+'-group','groups.resolve',{**guard(),'selector':{'kind':'parts','partIds':ids}});assert resolved['success'],resolved
        r.check(name+' complete group resolves',sorted(resolved['data']['partIds'])==ids)
        if name=='wing':
            partial=r.call('wing-incomplete','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{'kind':'transform.apply','partIds':[root],'mode':'delta','translation':[.1,0,0]}]})
            r.check('wing missing controls rejected',not partial['success'] and partial['error']['code']=='incomplete_native_group',partial.get('error'))
            r.check('wing rejected move preserves XML',snap('wing-after-rejection')['xml']==before['xml'])
        original_mesh=mesh(name+'-mesh-before',ids)
        q=[0,math.sin(math.radians(.2)/2),0,math.cos(math.radians(.2)/2)];pivot=[2,3,-1];delta=[.005,.002,0]
        def point(v):return [p+d+x for p,d,x in zip(pivot,delta,rotate(q,[x-p for x,p in zip(v,pivot)]))]
        edited=apply(name+'-rigid-move',[{'kind':'transform.apply','partIds':ids,'mode':'delta','frame':{'kind':'world'},'pivot':pivot,'translation':delta,'rotationQuaternion':q,'symmetric':False}])
        after=snap(name+'-after');post={p['id']:p for p in after['parts']}
        for pid in ids:
            dp=math.dist(post[pid]['position'],point(by[pid]['position']));dq=qa(post[pid]['rotationQuaternion'],qm(q,by[pid]['rotationQuaternion']))
            r.check(name+' rigid pose '+str(pid),dp<=.0001 and dq<=.01,{'metres':dp,'degrees':dq})
            r.check(name+' scale '+str(pid),post[pid]['scale']==by[pid]['scale'])
        r.check(name+' outside poses fixed',all(by[p]['position']==post[p]['position'] and qa(by[p]['rotationQuaternion'],post[p]['rotationQuaternion'])<1e-6 for p in by if p not in ids))
        r.check(name+' Animator and Input preserved',frozen(before['xml'])==frozen(after['xml']))
        changed_mesh=mesh(name+'-mesh-after',ids)
        topology=len(changed_mesh)==len(original_mesh) and all(a['partId']==b['partId'] and a['indices']==b['indices'] and len(a['vertices'])==len(b['vertices']) for a,b in zip(changed_mesh,original_mesh))
        err=max((math.dist(a,point(b)) for n,o in zip(changed_mesh,original_mesh) for a,b in zip(n['vertices'],o['vertices'])),default=0) if topology else float('inf')
        r.check(name+' all native meshes move rigidly',topology and err<=.0001,{'topology':topology,'maxVertexErrorMetres':err})
        capture=r.call(name+'-native','designer.capture',{**guard(),'focusPartIds':ids,'views':[{'view':'isometric','projection':'perspective'},{'view':'front','projection':'orthographic'}],'resolution':{'width':1280,'height':800}},images=True);assert capture['success'],capture
        r.call(name+'-points','connections.points',{'part':root})
        restored=r.call(name+'-reset','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':edited['beforeCheckpointId']});assert restored['success'],restored
        r.check(name+' precise restore',snap(name+'-restored')['xml']==before['xml'])
finally:
    a=r.call('restore-original','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert a['success'],a
    r.check('original complete XML restored',snap('final')['xml']==baseline['xml'])
    r.call('final-status','designer.status')
