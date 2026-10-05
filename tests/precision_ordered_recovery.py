"""Ordered transform boundaries, native dependencies and exact recovery."""
import json,math,sys,uuid
from precision_acceptance import Run,ROOT
from precision_diff import compare
r=Run(sys.argv[1]);gold=ROOT/sys.argv[2];cp=json.loads((gold/'fixture.json').read_text())['checkpointId']
def call(n,c,a=None,**kw):
 x=r.call(n,c,a,**kw);assert x['success'],x;return x['data']
def snap(n):
 x=call(n,'craft.snapshot',{'includeXml':True});assert x['name']=='SP2Build 050 Precision Lab E3' and x['partCount']==8 and not x['identity']['stateUncertain'];return x
def guard():
 i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def write(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def reset(n):call(n,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
def prop(pid,key,v):return {'kind':'properties.set','partId':pid,'patch':{key:v},'symmetric':False}
def raw(pid,key,v):return {'kind':'part.update','partId':pid,'changes':[{'path':'Part','attribute':key,'value':v}],'symmetric':False}
move={'kind':'transform.apply','partIds':[5,6],'mode':'delta','translation':[.01234567,-.02345678,.03456789],'rotationQuaternion':[0,.001745328,0,.999998477],'symmetric':False}
reset('initial-reset');base=snap('baseline')
try:
 for ids in ([5],[6],[5,6]):
  d=call('group-'+str(ids),'groups.resolve',{**guard(),'selector':{'kind':'parts','partIds':ids}})
  deps=d['nativeDependencies'];r.check('actual native gear-wheel dependency '+str(ids),len(deps)==1 and deps[0]['partId']==6 and deps[0]['hostPartId']==5 and deps[0]['bothIncluded']==(len(ids)==2),deps)
 for ids in ([5],[6]):
  x=r.call('incomplete-'+str(ids),'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{**move,'partIds':ids}]})
  r.check('incomplete rejected '+str(ids),not x['success'] and x['error']['code']=='incomplete_native_group' and x['rollbackResult']['restored'],x.get('error'));r.check('incomplete exact state '+str(ids),not compare(base['xml'],snap('after-incomplete-'+str(ids))['xml']))
 cases=[('pose-size',[move,prop(5,'GearLeg[0].size',.7872)]),
  ('pose-merged-raw',[move,raw(4,'name','ordered-host'),raw(5,'name','ordered-leg'),raw(6,'name','ordered-wheel')]),
  ('pose-explicit-position',[move,raw(5,'position','4.711,5.844,0.014'),raw(4,'name','explicit-position')]),
  ('same-property-twice',[prop(6,'JWheelAssembly[0].width',.92),prop(6,'JWheelAssembly[0].width',1.02)])]
 for name,ops in cases:
  reset(name+'-reset-batch');out=write(name+'-batch',ops);b=snap(name+'-batched')
  reset(name+'-reset-serial')
  for i,op in enumerate(ops):write(name+'-single-'+str(i),[op])
  s=snap(name+'-serial');diff=compare(b['xml'],s['xml']);r.check(name+' batch equals serial',not diff,diff)
  if name=='pose-merged-raw':r.check('adjacent raw edits only one reconstruction',out['rebuildCount']==1,out['rebuildCount'])
  if name=='pose-explicit-position':
   p=next(p for p in b['parts'] if p['id']==5);r.check('explicit position not overwritten by retained pose',math.dist(p['position'],[4.711,5.844,.014])<=.0001,p['position'])
 reset('failure-reset')
 x=r.call('later-failure','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[move,prop(6,'JWheelAssembly[0].size',-4)]})
 r.check('failure after verified transform rolls whole batch back',not x['success'] and x.get('rollbackResult',{}).get('restored'),x.get('error'))
 r.check('failure exact state',not compare(base['xml'],snap('after-failure')['xml']))
 # A previously unsupported animation target must stay explicit, not silently
 # accept a made-up property or manipulate serialized keyframes.
 fs=call('animator-discovery','properties.get',{'id':5,'limit':1000})['parts'][0]['fields'];anim=[f for f in fs if f['propertyId'].startswith('Animator[')]
 (r.root/'animator-boundary.json').write_text(json.dumps(anim,indent=2))
 x=r.call('unsupported-keyframes','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[prop(5,'Animator[0].keyframes',[])]})
 r.check('unsupported keyframes explicit failure',not x['success'] and x['error']['code'] in ('property_not_found','property_not_editable','property_unsupported'),x.get('error'))
 r.check('unsupported exact state',not compare(base['xml'],snap('after-unsupported')['xml']))
finally:
 reset('cleanup');r.check('complete baseline recovery',not compare(base['xml'],snap('restored')['xml']))
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
