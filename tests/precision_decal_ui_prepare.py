"""Connected adjacent targets for actual UI text/texture parity; leaves the fixture open."""
import json, sys, uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def call(label,cmd,args=None):
    x=r.call(label,cmd,args);assert x['success'],x;return x['data']
def snap(label):
    s=call(label,'craft.snapshot',{'includeXml':True})
    assert s['name']=='SP2Build 050 Precision Lab F2' and not s['identity']['stateUncertain']
    return s
def guard():
    i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def checkpoint(label):return call(label,'craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':label})['id']
def apply(label,ops):return call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def prop(p,patch):return {'kind':'properties.set','partId':p,'patch':patch,'symmetric':False}
b=snap('baseline');assert b['partCount']==3
original=checkpoint('original')
(r.root/'fixture.json').write_text(json.dumps({'originalCheckpointId':original}))
spec=[('a','tpl-f748657136c8ca1a',[4,2.25,0]),('b','tpl-f748657136c8ca1a',[6,2.25,0]),
      ('text','tpl-2eb27a8bdfcc3166',[5,2.5,-.5]),('decal','tpl-7da5fd121ac144c6',[5,2,-.5])]
ids=apply('add',[{'kind':'part.add','templateId':tpl,'temporaryId':key,'position':pos} for key,tpl,pos in spec])['temporaryIds']
hosts=[ids['a'],ids['b']];text,decal=ids['text'],ids['decal']
ops=[{'kind':'shape.update','partId':p,'symmetric':False,'patch':{'autoResize':False,'sections':[{'index':i,'width':2,'height':1.5} for i in (0,1)]}} for p in hosts]
ops += [{'kind':'connection.connect','partA':p,'partB':host,'attachPointA':0,'attachPointB':1,'symmetric':False} for p,host in [(hosts[0],1),(hosts[1],1),(text,hosts[0]),(decal,hosts[0])]]
ops += [prop(p,{'PartTargeting[0].targetMode':'Custom'}) for p in (text,decal)]
ops += [prop(p,{'PartTargeting[0].customPartIds':hosts}) for p in (text,decal)]
ops += [prop(text,{'TextDecal[0].Text':'SP2 050','TextDecal[0].Font':'Roboto','TextDecal[0].FontSize':2.5,
     'TextDecal[0].HorizontalAlignment':'Center','TextDecal[0].VerticalAlignment':'Center','TextDecal[0].Width':3,
     'TextDecal[0].Height':.4,'TextDecal[0].Depth':.3,'TextDecal[0].Penetration':.5,'TextDecal[0].TintColor':[0,0,0,1]}),
     prop(decal,{'TextureDecal[0].decalId':'Decals_Shapes_Arrow1','TextureDecal[0].Width':3,'TextureDecal[0].Height':.4,
     'TextureDecal[0].Depth':.3,'TextureDecal[0].Penetration':.5,'TextureDecal[0].TintColor':[.8,.08,.05,1]})]
ops += [{'kind':'decal.pose.set','partId':p,'frame':{'kind':'world'},'position':[5,y,-.51],'rotationQuaternion':[0,0,0,1],'symmetric':False} for p,y in [(text,2.5),(decal,2)]]
apply('configure',ops)
snap('prepared')
for p in (text,decal):call('properties-'+str(p),'properties.get',{'id':p,'limit':1000})
cp=checkpoint('ui-baseline')
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp,'originalCheckpointId':original,'partIds':ids,
    'views':[{'view':'back','projection':'orthographic'},{'view':'custom','azimuthDegrees':-155,'elevationDegrees':12,'projection':'perspective'}]},indent=2))
print(ids)
