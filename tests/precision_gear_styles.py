"""All native gear styles and the extra support-strut slots they expose."""
import json,sys,uuid
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1]);identity=None;name='SP2Build 050 Precision Lab F2';coverage=[];slots=set()
def call(n,c,a=None):
 global identity
 x=r.call(n,c,a);assert x['success'],x;d=x['data']
 if d.get('identity'):identity=d['identity']
 return d
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def cp(n):return call(n,'craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':n})['id']
def restore(n,c):return call(n,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':c})
def native(n,action,**a):return call(n,'acceptance.native',{**guard(),'requestId':uuid.uuid4().hex,'expectedCraftName':name,'action':action,**a})
def edit(n,patch):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{'kind':'properties.set','partId':part,'patch':patch,'symmetric':False}]})
def fields(n):return {f['propertyId']:f for f in call(n,'properties.get',{'id':part,'limit':1000})['parts'][0]['fields'] if f.get('writeOperation')=='properties.set'}
base=call('baseline','craft.snapshot',{'includeXml':True});assert base['name']==name and base['partCount']==3
original=cp('original')
try:
 added=call('prepare','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{'kind':'part.add','templateId':'tpl-ef03f5b3e35e1bbe','temporaryId':'nose','position':[5,4,0]}]})
 part=added['temporaryIds']['nose'];start=cp('gear-start');styles=fields('initial-fields')['GearLeg[0].gearLegStyle']['enumValues']
 for i,style in enumerate(styles):
  label=f'style-{i:02}';row={'style':style,'fields':{},'slotCases':[]};restore(label+'-reference-start',start)
  try:
   native(label+'-native','overload',partId=part,element='GearLeg.State',attribute='gearLegStyle',value=style)
   target=call(label+'-target','craft.snapshot',{'includeXml':True});restore(label+'-public-start',start)
   edit(label+'-public',{'GearLeg[0].gearLegStyle':style});actual=call(label+'-actual','craft.snapshot',{'includeXml':True})
   proof=audit(target['xml'],actual['xml']);r.check(label+' complete native state',proof['equivalent'],proof);row['passed']=proof['equivalent']
   fs=fields(label+'-fields');row['fields']=fs;style_cp=None
   for suffix in ('supportStrutType1','supportStrutType2'):
    key='GearLeg[0].'+suffix;f=fs[key]
    if suffix in slots or not f['currentCondition']['satisfied']:continue
    if style_cp is None:style_cp=cp(label+'-configured')
    controls=native(label+'-'+suffix+'-inspect','inspect',partId=part,modifierType='GearLegData',modifierIndex=0)['controls']
    control=next(c for c in controls if c['member']==f['nativeMember'])
    assert control['visible'] and control['referenceSetterSupported'],control
    values=[control['value']]+[v for v in f['enumValues'] if v!=control['value']]
    for j,v in enumerate(values):
     n=f'{label}-{suffix}-{j}';restore(n+'-reference-start',style_cp)
     try:
      native(n+'-native','property',partId=part,modifierType='GearLegData',modifierIndex=0,member=f['nativeMember'],value=v)
      target=call(n+'-target','craft.snapshot',{'includeXml':True});restore(n+'-public-start',style_cp)
      edit(n+'-public',{key:v});actual=call(n+'-actual','craft.snapshot',{'includeXml':True})
      proof=audit(target['xml'],actual['xml']);r.check(n+' native slot state',proof['equivalent'],proof);row['slotCases'].append({'field':key,'value':v,'passed':proof['equivalent']})
     except AssertionError as e:
      r.check(n+' native slot state',False,str(e));call(n+'-failed-state','craft.snapshot');restore(n+'-recover',style_cp)
    slots.add(suffix)
  except AssertionError as e:
   r.check(label+' complete native state',False,str(e));row['error']=str(e);call(label+'-failed-state','craft.snapshot');restore(label+'-recover',start)
  coverage.append(row);(r.root/'styles.json').write_text(json.dumps(coverage,indent=2))
 r.check('all current native gear styles exercised',len(coverage)==len(styles))
 # One patch can rebuild a style and then edit another field. The second
 # setter must act on the replacement modifier rather than the retired one.
 restore('mixed-reference-start',start)
 native('mixed-style-native','overload',partId=part,element='GearLeg.State',attribute='gearLegStyle',value='GL-AirlinerFront')
 native('mixed-size-native','property',partId=part,modifierType='GearLegData',modifierIndex=0,member='_size',value=1.1)
 target=call('mixed-target','craft.snapshot',{'includeXml':True});restore('mixed-public-start',start)
 edit('mixed-public',{'GearLeg[0].gearLegStyle':'GL-AirlinerFront','GearLeg[0].size':1.1})
 actual=call('mixed-actual','craft.snapshot',{'includeXml':True});proof=audit(target['xml'],actual['xml'])
 r.check('style plus size patch binds replacement modifier',proof['equivalent'],proof)
 # No fabricated positive fixture when the current native prefab library has
 # no such mount. The per-style currentCondition records are the denominator.
 (r.root/'slot-coverage.json').write_text(json.dumps({'positiveSlots':sorted(slots),'unavailableAcrossCatalog':sorted(set(('supportStrutType1','supportStrutType2'))-slots),'stylesInspected':len(coverage)},indent=2))
finally:
 restore('restore-original',original);final=call('final','craft.snapshot',{'includeXml':True});proof=audit(base['xml'],final['xml'])
 r.check('original full state restored',proof['equivalent'],proof)
