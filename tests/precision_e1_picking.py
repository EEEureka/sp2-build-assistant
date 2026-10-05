"""Compare native collider rays at gold, perturbed and all fitted checkpoints."""
import json,sys,uuid
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1]);gold=ROOT/sys.argv[2];fit=ROOT/sys.argv[3]
goldcp=json.loads((gold/'fixture.json').read_text())['checkpointId']
shift=json.loads((gold/'public-target.json').read_text()).get('fixtureTranslation',[0,0,0])
def guard():
    a=r.call('state-'+str(len(r.calls)),'designer.status');assert a['success'],a
    i=a['data']['identity'];assert not i['stateUncertain'] and a['data']['sceneIntegrity']['status']=='healthy'
    return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def restore(label,cp,allow_recovered_failure=False):
    a=r.call(label,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
    if not a['success']:
        r.check(label+' checkpoint restored',False,a.get('error'))
        assert allow_recovered_failure and a.get('rollbackResult',{}).get('restored') and not a['identity']['stateUncertain'],a
        return False
    return True
def rays(label):
    results=[]
    for i,x in enumerate((0,.20,.22,.23,.24,.25)):
        a=r.call(label+'-'+str(i),'designer.raycast',{'origin':[a+b for a,b in zip([x,6,2],shift)],'direction':[0,-1,0],'distance':2});assert a['success'],a
        results.append([{'partId':h['partId'],'distance':h['distance']} for h in a['data']['hits']])
    return results
try:
    restore('gold',goldcp);expected=rays('gold-rays')
    for trial in (1,2,3):
        prefix='trial-'+str(trial)
        start=json.loads((fit/(prefix+'-round-0-candidate.json')).read_text())['data']['beforeCheckpointId']
        best=json.loads((fit/(prefix+'-result.json')).read_text())['bestCheckpointId']
        restore(prefix+'-start',start);initial=rays(prefix+'-start-rays')
        r.check(prefix+' actually changed native pick distances/coverage',initial!=expected)
        if not restore(prefix+'-fit',best,True):continue
        actual=rays(prefix+'-fit-rays')
        equal=all(len(a)==len(b) and all(x['partId']==y['partId'] and abs(x['distance']-y['distance'])<=.0001 for x,y in zip(a,b)) for a,b in zip(expected,actual))
        r.check(prefix+' restored native ray hits within 0.1mm',equal,{'gold':expected,'fitted':actual})
finally:
    restore('restore-gold',goldcp)
    a=r.call('final','craft.snapshot',{'includeXml':True});assert a['success'],a
    r.check('gold full XML restored',a['data']['xml']==json.loads((gold/'gold-state.json').read_text())['data']['xml'])
