"""Double-layer window targets, expanded picking, and explicit host groups.

Runtime regression, not a substitute for the independent native UI golden case.
"""
import json,sys,uuid,math,xml.etree.ElementTree as ET
from precision_acceptance import Run
r=Run(sys.argv[1])
def snap(label):
 x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
 assert x['data']['name']=='SP2Build 050 Precision Lab F2'
 return x['data']
def guard():
 i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops):
 x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert x['success'],x
 return x['data']
def prop(pid,patch):return {'kind':'properties.set','partId':pid,'patch':patch,'symmetric':False}
def meshes(label,ids):
 x=r.call(label,'geometry.section',{**guard(),'partIds':ids,'frame':{'kind':'world'},'plane':{'origin':[4,2.25,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True);assert x['success'],x
 return json.loads(next((r.root/label).rglob('meshes.json')).read_text(encoding='utf-8-sig'))['meshes']
def only(ms,pid):return [{k:m[k] for k in ('vertices','indices')} for m in ms if m['partId']==pid]
def capture(label,ids,views=None):
 x=r.call(label,'designer.capture',{**guard(),'focusPartIds':ids,'views':views or [{'view':'back','projection':'orthographic'},{'view':'custom','azimuthDegrees':205,'elevationDegrees':15,'projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True);assert x['success'],x
 return x['data']['repeatableViews']
def ray(label,x):
 a=r.call(label,'designer.raycast',{'origin':[x,2.25,-3],'direction':[0,0,1],'distance':6});assert a['success'],a
 return a['data']['hits']
base=snap('baseline');assert len(base['parts'])==3
cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'Window scope original'})['data']['id']
try:
 added=apply('add-fixture',[{'kind':'part.add','templateId':tpl,'temporaryId':key,'position':pos} for key,tpl,pos in [
  ('outer','tpl-f748657136c8ca1a',[4,2.25,0]),('inner','tpl-f748657136c8ca1a',[4,2.25,0]),('window','tpl-a0c296e1a01292ad',[4,2.25,-1])]])
 ids=added['temporaryIds'];outer,inner,win=(ids[k] for k in ('outer','inner','window'))
 apply('configure-hosts',[{'kind':'shape.update','partId':pid,'symmetric':False,'patch':{'autoResize':False,'length':size,'sections':[{'index':i,'width':size,'height':size,'syncAdjacent':False} for i in (0,1)]}} for pid,size in [(outer,2),(inner,1.6)]]+
  [{'kind':'connection.connect','partA':pid,'partB':host,'attachPointA':0,'attachPointB':1,'symmetric':False} for pid,host in [(outer,1),(inner,outer),(win,outer)]])
 apply('empty-target',[prop(win,{'PartTargeting[0].targetMode':'Custom'}),prop(win,{'PartTargeting[0].customPartIds':[]}),prop(win,{'ProceduralWindow[0].height':.8,'ProceduralWindow[0].topWidth':.6,'ProceduralWindow[0].bottomWidth':.6,'ProceduralWindow[0].topOffset':0,'ProceduralWindow[0].bottomOffset':0,'ProceduralWindow[0].depth':1,'ProceduralWindow[0].penetration':.75,'ProceduralWindow[0].cornerRadius':.1,'ProceduralWindow[0].hideGlass':False,'Transparency[0].opacity':.3})])
 uncut=meshes('uncut-mesh',[outer,inner]);frozen=capture('uncut-native',[outer,inner,win])
 apply('target-outer',[prop(win,{'PartTargeting[0].customPartIds':[outer]})])
 cut=meshes('outer-cut-mesh',[outer,inner,win]);capture('outer-cut-native',[outer,inner,win],frozen)
 r.check('outer target geometry changes',only(uncut,outer)!=only(cut,outer))
 r.check('inner non-target mesh exact',only(uncut,inner)==only(cut,inner))
 r.check('glass renderer exists',bool(only(cut,win)))
 closed=ray('glass-center-ray',4);r.check('glass retains outer collider',any(h['partId']==outer and abs(h['point'][2]+1)<.001 for h in closed),closed)
 apply('hole',[prop(win,{'ProceduralWindow[0].hideGlass':True})])
 center=ray('hole-center-ray',4);edge=ray('small-hole-edge-ray',4.45)
 r.check('hole removes outer front center hit',not any(h['partId']==outer and abs(h['point'][2]+1)<.001 for h in center),center)
 r.check('untargeted inner blocks center',any(h['partId']==inner and abs(h['point'][2]+.8)<.001 for h in center),center)
 r.check('outside small opening still hits outer',any(h['partId']==outer and abs(h['point'][2]+1)<.001 for h in edge),edge)
 apply('enlarge-hole',[prop(win,{'ProceduralWindow[0].height':1.2,'ProceduralWindow[0].topWidth':1.1,'ProceduralWindow[0].bottomWidth':1.1})])
 expanded=ray('expanded-hole-edge-ray',4.45)
 r.check('expanded opening clears former collider',not any(h['partId']==outer and abs(h['point'][2]+1)<.001 for h in expanded),expanded)
 capture('expanded-native',[outer,inner,win],frozen)
 apply('switch-to-inner',[prop(win,{'PartTargeting[0].customPartIds':[inner]})])
 switched=meshes('inner-cut-mesh',[outer,inner,win])
 r.check('removing outer target restores its full mesh',only(uncut,outer)==only(switched,outer))
 r.check('new inner target geometry changes',only(uncut,inner)!=only(switched,inner))
 apply('both-targets',[prop(win,{'PartTargeting[0].customPartIds':[outer,inner]})])
 both=meshes('both-cut-mesh',[outer,inner,win]);capture('both-cut-native',[outer,inner,win],frozen)
 r.check('both targets changed',all(only(uncut,p)!=only(both,p) for p in (outer,inner)))
 # Moving the explicit group must not infer ownership from targeting or graph.
 before=snap('before-group-move');by={p['id']:p for p in before['parts']}
 resolved=r.call('resolved-group','groups.resolve',{**guard(),'selector':{'kind':'parts','partIds':[outer,inner,win]}});assert resolved['success'],resolved
 r.check('group selector resolves exact explicit IDs',sorted(resolved['data']['partIds'])==sorted([outer,inner,win]))
 r.check('group reports boundary and targeting separately',bool(resolved['data']['externalConnections']) and len(resolved['data']['targetReferences'])==1,resolved['data'])
 apply('move-explicit-host-group',[{'kind':'transform.apply','groupId':resolved['data']['groupId'],'frame':{'kind':'world'},'mode':'delta','translation':[.012,.007,-.005],'symmetric':False}])
 after=snap('after-group-move');post={p['id']:p for p in after['parts']}
 for pid in (outer,inner,win):r.check('explicit move '+str(pid),math.dist(post[pid]['position'],[a+b for a,b in zip(by[pid]['position'],[.012,.007,-.005])])<=.0001)
 r.check('all outside group poses frozen',all(by[p]['position']==post[p]['position'] and by[p]['rotationQuaternion']==post[p]['rotationQuaternion'] for p in by if p not in (outer,inner,win)))
 actual=meshes('moved-mesh',[outer,inner,win])
 topology=len(actual)==len(both) and all(a['indices']==b['indices'] and len(a['vertices'])==len(b['vertices']) for a,b in zip(actual,both))
 err=max((math.dist(v,[x+d for x,d in zip(w,[.012,.007,-.005])]) for a,b in zip(actual,both) for v,w in zip(a['vertices'],b['vertices'])),default=0) if topology else float('inf')
 r.check('cut surfaces move rigidly with explicit group',topology and err<=.0001,{'topology':topology,'maxVertexErrorMetres':err})
 capture('moved-native',[outer,inner,win],frozen)
 # Clone each mirrored peer explicitly. Target lists are not inferred from connectivity.
 mirrored=apply('create-mirrored-parts',[{'kind':'symmetry.create','partId':pid} for pid in (outer,inner,win)])
 peers={c['sourcePartId']:c['createdPartIds'][0] for c in mirrored['actualChanges'] if c['kind']=='symmetry.create'}
 mo,mi,mw=(peers[p] for p in (outer,inner,win))
 r.call('mirrored-window-default-targets','properties.get',{'id':mw,'limit':1000})
 apply('configure-mirrored-targets',[prop(mw,{'PartTargeting[0].customPartIds':[mo,mi]})]+
  [{'kind':'connection.connect','partA':p,'partB':h,'attachPointA':0,'attachPointB':1,'symmetric':False} for p,h in ((mo,1),(mi,mo),(mw,mo))])
 apply('symmetric-window-height',[{'kind':'properties.set','partId':win,'patch':{'ProceduralWindow[0].height':1.32},'symmetric':True}])
 for p in (win,mw):
  v=r.call('mirror-height-'+str(p),'properties.get',{'id':p,'fields':['ProceduralWindow[0].height','PartTargeting[0].customPartIds']});assert v['success'],v
  fields={f['propertyId']:f['value'] for f in v['data']['parts'][0]['fields']}
  r.check('symmetric window height '+str(p),abs(fields['ProceduralWindow[0].height']-1.32)<1e-5)
  r.check('targets remain on own side '+str(p),sorted(fields['PartTargeting[0].customPartIds'])==sorted([outer,inner] if p==win else [mo,mi]))
 mirror_before=snap('mirror-before-motion');prior={p['id']:p for p in mirror_before['parts']}
 apply('symmetric-host-group-motion',[{'kind':'transform.apply','partIds':[outer,inner,win],'frame':{'kind':'world'},'mode':'delta','translation':[.009,.006,-.004],'symmetric':True}])
 mirror_after=snap('mirror-after-motion');post={p['id']:p for p in mirror_after['parts']}
 all_ids=[outer,inner,win,mo,mi,mw]
 for p in all_ids:
  delta=[.009 if p in (outer,inner,win) else -.009,.006,-.004]
  r.check('one mirrored translation '+str(p),math.dist(post[p]['position'],[x+d for x,d in zip(prior[p]['position'],delta)])<.0001)
 r.check('mirrored motion freezes all outside parts',all(prior[p]==post[p] for p in prior if p not in all_ids))
 joint_views=capture('mirrored-joint-native',all_ids)
 reject=r.call('overlapping-symmetry-rejected','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{'kind':'transform.apply','partIds':[outer,inner,win,mo,mi,mw],'mode':'delta','translation':[.1,0,0],'symmetric':True}]})
 r.check('both sides with symmetry rejected clearly',not reject['success'] and reject['error']['code']=='symmetry_scope_overlap',reject.get('error'))
 r.check('overlap rejection preserves full XML',snap('after-overlap-rejection')['xml']==mirror_after['xml'])
finally:
 x=r.call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert x['success'],x
 r.check('exact original XML restored',snap('restored')['xml']==base['xml'])
 r.call('status','designer.status')
