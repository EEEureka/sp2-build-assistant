"""Freeze an existing open UI test fixture before the next manual target."""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1]);s=r.call('prepared','craft.snapshot',{'includeXml':True})['data']
assert s['name']=='SP2Build 050 Precision Lab F2'
i=s['identity'];cp=r.call('checkpoint','craft.checkpoint.create',{'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex,'name':sys.argv[1]})['data']['id']
for pid in map(int,sys.argv[2:]):r.call('properties-'+str(pid),'properties.get',{'id':pid,'limit':1000})
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp}),encoding='utf-8')
