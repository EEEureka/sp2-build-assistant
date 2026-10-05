"""Live precision boundaries on disposable parts, with guarded full recovery."""
import json,math,sys,uuid
import xml.etree.ElementTree as ET
from precision_acceptance import Run

r=Run(sys.argv[1] if len(sys.argv)>1 else 'dev7-boundaries')
def snapshot(label):
    x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
    assert x['data']['name'].startswith('SP2Build 050 Precision Lab')
    assert not x['data']['identity']['stateUncertain']
    return x['data']
def guard():
    i=snapshot('guard-'+str(len(r.calls)))['identity']
    return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops,expected_error=None):
    x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
    r.check(label,x.get('error',{}).get('code')==expected_error if expected_error else x['success'],x.get('error'))
    assert x.get('error',{}).get('code')==expected_error if expected_error else x['success'],x
    if expected_error and x.get('rollbackResult'):
        assert x['rollbackResult']['restored'],x
    return x
def pose(pid,p,q=(0,0,0,1)):
    return {'kind':'transform.apply','partIds':[pid],'mode':'absolute','position':p,'rotationQuaternion':list(q),'symmetric':False}
def scale(pid,values):
    return {'kind':'part.update','partId':pid,'symmetric':False,'changes':[{'path':'Part','attribute':'scale','value':','.join(map(str,values))}]}
def query(label,command,**kw):
    x=r.call(label,command,{**guard(),**kw},images=kw.get('export',False));assert x['success'],x
    return x['data']
def part(label,pid):
    x=r.call(label,'parts.get',{'id':pid});assert x['success'],x
    return x['data']['part']
def angle(a,b):
    d=abs(sum(x*y for x,y in zip(a,b)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return math.degrees(2*math.acos(min(1,d)))
def close(a,b,tol=.0001):return math.dist(a,b)<=tol

base=snapshot('baseline')
checkpoint=r.call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'precision-boundaries-baseline'})['data']['id']
try:
    added=apply('add-fixtures',[{'kind':'part.add','templateId':'tpl-f748657136c8ca1a','temporaryId':name,'position':pos,'rotation':[0,0,0]} for name,pos in [('box-a',[2,0,0]),('box-b',[3.012,0,0])]])
    a=added['data']['temporaryIds']['box-a'];b=added['data']['temporaryIds']['box-b']
    corners={x:0 for x in ('topLeft','topRight','bottomRight','bottomLeft')}
    apply('sharp-boxes',[{'kind':'shape.update','partId':pid,'symmetric':False,'patch':{'length':1,'autoResize':False,'sections':[{'index':i,'width':1,'height':1,'smoothing':False,'syncAdjacent':False,'cornerRadius':corners} for i in (0,1)]}} for pid in (a,b)])
    m=query('mirror','geometry.symmetry',partIdsA=[a],partIdsB=[b],plane={'origin':[2.506,0,0],'normal':[1,0,0]},sampleSpacingMetres=.1,export=True,exportMeshes=True)['measurement']
    r.check('identical mirrored surfaces near zero',m['sampledMaxMetres']<.0001,m)
    r.check('unambiguous mirrored normals near zero',m['normalSampleCount']>0 and m['maxUnorientedNormalAngleDegrees']<.01,m)
    r.check('ambiguous edge normals explicitly excluded',m['ambiguousNormalSampleCount']>0,m)
    apply('nonuniform-scale',[scale(a,[1.5,.7,1.2]),scale(b,[1.5,.7,1.2]),pose(b,[3.512,0,0])])
    measured=query('scaled-gap','geometry.measure',partIdsA=[a],partIdsB=[b],export=True,exportMeshes=True)['measurement']
    r.check('nonuniform scale actual surface 12mm gap',abs(measured['distanceMetres']-.012)<.0001,measured)
    q=[0,math.sin(math.radians(179.999)/2),0,math.cos(math.radians(179.999)/2)]
    apply('quaternion-plus',[pose(a,[2,.13,-.27],q)])
    p=part('plus-state',a)
    apply('quaternion-minus',[pose(a,[2,.13,-.27],[-v for v in q])])
    n=part('minus-state',a)
    r.check('q and minus q same orientation',angle(p['rotationQuaternion'],n['rotationQuaternion'])<.01,{'plus':p['rotationQuaternion'],'minus':n['rotationQuaternion']})
    r.check('rigid transform preserves nonuniform scale',n['scale']==p['scale']==[1.5,.7,1.2],n['scale'])
    stable=snapshot('before-invalid-quaternion')
    invalid=r.call('zero-quaternion','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[pose(a,[2,0,0],[0,0,0,0])]})
    r.check('zero quaternion rejected',not invalid['success'],invalid.get('error'))
    r.check('zero quaternion leaves state unchanged',snapshot('after-invalid-quaternion')['xml']==stable['xml'])
    group=query('resolve-group','groups.resolve',selector={'kind':'parts','partIds':[a,b]})
    apply('rev-change',[pose(b,[4,0,0])])
    stable=snapshot('before-stale-group')
    apply('stale-group',[{'kind':'transform.apply','groupId':group['groupId'],'mode':'delta','translation':[.001,0,0]}],'stale_group')
    r.check('stale group rejection preserves craft',snapshot('after-stale-group')['xml']==stable['xml'])
    apply('unit-scales',[scale(a,[1,1,1]),scale(b,[1,1,1]),pose(a,[2,0,0]),pose(b,[4,.2,0])])
    pa=part('align-a-before',a);pb=part('align-b-before',b)
    points_a=pa['attachPoints'];points_b=pb['attachPoints']
    source=next(x for x in points_a if math.dist(x['normal'],[0,0,0])>0)
    target=next(x for x in points_b if math.dist(x['normal'],[0,0,0])>0)
    before_connections=snapshot('align-before')['connections']
    apply('align',[{'kind':'transform.align','partIds':[a],'sourcePartId':a,'sourcePointId':source['id'],'targetPartId':b,'targetPointId':target['id'],'offset':[0,.012,0]}])
    pa=part('align-a-after',a);pb=part('align-b-after',b)
    ap=next(x for x in pa['attachPoints'] if x['id']==source['id']);bp=next(x for x in pb['attachPoints'] if x['id']==target['id'])
    r.check('attach-point align preserves requested offset',close(ap['worldPosition'],[bp['worldPosition'][0],bp['worldPosition'][1]+.012,bp['worldPosition'][2]]),{'a':ap,'b':bp})
    r.check('alignment does not create connection',snapshot('align-after')['connections']==before_connections)
    # Reuse is native allocation, never assume a specific chosen ID.
    group=query('resolve-before-reuse','groups.resolve',selector={'kind':'parts','partIds':[a]})
    replaced=apply('delete-and-replace',[{'kind':'part.delete','partId':a,'symmetric':False},{'kind':'part.add','templateId':'tpl-f748657136c8ca1a','temporaryId':'replacement','position':[2,0,0]}])['data']
    r.check('reused ID reported if native allocation reuses it',replaced['temporaryIds']['replacement']!=a or bool(replaced['reusedPartIds']),replaced.get('reusedPartIds'))
    apply('stale-group-after-reuse',[{'kind':'transform.apply','groupId':group['groupId'],'mode':'delta','translation':[1,0,0]}],'stale_group')
finally:
    result=r.call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':checkpoint})
    assert result['success'],result
    final=snapshot('restored')
    r.check('full fixture restore',final['xml']==base['xml'])
    s=r.call('final-status','designer.status')['data']
    r.check('one active aircraft after boundaries',s['sceneIntegrity']['aircraftInstanceCount']==s['sceneIntegrity']['activeAircraftInstanceCount']==1)
