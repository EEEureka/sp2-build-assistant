"""Exercise actual public cancellation at proven render/queue stages.

The acceptance-only hook pauses one frame; it does not inject cancellation.
Every cancel and result query invokes globally installed sp2build.
"""
import json
import sys
import time
from pathlib import Path
from precision_acceptance import Run

r=Run(sys.argv[1] if len(sys.argv)>1 else 'dev7-cancellation')
flag=Path('D:/apps/steam/steamapps/common/SimplePlanes 2/BepInEx/config/sp2build.acceptance-fault.json')
assert not flag.exists(), 'Do not overwrite a pending fault request'
status=r.call('status','designer.status')['data']
baseline=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert baseline['name'].startswith('SP2Build 050 Precision Lab')
identity=baseline['identity']
args={'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision'],
      'views':['front','right','top'],'resolution':{'width':800,'height':600}}

def paused_capture(label):
    flag.write_text(json.dumps({'stage':'capture_render_0','pauseMilliseconds':5000}),encoding='utf-8')
    submit=r.call(label,'designer.capture',args,extra_args=['--async'])
    assert submit['success'],submit
    deadline=time.monotonic()+10
    while flag.exists() and time.monotonic()<deadline:
        time.sleep(.02)
    consumed=not flag.exists()
    r.check(label+' pause branch entered',consumed)
    assert consumed,'Hook was not entered; do not claim this cancellation branch was tested'
    return submit['data']['operationId']

def task(label,verb,job):
    return r.call(label,'operation.'+verb,extra_args=['--id',job])

try:
    job=paused_capture('running-submit')
    cancel=task('running-cancel','cancel',job)
    r.check('cancel issued while running',cancel.get('data',{}).get('state')=='running',cancel)
    result=task('running-result','wait',job)
    detail=result.get('error',{}).get('details',{})
    r.check('render cancellation error',not result['success'] and result.get('error',{}).get('code')=='cancelled',result)
    r.check('one completed view before cancellation',detail.get('completedViewCount')==1,detail)
    r.check('cancel camera restored including next two frames',detail.get('fieldDiff')==[] and len(detail.get('followingFrames',[]))==2 and all(x['fieldDiff']==[] for x in detail['followingFrames']),detail)
    final=task('running-final-state','status',job)
    r.check('render cancellation final state',final.get('data',{}).get('state')=='cancelled',final)
    normal=r.call('running-next-capture','designer.capture',args,images=True)
    r.check('next capture after render cancellation',normal['success'],normal.get('error'))

    blocker=paused_capture('queue-blocker')
    queued=r.call('queue-submit','designer.capture',args,extra_args=['--async'])
    assert queued['success'],queued
    job=queued['data']['operationId']
    cancel=task('queue-cancel','cancel',job)
    r.check('cancel issued while queued',cancel.get('data',{}).get('state')=='queued',cancel)
    block_result=task('queue-blocker-result','wait',blocker)
    r.check('blocker completed normally',block_result['success'],block_result.get('error'))
    result=task('queue-result','wait',job)
    r.check('queue cancelled before execution',result.get('error',{}).get('code')=='cancelled' and result['error']['message']=='Cancelled before execution.',result)
    final=task('queue-final-state','status',job)
    r.check('queued cancellation final state',final.get('data',{}).get('state')=='cancelled',final)
    normal=r.call('queue-next-capture','designer.capture',args,images=True)
    r.check('next capture after queue cancellation',normal['success'],normal.get('error'))
    completed=task('completed-cancel','cancel',normal['operationId'])
    r.check('completed cancellation does not change success',completed['data']['state']=='succeeded' and completed['data']['result']['success'],completed)
finally:
    if flag.exists():flag.unlink()
after=r.call('after','craft.snapshot',{'includeXml':True})['data']
r.check('cancellation suite preserves complete XML',after['xml']==baseline['xml'])
r.call('final-status','designer.status')
