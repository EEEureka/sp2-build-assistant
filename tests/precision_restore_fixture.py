"""Explicit recovery through the public CLI to a recorded same-session fixture."""
import json,sys,uuid
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1]);prep=ROOT/sys.argv[2]
s=r.call('before','craft.snapshot',{'includeXml':True})['data']
assert s['name']=='SP2Build 050 Precision Lab F2'
i=s['identity'];fixture=json.loads((prep/'fixture.json').read_text(encoding='utf-8-sig'))
original='checkpointId' not in fixture or '--original' in sys.argv[3:]
cp=fixture['originalCheckpointId'] if original else fixture['checkpointId']
x=r.call('rollback','craft.rollback',{'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex,'checkpointId':cp})
assert x['success'],x
a=r.call('after','craft.snapshot',{'includeXml':True})['data']
baseline_file=prep/('baseline.json' if original else 'prepared.json')
if original and not baseline_file.exists():baseline_file=prep/'original.json'
b=json.loads(baseline_file.read_text(encoding='utf-8-sig'))['data']
r.check('exact fixture XML restored',a['xml']==b['xml'])
r.check('exact fixture fingerprint restored',a['identity']['fingerprint']==b['identity']['fingerprint'])
r.call('status','designer.status')
