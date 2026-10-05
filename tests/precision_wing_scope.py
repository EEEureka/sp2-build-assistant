"""Native wing/control mirror scopes and ordered edits; F2-only, full restore.

The mesh oracle applies an independent rigid matrix to every exported vertex.
These checks are not a native-UI parameter-parity claim.
"""
import json, math, sys, uuid, xml.etree.ElementTree as ET
from precision_acceptance import Run
from review_restore_state import audit

r = Run(sys.argv[1])
def call(n,c,a=None,**kw):
    x=r.call(n,c,a,**kw); assert x['success'], x; return x['data']
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity']
    return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def snap(n): return call(n,'craft.snapshot',{'includeXml':True})
def write(n,ops): return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def checkpoint(n): return call(n,'craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':n})['id']
def restore(n,cp): return call(n,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
def meshes(n,ids):
    call(n,'geometry.section',{**guard(),'partIds':ids,'plane':{'origin':[0,2,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True)
    return json.loads(next((r.root/n).rglob('meshes.json')).read_text(encoding='utf-8-sig'))['meshes']
def qm(a,b):
    x,y,z,w=a; X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def rot(q,v): return qm(qm(q,[*v,0]),[-q[0],-q[1],-q[2],q[3]])[:3]
def flip(v): return [-v[0],v[1],v[2]]
def bindings(s):
    return {int(p.get('id')):[ET.tostring(x,encoding='unicode') for x in p if x.tag in ('Animator.State','InputController.State')] for p in ET.fromstring(s['xml']).findall('./Assembly/Parts/Part')}
def byid(s): return {p['id']:p for p in s['parts']}
def verify_move(n,ids,point):
    before=snap(n+'-before'); mb=meshes(n+'-mesh-before',ids)
    out=write(n,[operations[n]])
    after=snap(n+'-after'); ma=meshes(n+'-mesh-after',ids)
    a,b=byid(before),byid(after)
    for pid in ids:
        err=math.dist(b[pid]['position'],point(pid,a[pid]['position']))
        r.check(n+' position '+str(pid),err<=.0001,err)
    r.check(n+' outside unchanged',all(a[p]==b[p] for p in a if p not in ids))
    r.check(n+' inputs/animation unchanged',bindings(before)==bindings(after))
    topology=len(ma)==len(mb) and all(x['partId']==y['partId'] and x['indices']==y['indices'] and len(x['vertices'])==len(y['vertices']) for x,y in zip(ma,mb))
    error=max((math.dist(x,point(m['partId'],y)) for m,o in zip(ma,mb) for x,y in zip(m['vertices'],o['vertices'])),default=0) if topology else float('inf')
    r.check(n+' every mesh vertex rigid',topology and error<=.0001,{'topology':topology,'maxMetres':error})
    actual=out['actualChanges'][0]['partIds']
    r.check(n+' affected once',len(actual)==len(set(actual)) and set(actual)==set(ids),actual)
    call(n+'-native','designer.capture',{**guard(),'focusPartIds':allids,'views':[{'view':'top','projection':'orthographic'},{'view':'isometric','projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True)
    restore(n+'-restore',cp)
    proof=audit(mounted['xml'],snap(n+'-restored')['xml']); r.check(n+' full restoration',proof['equivalent'],proof)

base=snap('baseline');assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
original=checkpoint('original')
try:
    added=write('add-wing',[{'kind':'part.add','templateId':'tpl-1bdb332430679d47','temporaryId':'wing','position':[2,2.25,0]}])
    root=added['temporaryIds']['wing']; source=sorted(set(byid(snap('source')))-set(byid(base)))
    write('mount-wing',[{'kind':'connection.connect','partA':root,'attachPointA':0,'partB':1,'attachPointB':1,'symmetric':False}])
    graph=call('source-graph','connections.list',{'view':'structured'})['connections']
    config=call('mirror-config','symmetry.get')['configuration'];assert config['mirrorPlaneNormal']==[1,0,0] and config['mirrorPlaneDistance']==0
    out=write('create-peers',[{'kind':'symmetry.create','partId':p} for p in source])
    peers={c['sourcePartId']:c['createdPartIds'][0] for c in out['actualChanges']};allids=source+list(peers.values())
    edges=[]
    now=call('peer-graph','connections.list',{'view':'structured'})['connections'];existing={frozenset([c['partA'],c['partB']]) for c in now}
    for c in graph:
        if c['partA'] in source and c['partB'] in source:
            a,b=peers[c['partA']],peers[c['partB']]
            if frozenset([a,b]) not in existing:
                ap,bp=c['attachPointsA'][0],c['attachPointsB'][0]
                # Connection rows are undirected topology. Creation is directed:
                # the control seeks a wing surface receiver, never vice versa.
                if c['partA']==root:a,b,ap,bp=b,a,bp,ap
                edges.append({'kind':'connection.connect','partA':a,'partB':b,'attachPointA':ap,'attachPointB':bp,'symmetric':False})
    host_points=call('host-free-mounts','connections.points',{'part':1})['points']
    host_ap=next(p['id'] for p in host_points if p['allowManualConnection'] and (p['available'] or p['allowMultiple']) and 'Normal' in p['receiveTypes'])
    edges.append({'kind':'connection.connect','partA':peers[root],'attachPointA':0,'partB':1,'attachPointB':host_ap,'symmetric':False})
    write('mount-peers',edges)
    mounted=snap('mounted');cp=checkpoint('mounted-checkpoint')
    (r.root/'fixture.json').write_text(json.dumps({'source':source,'peers':peers,'originalCheckpointId':original,'checkpointId':cp},indent=2))
    for p in source:
        r.check('initial mirror '+str(p),math.dist(byid(mounted)[peers[p]]['position'],flip(byid(mounted)[p]['position']))<=.0001)
    for label,scope,error,sym in [('overlap',allids,'symmetry_scope_overlap',True),('missing-control',[root],'incomplete_native_group',False)]:
        x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{'kind':'transform.apply','partIds':scope,'mode':'delta','translation':[.01,0,0],'symmetric':sym}]})
        r.check(label+' explicit rejection',not x['success'] and x['error']['code']==error,x.get('error'))
        proof=audit(mounted['xml'],snap(label+'-after')['xml']);r.check(label+' unchanged',proof['equivalent'],proof)
    q=[0,math.sin(math.radians(.2)/2),0,math.cos(math.radians(.2)/2)];pivot=[1.1,3.2,-.7];delta=[.003,-.002,.004]
    def point(v): return [x+p+d for x,p,d in zip(rot(q,[x-p for x,p in zip(v,pivot)]),pivot,delta)]
    move={'kind':'transform.apply','partIds':source,'mode':'delta','pivot':pivot,'translation':delta,'rotationQuaternion':q}
    operations={'one-side':{**move,'symmetric':False},'mirrored':{**move,'symmetric':True},'both-explicit':{**move,'partIds':allids,'symmetric':False}}
    verify_move('one-side',source,lambda pid,v:point(v))
    verify_move('mirrored',allids,lambda pid,v:point(v) if pid in source else flip(point(flip(v))))
    verify_move('both-explicit',allids,lambda pid,v:point(v))
    shape=call('wing-before-shape','shape.get',{'id':root})['shape']
    op={'kind':'shape.update','partId':root,'patch':{'sections':[{'index':0,'chord':2.13},{'index':1,'chord':.93} ]},'symmetric':True}
    write('symmetric-chord',[op])
    for pid in [root,peers[root]]:
        s=call('chord-'+str(pid),'shape.get',{'id':pid})['shape'];sections=s['configuration']['sections'];r.check('symmetric chord '+str(pid),abs(sections[0]['chord']-2.13)<=1e-5 and abs(sections[1]['chord']-.93)<=1e-5,s)
    for p in source:
        if p!=root:
            for pid,host in [(p,root),(peers[p],peers[root])]:
                s=call('control-'+str(pid),'shape.get',{'id':pid})['shape'];r.check('native control host '+str(pid),s['wingPartId']==host,s)
    r.check('shape changes preserve input bindings',bindings(snap('after-shape'))==bindings(mounted))
    call('shape-native','designer.capture',{**guard(),'focusPartIds':allids,'views':[{'view':'top','projection':'orthographic'},{'view':'isometric','projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True)
finally:
    restore('restore-original',original);end=snap('final');proof=audit(base['xml'],end['xml']);r.check('complete original restore',proof['equivalent'],proof)
    s=call('final-status','designer.status');r.check('one healthy instance',s['sceneIntegrity']['status']=='healthy' and s['sceneIntegrity']['aircraftInstanceCount']==1)
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
