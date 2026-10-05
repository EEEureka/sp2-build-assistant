"""Record real native mouse picks; mutations only use the installed CLI.

Between phases the operator clicks the documented point through the native UI.
This script never injects a synthetic selection or treats raycasts as mouse picks.
"""
import json,sys,uuid
from precision_acceptance import Run,ROOT
from review_restore_state import audit

phase,name,prep_name=sys.argv[1:4]
r=Run(name);prep=ROOT/prep_name
fixture=json.loads((prep/'fixture.json').read_text())
def call(n,c,a=None,images=False):
    x=r.call(n,c,a,images=images);assert x['success'],x;return x['data']
def guard(s):
    i=s['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
s=call('snapshot','craft.snapshot',{'includeXml':True})
assert s['name']=='SP2Build 050 Precision Lab F2' and s['partCount']==6
assert not s['identity']['stateUncertain']
selection=call('selection','designer.selection')
call('view','designer.capture',{**guard(s),'views':['current'],'resolution':{'width':1707,'height':1067}},images=True)
patch={'ProceduralWindow[0].height':1.2,'ProceduralWindow[0].topWidth':1.1,'ProceduralWindow[0].bottomWidth':1.1}
if phase=='edit':
    r.check('before expansion actual mouse selects outer host',selection['selectedPartId']==fixture['outer'])
    assert selection['selectedPartId']==fixture['outer']
    call('expand','batch.apply',{**guard(s),'requestId':uuid.uuid4().hex,'operations':[
        {'kind':'properties.set','partId':fixture['window'],'symmetric':False,'patch':patch}]})
elif phase in ('cli-pick','native-pick'):
    r.check('expanded area actual mouse selects window',selection['selectedPartId']==fixture['window'],{'screenPoint':[1080,533],'selected':selection['selectedPartId']})
    fields=call('properties','properties.get',{'id':fixture['window'],'fields':list(patch)})['parts'][0]['fields']
    values={f['propertyId']:f['value'] for f in fields}
    r.check('expanded dimensions match',values==patch,values)
    if phase=='native-pick':
        prior=json.loads((ROOT/sys.argv[4]/'snapshot.json').read_text(encoding='utf-8-sig'))['data']
        a=audit(prior['xml'],s['xml'])
        (r.root/'independent-parity.json').write_text(json.dumps(a,indent=2))
        r.check('native and CLI complete state equivalent',a['equivalent'],a)
elif phase=='restored-pick':
    r.check('after restore same mouse point selects outer host',selection['selectedPartId']==fixture['outer'],{'screenPoint':[1080,533],'selected':selection['selectedPartId']})
elif phase in ('reset','cleanup'):
    original=phase=='cleanup'
    call('restore','craft.rollback',{**guard(s),'requestId':uuid.uuid4().hex,'checkpointId':fixture['originalCheckpointId' if original else 'checkpointId']})
    after=call('restored','craft.snapshot',{'includeXml':True})
    before=json.loads((prep/('original.json' if original else 'prepared.json')).read_text(encoding='utf-8-sig'))['data']
    a=audit(before['xml'],after['xml']);r.check('full fixture restored',a['equivalent'],a)
    assert a['equivalent'],a
status=call('status','designer.status')
r.check('single healthy aircraft',status['sceneIntegrity']['status']=='healthy' and status['sceneIntegrity']['aircraftInstanceCount']==1)
