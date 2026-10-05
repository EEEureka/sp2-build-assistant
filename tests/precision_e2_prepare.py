"""Prepare a native-current-aircraft E2 fixture; then stop for UI gold edits."""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1]);identity=None
def snap(label):
    global identity
    x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
    identity=x['data']['identity'];return x['data']
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def apply(label,ops):
    global identity
    a=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert a['success'],a
    identity=a['data']['identity'];return a['data']
base=snap('baseline');assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
cp=r.call('baseline-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'E2 before preparation'})['data']['id']
(r.root/'fixture.json').write_text(json.dumps({'baselineCheckpointId':cp}))
added=apply('add-assemblies',[{'kind':'part.add','templateId':tpl,'temporaryId':key,'position':pos} for key,tpl,pos in [
    ('wing','tpl-1bdb332430679d47',[4,3.5,0]),('engine','tpl-1a5ee3557bbab375',[5.5,1,1.8]),
    ('pylon','tpl-f748657136c8ca1a',[5.5,2.75,0]),('text','tpl-2eb27a8bdfcc3166',[5.34,2.75,0]),('stripe','tpl-7da5fd121ac144c6',[5.34,3.05,0])]])
ids=added['temporaryIds'];assert ids=={'wing':4,'engine':7,'pylon':9,'text':10,'stripe':11},ids
apply('configure-pylon',[{'kind':'shape.update','partId':9,'symmetric':False,'patch':{'length':1.3,'autoResize':False,'sections':[{'index':i,'width':.3,'height':1.2,'cornerRadius':{c:.04 for c in ('topLeft','topRight','bottomLeft','bottomRight')},'cornerStretch':{c:False for c in ('topLeft','topRight','bottomLeft','bottomRight')},'syncAdjacent':False} for i in (0,1)]}}])
mounts={}
for key,members in [('wing',[4,5,6]),('engine',[7,8])]:
    eligible=[]
    for pid in members:
        x=r.call('mounts-'+str(pid),'connections.points',{'part':pid});assert x['success'],x
        eligible += [(pid,p['id']) for p in x['data']['points'] if (p['available'] or p['allowMultiple']) and p['allowManualConnection'] and 'Normal' in p['seekTypes']]
    assert eligible;mounts[key]=eligible[0]
before_connect=snap('before-connect')
apply('connect-assemblies',[{'kind':'connection.connect','partA':pid,'partB':host,'attachPointA':ap,'attachPointB':target,'symmetric':False} for pid,ap,host,target in [
    (*mounts['wing'],1,1),(*mounts['engine'],9,0),(9,1,4,1),(10,0,9,0),(11,0,9,0)]])
after_connect=snap('after-connect');old={p['id']:p for p in before_connect['parts']}
r.check('connect preserves every pose',all(p['position']==old[p['id']]['position'] and p['rotationQuaternion']==old[p['id']]['rotationQuaternion'] for p in after_connect['parts']))
def prop(pid,patch):return {'kind':'properties.set','partId':pid,'symmetric':False,'patch':patch}
apply('explicit-decal-targets',[prop(p,{'PartTargeting[0].targetMode':'Custom'}) for p in (10,11)]+[prop(p,{'PartTargeting[0].customPartIds':[9]}) for p in (10,11)])
apply('surface-details',[prop(10,{'TextDecal[0].Text':'POD 050','TextDecal[0].Font':'Roboto','TextDecal[0].FontSize':1.3,'TextDecal[0].HorizontalAlignment':'Center','TextDecal[0].VerticalAlignment':'Center','TextDecal[0].Width':1.1,'TextDecal[0].Height':.18,'TextDecal[0].Depth':.1,'TextDecal[0].Penetration':.5,'TextDecal[0].TintColor':[0,0,0,1]}),
    prop(11,{'TextureDecal[0].decalId':'Decals_Shapes_Arrow1','TextureDecal[0].Width':1.1,'TextureDecal[0].Height':.16,'TextureDecal[0].Depth':.1,'TextureDecal[0].Penetration':.5,'TextureDecal[0].TintColor':[.8,.05,.05,1],'TextureDecal[0].TextureTiling':[1,1],'TextureDecal[0].TextureOffset':[0,0]})]+
    [{'kind':'decal.pose.set','partId':p,'frame':{'kind':'world'},'position':[5.34,y,0],'rotationQuaternion':[0,2**-.5,0,2**-.5],'symmetric':False} for p,y in ((10,2.75),(11,3.05))])
r.call('shroud-properties','properties.get',{'id':8,'limit':1000})
for label,scope in [('joint',[4,5,6,7,8,9,10,11]),('detail',[7,8,9,10,11])]:
    a=r.call(label+'-native','designer.capture',{**guard(),'focusPartIds':scope,'views':[{'view':'left','projection':'orthographic'},{'view':'custom','azimuthDegrees':-65,'elevationDegrees':12,'projection':'perspective'}],'resolution':{'width':1600,'height':1000}},images=True);assert a['success'],a
r.call('mesh','geometry.section',{**guard(),'partIds':list(range(4,12)),'plane':{'origin':[5.5,0,0],'normal':[1,0,0]},'export':True,'exportMeshes':True},images=True)
r.call('pylon-wing-gap','geometry.measure',{**guard(),'partIdsA':[9],'partIdsB':[4]})
snap('prepared');r.call('status','designer.status')
(r.root/'fixture.json').write_text(json.dumps({'baselineCheckpointId':cp,'ids':ids,'engineMembers':[7,8],'mutableGroup':[7,8,9,10,11],'frozenWing':[4,5,6],'provenance':'CLI primitives; pending actual native UI gold edits'},indent=2))
