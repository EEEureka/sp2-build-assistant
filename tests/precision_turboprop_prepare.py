"""Prepare a native turboshaft shroud UI target, preserving original test data."""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def call(n,c,a=None):
    x=r.call(n,c,a);assert x['success'],x;return x['data']
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==10
original=call('original-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'before turboprop UI fixture'})['id']
out=call('add','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[{'kind':'part.add','templateId':'tpl-0107631356a369e6','temporaryId':'turboprop','position':[8,4,0]}]})
snapshot=call('prepared','craft.snapshot',{'includeXml':True})
added=[p for p in snapshot['parts'] if p['id'] not in {x['id'] for x in base['parts']}]
shrouds=[p for p in added if p['type']=='Engine-Jet-Shroud-2']
assert len(shrouds)==1,added
pid=shrouds[0]['id']
call('properties-'+str(pid),'properties.get',{'id':pid,'limit':1000})
checkpoint=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'native turboprop shroud UI baseline'})['id']
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':checkpoint,'originalCheckpointId':original,'shroud':pid,'groupIds':[p['id'] for p in added]},indent=2))
