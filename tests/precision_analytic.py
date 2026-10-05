"""Live analytic fixture; expectations use boxes/plane equations, not DLL math."""
import json, math, uuid
from pathlib import Path
from precision_acceptance import Run

r=Run('dev6-analytic')
def state():
    s=r.call('state-'+str(len(r.calls)),'craft.snapshot',{'includeXml':True})['data']
    assert s['name']=='SP2Build 050 Precision Lab F1'
    return s
def guard():
    i=state()['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops):
    x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
    assert x['success'],x
    return x['data']
def query(label,command,**args):
    x=r.call(label,command,{**guard(),**args},images=args.get('export',False));assert x['success'],x
    return x['data']
def pose(pid,p,q=(0,0,0,1)):
    return {'kind':'transform.apply','partIds':[pid],'mode':'absolute','position':p,'rotationQuaternion':list(q)}
corners={x:0 for x in ('topLeft','topRight','bottomRight','bottomLeft')}
apply('rectangular-boxes',[{'kind':'shape.update','partId':pid,'symmetric':False,'patch':{'length':1,'autoResize':False,'sections':[{'index':i,'width':1,'height':1,'smoothing':False,'syncAdjacent':False,'cornerRadius':corners} for i in (0,1)]}} for pid in (2,4)])
d=query('gap12','geometry.measure',partIdsA=[2],partIdsB=[4],export=True,exportMeshes=True)
print('gap result',d['measurement'],flush=True)
r.check('12mm analytic gap',abs(d['measurement']['distanceMetres']-.012)<=.0001,d['measurement'])
section=query('box-section','geometry.section',partIds=[2],plane={'origin':[0,0,0],'normal':[0,0,1]},limit=100,export=True,exportMeshes=True)
collider=query('collider-source','geometry.measure',partIdsA=[2],partIdsB=[4],source='collider')
r.check('collider source explicit',collider['source']=='collider' and (collider['measurement'].get('status')=='unavailable' or abs(collider['measurement']['distanceMetres']-.012)<=.0001),collider['measurement'])
apply('intersect',[pose(4,[2.8,0,0])])
inter=query('intersect-distance','geometry.measure',partIdsA=[2],partIdsB=[4])
r.check('intersect unsigned zero',inter['measurement']['distanceMetres']<=.0001,inter['measurement'])
# Two long thin parallel rectangles, rotated 45deg. Their AABBs overlap,
# but their facing sides have a 12mm gap along the local Y normal.
thin=[{'kind':'shape.update','partId':pid,'symmetric':False,'patch':{'sections':[{'index':i,'width':2,'height':.1} for i in (0,1)]}} for pid in (2,4)]
q=[0,0,math.sin(math.pi/8),math.cos(math.pi/8)]
normal=[-math.sqrt(.5),math.sqrt(.5),0]
apply('tilted-separated',thin+[pose(2,[2,0,0],q),pose(4,[2+.112*normal[0],.112*normal[1],0],q)])
tilt=query('aabb-false-overlap','geometry.measure',partIdsA=[2],partIdsB=[4],export=True,exportMeshes=True)
r.check('tilted actual separation despite AABB overlap',abs(tilt['measurement']['distanceMetres']-.012)<=.0001,tilt['measurement'])
apply('restore-unit-boxes',[{'kind':'shape.update','partId':pid,'symmetric':False,'patch':{'sections':[{'index':i,'width':1,'height':1} for i in (0,1)]}} for pid in (2,4)]+[pose(2,[2,0,0]),pose(4,[3.012,0,0])])
sym=query('mirror-zero','geometry.symmetry',partIdsA=[2],partIdsB=[4],plane={'origin':[2.506,0,0],'normal':[1,0,0]},sampleSpacingMetres=.1)
print('symmetry',sym['measurement'],flush=True)
r.call('final','craft.snapshot',{'includeXml':True})
