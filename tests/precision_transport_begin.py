"""Public CLI discovery, wire-format and idempotence regression on a lab copy.

The shadow discovery directory simulates a live reused PID at the game's port
with an obsolete token. It never edits the real discovery directory.
"""
import json, os, sys, tempfile, uuid
from pathlib import Path
from precision_acceptance import Run
r=Run(sys.argv[1])
s=r.call('baseline','craft.snapshot',{'includeXml':True});assert s['success'],s
assert s['data']['name'].startswith('SP2Build 050 Precision Lab')
pid=s['instancePid'];real=Path(os.environ['LOCALAPPDATA'])/'SP2BuildAssistant'/'instances'/f'{pid}.json'
item=json.loads(real.read_text(encoding='utf-8-sig'));oldenv=os.environ['LOCALAPPDATA']
try:
    with tempfile.TemporaryDirectory(prefix='sp2-discovery-proof-') as tmp:
        directory=Path(tmp)/'SP2BuildAssistant'/'instances';directory.mkdir(parents=True)
        (directory/f'{pid}.json').write_text(json.dumps(item))
        fake={**item,'pid':os.getpid(),'token':'deliberately-obsolete-test-token','instanceId':'obsolete-pid-reuse'}
        (directory/f'{os.getpid()}.json').write_text(json.dumps(fake))
        os.environ['LOCALAPPDATA']=tmp
        found=r.call('stale-record-and-reused-pid','instances.list')
        r.check('only authenticated real instance is listed',found['success'] and [v['pid'] for v in found['data']['instances']]==[pid])
        status=r.call('status-with-stale-record','designer.status')
        r.check('unqualified command reaches intended instance',status['success'] and status['instancePid']==pid)
finally:os.environ['LOCALAPPDATA']=oldenv
i=s['data']['identity'];name=s['data']['parts'][0]['name'];part=s['data']['parts'][0]['id']
args={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex,
      'operations':[{'kind':'part.update','partId':part,'changes':[{'path':'Part','attribute':'name','value':name}],'symmetric':False}]}
a=r.call('canary-edit','batch.apply',args);assert a['success'],a
b=r.call('retry-identical-request','batch.apply',args);assert b['success'],b
r.check('identical write returns exact cached response',a==b)
view=r.call('canary-status','operation.status',extra_args=['--id',a['operationId']])
r.check('completed response is nested object with terminal metadata',view['data']['result']['success'] and view['data']['state']=='succeeded' and view['data']['completionState']=='succeeded' and view['data']['resultRetention']=='available')
bad=json.loads(json.dumps(args));bad['operations'][0]['changes'][0]['value']='must never execute'
x=r.call('request-id-conflict','batch.apply',bad)
r.check('same requestId different content is rejected',not x['success'] and x['error']['code']=='request_id_conflict')
final=r.call('after','craft.snapshot',{'includeXml':True});assert final['success'],final
from review_restore_state import audit
review=audit(s['data']['xml'],final['data']['xml']);r.check('canary preserves full state',review['equivalent'],review)
(r.root/'canary.json').write_text(json.dumps({'operationId':a['operationId'],'arguments':args,'completedAt':view['data']['completedAt'],'instancePid':pid},indent=2))
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
