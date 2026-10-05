"""One-shot acceptance-build fault injection. No private game editing API."""
import json
import uuid
from pathlib import Path
from precision_acceptance import Run

r=Run('dev5-faults')
baseline=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert baseline['name'].startswith('SP2Build 050 Precision Lab')
flag=Path('D:/apps/steam/steamapps/common/SimplePlanes 2/BepInEx/config/sp2build.acceptance-fault.json')
assert not flag.exists(), 'Do not overwrite a pending fault request'
for stage in ('after_operation_0','after_operation_1','after_operations','after_refresh','before_commit','after_commit'):
    before=r.call(stage+'-before','craft.snapshot',{'includeXml':True})['data']
    identity=before['identity']
    flag.write_text(json.dumps({'stage':stage}),encoding='utf-8')
    try:
        result=r.call(stage,'batch.apply',{'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision'],'requestId':uuid.uuid4().hex,'operations':[
            {'kind':'properties.set','partId':76,'symmetric':False,'patch':{'ProceduralWindow[0].height':.735}},
            {'kind':'properties.set','partId':218,'symmetric':False,'patch':{'TextureDecal[0].Opacity':.65}}]})
    finally:
        if flag.exists():flag.unlink()
    r.check(stage+' entered injected branch',not result['success'] and result['error']['code']=='acceptance_injected_failure',result.get('error'))
    r.check(stage+' restored',result.get('rollbackResult',{}).get('restored') is True,result.get('rollbackResult'))
    after=r.call(stage+'-after','craft.snapshot',{'includeXml':True})['data']
    if after['identity']['stateUncertain']:raise RuntimeError('Stop on uncertain recovery')
    r.check(stage+' identical baseline',before['identity']['fingerprint']==after['identity']['fingerprint'])
    status=r.call(stage+'-scene','designer.status')['data']
    r.check(stage+' only one aircraft',status['sceneIntegrity']['status']=='healthy')
for stage in ('capture_render_0','capture_encode_0','capture_render_1','capture_encode_1'):
    identity=r.call(stage+'-before','designer.status')['data']['identity']
    args={'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision'],'views':['front','right'],'resolution':{'width':800,'height':600}}
    flag.write_text(json.dumps({'stage':stage}),encoding='utf-8')
    try: result=r.call(stage,'designer.capture',args,images=True)
    finally:
        if flag.exists():flag.unlink()
    r.check(stage+' injected render/encode failure',not result['success'] and result['error']['code']=='acceptance_injected_failure')
    diagnostic=result.get('error',{}).get('details',{})
    r.check(stage+' two following stable frames',len(diagnostic.get('followingFrames',[]))==2 and all(not frame['fieldDiff'] for frame in diagnostic['followingFrames']))
    r.check(stage+' restore fields empty',not diagnostic.get('fieldDiff',['missing']))
    success=r.call(stage+'-next-normal','designer.capture',args,images=True)
    r.check(stage+' next capture succeeds',success['success'])
r.call('final','craft.snapshot',{'includeXml':True})
