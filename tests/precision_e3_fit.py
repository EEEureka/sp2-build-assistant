"""Three declared mechanical fitting starts using only public targets.

Native gold XML is never a solver input. Each trial includes a deliberately
worse wheel adjustment, real craft.undo, then a fresh measured correction.
"""
import json,math,sys,uuid
from precision_acceptance import Run,ROOT
from precision_diff import compare
r=Run(sys.argv[1]);gold=ROOT/sys.argv[2];target=json.loads((gold/'public-target.json').read_text());cp=json.loads((gold/'fixture.json').read_text())['checkpointId'];identity=None
keys={5:['GearLeg[0].size','GearLeg[0].suspensionTravel','GearLeg[0].torqueLinkLength'],6:['JWheelAssembly[0].size','JWheelAssembly[0].width','JWheelAssembly[0].wheelOffset'],7:['GearBay[0].height','GearBay[0].topWidth','GearBay[0].bottomWidth','GearBay[0].doorThickness'],8:['Piston[0].radius','Piston[0].range','Piston[0].speed']}
starts=[{'translation':[.015,-.02,.012],'scaleFactor':.92,'strokeDelta':.04},{'translation':[-.023,.015,-.018],'scaleFactor':1.08,'strokeDelta':-.05},{'translation':[.011,-.03,.022],'scaleFactor':.88,'strokeDelta':.06}]
(r.root/'fixed-starts.json').write_text(json.dumps(starts,indent=2));rows=[]
def call(label,cmd,args=None,**kw):
 x=r.call(label,cmd,args,**kw);assert x['success'],x;return x['data']
def snap(label):
 global identity
 s=call(label,'craft.snapshot',{'includeXml':True});assert s['name'] in ('SP2Build 050 Precision Lab F2','SP2Build 050 Precision Lab E3') and s['partCount']==8;identity=s['identity'];return s
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def write(label,ops):
 global identity
 d=call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});identity=d['identity'];return d
def restore(label):
 global identity
 snap(label+'-guard');d=call(label,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});identity=d['identity']
def props(pid,patch):return {'kind':'properties.set','partId':pid,'patch':patch,'symmetric':False}
def measure(label):
 s=snap(label+'-state');anchor=next(p['position'] for p in s['parts'] if p['id']==5);vals={}
 for pid,ks in keys.items():
  fs=call(label+'-properties-'+str(pid),'properties.get',{'id':pid,'fields':ks})['parts'][0]['fields'];vals[pid]={f['propertyId']:f['value'] for f in fs if f['valueAvailable']};assert set(vals[pid])==set(ks)
 g=call(label+'-wheel','parts.geometry',{'id':6})['geometry'];tire=next(x['bounds']['center'] for x in g['renderers'] if x['name'].startswith('Tire'))
 errs={'anchorMetres':math.dist(anchor,target['anchor']['position']),'scalar':max(abs(v-target['fields'][str(pid)][k]) for pid,vs in vals.items() for k,v in vs.items()),'wheelCenter':tire}
 return s,anchor,vals,errs
def capture(label):
 ref=json.loads((gold/'native-views.json').read_text())['data'];return call(label+'-views','designer.capture',{**guard(),'views':ref['repeatableViews'],'resolution':ref['repeatableResolution']},images=True)
def mesh(label):return call(label,'geometry.section',{**guard(),'partIds':[4,5,6,7,8],'frame':{'kind':'world'},'plane':{'origin':[0,0,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True)
try:
 for trial,start in enumerate(starts,1):
  n='trial-'+str(trial);restore(n+'-reset')
  ops=[{'kind':'transform.apply','partIds':[5,6],'mode':'delta','translation':start['translation'],'symmetric':False}]
  for pid,ks in keys.items():
   patch={k:target['fields'][str(pid)][k]*start['scaleFactor'] for k in ks}
   if pid==8:patch['Piston[0].range']=target['fields']['8']['Piston[0].range']+start['strokeDelta']
   ops.append(props(pid,patch))
  # Deliberately retain the original transform-before-dimensions order: this
  # verifies the ordered native postcondition fix, not an input workaround.
  write(n+'-perturb',ops);capture(n+'-start')
  for iteration,gain in enumerate([.8,1.]):
   label=n+'-round-'+str(iteration);s,anchor,vals,errs=measure(label)
   ops=[{'kind':'transform.apply','partIds':[5,6],'mode':'delta','translation':[gain*(b-a) for a,b in zip(anchor,target['anchor']['position'])],'symmetric':False}]
   ops.extend(props(pid,{k:v+gain*(target['fields'][str(pid)][k]-v) for k,v in vs.items()}) for pid,vs in vals.items())
   rows.append({'trial':trial,'iteration':iteration,'errors':errs,'decision':{'basis':'current effective mechanical dimensions and native anchor, compared with public targets; ordered pose then native dimensions','gain':gain,'operations':ops}})
   (r.root/'iterations.json').write_text(json.dumps(rows,indent=2));write(label+'-candidate',ops)
   if iteration==0:
    good=snap(n+'-before-bad')
    now=call(n+'-prebad-wheel','properties.get',{'id':6,'fields':['JWheelAssembly[0].wheelOffset']})['parts'][0]['fields'][0]['value']
    write(n+'-deliberately-worse',[props(6,{'JWheelAssembly[0].wheelOffset':now+.25})]);capture(n+'-worse')
    call(n+'-history-before-undo','craft.history')
    call(n+'-undo-worse','craft.undo',{**guard(),'requestId':uuid.uuid4().hex});restored=snap(n+'-after-undo')
    diffs=compare(good['xml'],restored['xml']);r.check(n+' real native undo restores prior complete state',not diffs,diffs)
    assert not diffs, 'Undo changed unrelated state; retain evidence and stop dependent edits'
  s,anchor,vals,err=measure(n+'-final-measure');r.check(n+' dimensions and anchor converge in two candidates',err['anchorMetres']<=.0001 and err['scalar']<=1e-6,err)
  snap(n+'-final');mesh(n+'-final-mesh');capture(n+'-final')
  for pid in (5,6,7,8):call(n+'-ap-'+str(pid),'connections.points',{'part':pid})
  best=call(n+'-best-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':n+' E3 candidate'})['id'];(r.root/(n+'-best.json')).write_text(json.dumps({'checkpointId':best}))
finally:
 restore('cleanup-gold');snap('final-restored');call('final-status','designer.status')
