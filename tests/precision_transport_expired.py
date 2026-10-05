"""Verify an actually expired write stays a tombstone, never a new execution."""
import json,sys,datetime
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1]);canary=json.loads((ROOT/sys.argv[2]/'canary.json').read_text())
assert (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(canary['completedAt'])).total_seconds()>=901
before=r.call('before','craft.snapshot',{'includeXml':True});assert before['success'],before
assert before['instancePid']==canary['instancePid'], 'Expiration must be tested in the original process'
history=r.call('history-before','craft.history');assert history['success'],history
status=r.call('expired-status','operation.status',extra_args=['--id',canary['operationId']])
r.check('actual aged result expired but succeeded outcome retained',status['success'] and status['data']['state']=='result_expired' and status['data']['completionState']=='succeeded' and status['data']['result'] is None,status.get('data'))
again=r.call('retry-expired-write','batch.apply',canary['arguments'])
r.check('same requestId returns original expired operation',not again['success'] and again['error']['code']=='result_expired' and again['error'].get('operationId')==canary['operationId'],again)
bad=json.loads(json.dumps(canary['arguments']));bad['operations'][0]['changes'][0]['value']='must never execute after expiration'
conflict=r.call('expired-id-conflict','batch.apply',bad)
r.check('expired ID still rejects conflicting content',not conflict['success'] and conflict['error']['code']=='request_id_conflict',conflict.get('error'))
after=r.call('after','craft.snapshot',{'includeXml':True});hafter=r.call('history-after','craft.history')
r.check('full current XML and identity unchanged',after['success'] and after['data']['xml']==before['data']['xml'] and after['data']['identity']==before['data']['identity'])
r.check('native and plugin history unchanged',hafter['data']==history['data'])
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
