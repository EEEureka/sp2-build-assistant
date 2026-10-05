"""Freeze native-UI shroud reference plus an analytically specified rigid target."""
import json,math,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1]);identity=None;group=[7,8,9,10,11]
def snap(label):
    global identity
    x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
    identity=x['data']['identity'];return x['data']
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def apply(label,ops):
    global identity
    a=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert a['success'],a
    identity=a['data']['identity'];return a['data']
base=snap('native-ui-shroud');assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==11
p=r.call('native-ui-shroud-properties','properties.get',{'id':8,'fields':['JetEngineShroud[0].length']})['data']['parts'][0]['fields'][0]
assert abs(p['value']-1.11)<1e-5,p
# Keep the unrelated original cube out of the detail camera's line of sight.
apply('separate-fixture-from-baseline',[{'kind':'transform.apply','partIds':list(range(4,12)),'mode':'delta','translation':[0,3,0],'symmetric':False}])
for i in range(2):
    m=r.call('reference-gap-'+str(i),'geometry.measure',{**guard(),'partIdsA':[9],'partIdsB':[4]});assert m['success'],m
    d=m['data']['measurement']['distanceMetres']
    if abs(d-.012)<1e-6:break
    apply('reference-gap-adjust-'+str(i),[{'kind':'transform.apply','partIds':group,'mode':'delta','translation':[0,d-.012,0],'symmetric':False}])
reference=snap('before-rigid-target');by={p['id']:p for p in reference['parts']}
q=[0,math.sin(math.radians(.2)/2),0,math.cos(math.radians(.2)/2)]
frame={'kind':'custom','position':by[9]['position'],'rotationQuaternion':by[9]['rotationQuaternion']}
motion={'kind':'transform.apply','partIds':group,'anchorPartId':9,'frame':frame,'mode':'delta','pivot':[-1.5,.75,.2],'translation':[.005,0,0],'rotationQuaternion':q,'symmetric':False}
apply('analytic-rigid-target',[motion]);final=snap('gold');finalby={p['id']:p for p in final['parts']}
props={}
for pid in (8,10,11):
    a=r.call('gold-properties-'+str(pid),'properties.get',{'id':pid,'limit':1000});assert a['success'],a
    props[pid]={f['propertyId']:f.get('value') for f in a['data']['parts'][0]['fields'] if f.get('valueAvailable')}
gap=r.call('gold-gap','geometry.measure',{**guard(),'partIdsA':[9],'partIdsB':[4]})['data']['measurement']['distanceMetres']
r.check('specified gap within 1mm',abs(gap-.012)<=.001,gap)
for label,scope,views in [('joint',[4,5,6,*group],[{'view':'isometric','projection':'perspective'},{'view':'top','projection':'orthographic'}]),
    ('detail',group,[{'view':'left','projection':'orthographic'},{'view':'custom','azimuthDegrees':-65,'elevationDegrees':12,'projection':'perspective'}])]:
    a=r.call('gold-'+label,'designer.capture',{**guard(),'focusPartIds':scope,'views':views,'resolution':{'width':1600,'height':1000}},images=True);assert a['success'],a
a=r.call('gold-mesh','geometry.section',{**guard(),'partIds':list(range(4,12)),'plane':{'origin':[5.5,0,0],'normal':[1,0,0]},'export':True,'exportMeshes':True},images=True);assert a['success'],a
for pid in (8,9):r.call('gold-ap-'+str(pid),'connections.points',{'part':pid})
for pid in (10,11):r.call('gold-projector-'+str(pid),'decal.pose.get',{'id':pid})
r.call('gold-appearance','appearance.get',{'partIds':list(range(1,12))})
cp=r.call('gold-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'E2 gold'})['data']['id']
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp,'group':group,'frozen':[1,2,3,4,5,6],'provenance':'CLI primitives, native UI shroud length 111%, CLI gap setup, analytic 5mm local X and 0.2 degree external pivot target'},indent=2))
public={'group':group,'anchorPartId':9,'anchorTarget':{k:finalby[9][k] for k in ('position','rotationQuaternion')},'requestedLocalMotion':motion,'gapMetres':.012,
    'shroudLengthRatio':props[8]['JetEngineShroud[0].length'],'text':'POD 050','textWidthMetres':props[10]['TextDecal[0].Width'],'stripeWidthMetres':props[11]['TextureDecal[0].Width'],
    'tolerances':{'positionMetres':.0001,'rotationDegrees':.01,'gapMetres':.001,'scalar':1e-6}}
(r.root/'public-target.json').write_text(json.dumps(public,indent=2))
