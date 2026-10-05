"""Supplemental native complex controls, conditional fields and overload parity.

Uses only installed CLI commands. Test reference invokes real native widgets;
input values and complete-state comparison are independent of production codecs.
"""
import json,sys,uuid,copy,re
from precision_acceptance import Run
from review_restore_state import audit
from review_native_pose import compare as compare_property_state
r=Run(sys.argv[1]);identity=None;name='SP2Build 050 Precision Lab F2';inventory=[]
def call(label,command,args=None,**kw):
 global identity
 x=r.call(label,command,args,**kw);assert x['success'],x;d=x['data']
 if d.get('identity'):identity=d['identity']
 return d
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def batch(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def prop(p,patch):return {'kind':'properties.set','partId':p,'patch':patch,'symmetric':False}
def cp(n):return call(n,'craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':n})['id']
def restore(n,c):return call(n,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':c})
def native(n,action,**kw):return call(n,'acceptance.native',{**guard(),'requestId':uuid.uuid4().hex,'expectedCraftName':name,'action':action,**kw})
def fields(n,p):return {f['propertyId']:f for f in call(n,'properties.get',{'id':p,'limit':1000})['parts'][0]['fields'] if f.get('writeOperation')=='properties.set'}
base=call('baseline','craft.snapshot',{'includeXml':True});assert base['name']==name and base['partCount']==3
original=cp('original')
templates={'text':'tpl-2eb27a8bdfcc3166','decal':'tpl-7da5fd121ac144c6','turbo':'tpl-0107631356a369e6',
 'nose':'tpl-ef03f5b3e35e1bbe','bay':'tpl-0e1d278f1dc91cf6','piston':'tpl-c2ea68c52a8d3473','jet':'tpl-1a5ee3557bbab375','host':'tpl-f748657136c8ca1a'}
try:
 added=batch('prepare',[{'kind':'part.add','templateId':t,'temporaryId':k,'position':[5+i*4,4,0]} for i,(k,t) in enumerate(templates.items())])
 ids=added['temporaryIds'];snap=call('prepared','craft.snapshot',{'includeXml':True})
 turbo=next(p['id'] for p in snap['parts'] if p['type']=='Engine-Jet-Shroud-2')
 jet=next(p['id'] for p in snap['parts'] if p['type']=='Engine-Jet-Shroud-1')
 setups=[prop(ids['bay'],{'GearBay[0].autoHingeAxis':False,'GearBay[0].doorStyle':'DoubleLengthways'})]
 for p in (2,ids['text'],ids['decal'],ids['bay']):setups.append(prop(p,{'PartTargeting[0].targetMode':'Custom'}))
 nf=fields('nose-prerequisites',ids['nose'])
 if nf['GearLeg[0].catapultConnectorEnabled']['currentCondition']['satisfied']:
  setups.append(prop(ids['nose'],{'GearLeg[0].catapultConnectorEnabled':True}))
 batch('prerequisites',setups)
 prepared=call('prepared-conditional','craft.snapshot',{'includeXml':True});prepared_cp=cp('conditional baseline')
 plans=[]
 for role,p in [('text',ids['text']),('decal',ids['decal']),('turbo',turbo),('nose',ids['nose']),('bay',ids['bay']),('window',2)]:
  fs=fields(role+'-fields',p)
  for key,row in fs.items():
   # Already covered primitive bay/window fields in the first matrix.
   if role in ('window','bay') and not any(x in key for x in ('customPartIds','hingeAxisPose')):continue
   if role=='nose' and not any(x in key for x in ('catapult','targetLaunch','supportStrut','torqueLink')):continue
   if role=='turbo' and row['family']!='JetEngineShroud':continue
   plans.append({'role':role,'partId':p,'property':row})
 (r.root/'plans.json').write_text(json.dumps(plans,indent=2))
 for index,entry in enumerate(plans):
  tag=f'p{index:03}';p=entry['partId'];row=entry['property'];key=row['propertyId'];mi=int(key.split('[')[1].split(']')[0])
  if len(sys.argv)>2 and not re.search(sys.argv[2],key):continue
  restore(tag+'-initial',prepared_cp)
  c=next((c for c in native(tag+'-controls','inspect',partId=p,modifierType=row['family']+'Data',modifierIndex=mi)['controls'] if c['member']==row['nativeMember']),None)
  entry['nativeControl']=c
  if not c or not c['visible'] or not c['referenceSetterSupported']:
   entry['coverage']='unavailable_in_this_scenario';inventory.append(entry);continue
  value=c['value'];values=[('default',value)]
  if isinstance(value,bool):values += [('toggle',not value)]
  elif isinstance(value,(int,float)):
   values += [(side,row['limits'][side]) for side in ('min','max') if row.get('limits',{}).get(side) is not None]
  elif key.endswith('customPartIds'):values += [('target-list',[1,ids['host']]),('target-list-reordered',[ids['host'],1]),('empty',[])]
  elif isinstance(value,list):
   if key.endswith('TintColor'):values += [('min-rgb',[0,0,0,1]),('max-rgb',[1,1,1,1]),('fractional',[.125,.35,.8,1])]
   else:
    values += [(side,[row['limits'][side]]*len(value)) for side in ('min','max') if row.get('limits',{}).get(side) is not None]
    values += [('fractional',[-.25,.75])]
  elif isinstance(value,dict) and 'rotationQuaternion' in value:
   values += [('pose',{'position':[.037,-.021,.049],'rotationQuaternion':[0,0,.2588190451,.9659258263]})]
  elif row.get('enumValues'):
   choices=row['enumValues']
   if key.endswith('decalId'):choices=[choices[0],choices[-1]] # Picker resource list is audited separately; avoid rendering every decal.
   values += [('option-'+str(i),v) for i,v in enumerate(choices) if v!=value]
  elif isinstance(value,str):values += [('text','C-17 & <Test> / 精修')]
  if row['type']=='integer':values=[(case,int(v)) for case,v in values]
  entry['cases']=[]
  for case,v in values:
   label=tag+'-'+case
   restore(label+'-reference-start',prepared_cp)
   try:
    native(label+'-native','property',partId=p,modifierType=row['family']+'Data',modifierIndex=mi,member=row['nativeMember'],value=v)
    target=call(label+'-target','craft.snapshot',{'includeXml':True})
    restore(label+'-public-start',prepared_cp)
    batch(label+'-public',[prop(p,{key:v})])
    after=call(label+'-actual','craft.snapshot',{'includeXml':True});proof=compare_property_state(target['xml'],after['xml'],p,key)
    r.check(label+' native full state',proof['equivalent'],proof);entry['cases'].append({'case':case,'value':v,'passed':proof['equivalent']})
   except AssertionError as e:
    r.check(label+' native full state',False,str(e));entry['cases'].append({'case':case,'value':v,'passed':False,'error':str(e)})
    call(label+'-failure-state','craft.snapshot',{'includeXml':True});restore(label+'-recover',prepared_cp)
  entry['coverage']='executed';inventory.append(entry);(r.root/'inventory.json').write_text(json.dumps(inventory,indent=2))
 # Native Overload covers mandatory properties that have no ordinary UI widget.
 for i,(p,key,element,attribute,values) in enumerate([
  (ids['piston'],'Piston[0].PreventBreaking','Piston.State','preventBreaking',[False,True]),
  (ids['nose'],'GearLeg[0].gearLegStyle','GearLeg.State','gearLegStyle',['GL-AirlinerFront','GL-VFrameStrut']),
  (jet,'JetEngineShroud[0].width','JetEngineShroud.State','width',[.75,1,1.5]),
  (jet,'JetEngineShroud[0].height','JetEngineShroud.State','height',[.75,1,1.5])]):
  if len(sys.argv)>2 and not re.search(sys.argv[2],key):continue
  for j,v in enumerate(values):
   label=f'overload-{i}-{j}';restore(label+'-reference-start',prepared_cp)
   try:
    text=('true' if v else 'false') if isinstance(v,bool) else str(v)
    native(label+'-native','overload',partId=p,element=element,attribute=attribute,value=text)
    target=call(label+'-target','craft.snapshot',{'includeXml':True});restore(label+'-public-start',prepared_cp)
    batch(label+'-public',[prop(p,{key:v})]);actual=call(label+'-actual','craft.snapshot',{'includeXml':True})
    proof=audit(target['xml'],actual['xml']);r.check(label+' native full state',proof['equivalent'],proof)
   except AssertionError as e:
    r.check(label+' native full state',False,str(e));call(label+'-failure-state','craft.snapshot',{'includeXml':True});restore(label+'-recover',prepared_cp)
finally:
 restore('restore-original',original);final=call('final','craft.snapshot',{'includeXml':True})
 proof=audit(base['xml'],final['xml']);r.check('original full state restored',proof['equivalent'],proof)
 (r.root/'inventory.json').write_text(json.dumps(inventory,indent=2))
