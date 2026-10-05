"""Live native selection and scene navigation; no desktop input."""
import json, sys, uuid
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1]);identity=None;name=None
def call(label,command,args=None,images=False):
    global identity,name
    result=r.call(label,command,args,images=images);assert result['success'],result
    data=result['data']
    if data.get('identity'):identity=data['identity']
    if data.get('name'):name=data['name']
    if data.get('craftName'):name=data['craftName']
    return data
def args(action,**kw):return {'action':action,'expectedScene':'Designer','craftSessionId':identity['craftSessionId'],
    'expectedRevision':identity['revision'],'expectedCraftName':name,'requestId':uuid.uuid4().hex,**kw}
def control(label,action,**kw):return call(label,'designer.control',args(action,**kw))
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
catalog=call('fixtures','designer.crafts',{'query':'SP2Build 050 Precision Lab','limit':200})
fixture=next(x for x in catalog['items'] if x['name']==name)
r.check('catalog metadata returns exact loadable fixture',bool(fixture['craftId']))
for label,payload,code in [
    ('reject-discard',args('load',craftId=fixture['craftId']),'discard_confirmation_required'),
    ('reject-scene',{**args('select',partId=3),'expectedScene':'MainMenu'},'scene_conflict'),
    ('reject-id',args('select',partId=9999999),'part_not_found'),
    ('reject-string-confirmation',args('load',craftId=fixture['craftId'],discardCurrent='true'),'invalid_input')]:
    result=r.call(label,'designer.control',payload)
    r.check(label,not result['success'] and result.get('error',{}).get('code')==code,result)
    current=call(label+'-state','craft.snapshot',{'includeXml':True})
    proof=audit(base['xml'],current['xml']);r.check(label+' unchanged',proof['equivalent'],proof)
for part in base['parts']:
    selected=control('select-'+str(part['id']),'select',partId=part['id'])
    r.check('native selection '+str(part['id']),selected['selectedPartId']==part['id'])
    call('selection-read-'+str(part['id']),'designer.selection')
control('clear','select',clear=True)
original_identity=dict(identity)
loaded=control('reload-saved-native','load',craftId=fixture['craftId'],discardCurrent=True)
r.check('native load establishes new session',loaded['identity']['craftSessionId']!=original_identity['craftSessionId'])
after=call('after-load','craft.snapshot',{'includeXml':True})
proof=audit(base['xml'],after['xml']);r.check('native saved load full content',proof['equivalent'],proof)
control('menu','menu',discardCurrent=True)
status=call('menu-status','designer.status')
r.check('main menu and no ready designer',status['scene']=='MainMenu' and not status['designerReady'])
call('enter','designer.control',{'action':'enter','expectedScene':'MainMenu','requestId':uuid.uuid4().hex})
# Native designer startup restores __editor__; it may be a player aircraft.
# Do not modify it. Immediately load the explicit lab through native loader.
call('entered-state','craft.snapshot',{'includeXml':True})
control('return-lab','load',craftId=fixture['craftId'],discardCurrent=True)
final=call('final','craft.snapshot',{'includeXml':True})
proof=audit(base['xml'],final['xml']);r.check('final lab full content',proof['equivalent'],proof)
call('final-view','designer.capture',{'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision'],
    'views':['front','right','top'],'resolution':{'width':1000,'height':700}},images=True)
print(json.dumps({'checks':len(r.checks),'failures':[x for x in r.checks if x['status']=='fail']}))
