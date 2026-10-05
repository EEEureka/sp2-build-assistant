"""Native modifier-sync toggle versus the style setter's actual impact set.

Style value/animation parity is covered by the separate 17-style Overload suite.
Here explicit symmetric:false writes to independently expected IDs are the
scope control, compared with one automatic propagation operation.
"""
import json,sys,uuid
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1]);host=sys.argv[2];identity=None;name='SP2Build 050 Precision Lab F2'
def call(n,c,a=None,**kw):
 global identity
 x=r.call(n,c,a,**kw);assert x['success'],x;d=x['data']
 if d.get('identity'):identity=d['identity']
 return d
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def snapshot(n):return call(n,'craft.snapshot',{'includeXml':True})
def checkpoint(n):return call(n,'craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':n})['id']
def restore(n,cp):return call(n,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
def batch(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def style(pid,symmetric):return {'kind':'properties.set','partId':pid,'patch':{'GearLeg[0].gearLegStyle':target_style},'symmetric':symmetric}
base=snapshot('baseline');assert base['name']==name and base['partCount']==3
original=checkpoint('symmetry original')
try:
 state=call('symmetry','symmetry.get');assert state['configuration']['mode']=='Mirrored',state
 x=batch('prepare',[{'kind':'part.add','templateId':'tpl-ef03f5b3e35e1bbe','temporaryId':'gear','position':[5,4,0]},
                    {'kind':'symmetry.create','partId':'gear'}])
 source=x['temporaryIds']['gear'];batch('enable-part-group',[{'kind':'symmetry.enable','partId':source,'enabled':True}]);prepared=snapshot('prepared')
 rows={p['id']:p for p in prepared['parts']};group=rows[source]['symmetryId']
 peers=[p['id'] for p in prepared['parts'] if p['id']!=source and p.get('symmetryId')==group and p['type']==rows[source]['type']]
 assert len(peers)==1,peers
 fs=call('style-options','properties.get',{'id':source,'limit':1000})['parts'][0]['fields']
 f=next(f for f in fs if f['propertyId']=='GearLeg[0].gearLegStyle')
 target_style='GL-VFrameStrut' if f['value']!='GL-VFrameStrut' else 'GL-AirlinerFront'
 assert target_style in f['enumValues'];ready=checkpoint('paired gear')
 for enabled in (True,False):
  restore('enabled-'+str(enabled)+'-start',ready)
  call('toggle-'+str(enabled),'acceptance.host',extra_args=['--host',host,'--action','modifier-symmetry',
      '--part-id',str(source),'--enabled',str(enabled).lower(),'--expected-craft-name',name])
  snap=snapshot('toggle-'+str(enabled)+'-state')
  import xml.etree.ElementTree as ET
  xml=ET.fromstring(snap['xml']);nodes={int(p.get('id')):p for p in xml.findall('./Assembly/Parts/Part')}
  r.check('native modifier flags '+str(enabled),all((nodes[p].find('GearLeg.State').get('symmetryDisabled')=='true')== (not enabled) for p in [source,*peers]))
  configured=checkpoint('modifier enabled '+str(enabled))
  for symmetric in (False,True):
   tag=f'enabled-{enabled}-symmetric-{symmetric}';expected_ids=[source,*peers] if enabled and symmetric else [source]
   restore(tag+'-reference-start',configured)
   batch(tag+'-explicit-scope',[style(pid,False) for pid in expected_ids]);reference=snapshot(tag+'-reference')
   restore(tag+'-actual-start',configured)
   result=batch(tag+'-actual-edit',[style(source,symmetric)]);actual=snapshot(tag+'-actual')
   proof=audit(reference['xml'],actual['xml']);r.check(tag+' full scope parity',proof['equivalent'],proof)
   (r.root/(tag+'-scope.json')).write_text(json.dumps({'expectedPartIds':expected_ids,'result':result,'fullState':proof},indent=2))
finally:
 restore('restore-original',original);final=snapshot('final');proof=audit(base['xml'],final['xml'])
 r.check('original full state restored',proof['equivalent'],proof)
print(json.dumps({'checks':len(r.checks),'failed':[c['check'] for c in r.checks if c['status']!='pass']}))
