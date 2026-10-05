"""Actual native reserved engine slot and a full per-craft palette; restore F2."""
import json,sys,uuid
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1])
def call(n,c,a=None):
    x=r.call(n,c,a);assert x['success'],x;return x['data']
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def snap(n):return call(n,'craft.snapshot',{'includeXml':True})
def write(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def reject(n,op,code):
    before=snap(n+'-before');x=r.call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[op]})
    r.check(n+' rejects',not x['success'] and x['error']['code']==code,x.get('error'))
    proof=audit(before['xml'],snap(n+'-after')['xml']);r.check(n+' atomic unchanged',proof['equivalent'],proof)
    assert not x['success'] and proof['equivalent'],x
base=snap('baseline');assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'palette boundaries'})['id']
look=call('appearance-baseline','appearance.get',{'partIds':[1,2,3]});global_before=look['globalCustomThemeFingerprint']
try:
    add=write('add-engine',[{'kind':'part.add','templateId':'tpl-1a5ee3557bbab375','position':[4,2.25,0],'temporaryId':'engine'}])
    ids=[p['id'] for p in snap('fixture')['parts']]
    look=call('actual-slots','appearance.get',{'partIds':ids})
    source=next(m['id'] for m in look['palette'] if not m['reserved']);slot=next(s['slot'] for p in look['parts'] if p['partId']==1 for s in p['slots'] if s['assignable'])
    reserved=[(p['partId'],s['slot'],s['materialId']) for p in look['parts'] for s in p['slots'] if not s['assignable']];assert reserved,'No native reserved slot in discovered fixture'
    reject('reserved-slot',{'kind':'appearance.set','mode':'assign','materialId':source,'partIds':[reserved[0][0]],'slots':[reserved[0][1]]},'reserved_material_slot')
    reject('reserved-source',{'kind':'appearance.set','mode':'shared','materialId':reserved[0][2],'patch':{'metallic':.2}},'material_not_editable')
    capacity=look['editablePaletteCapacity'];remaining=capacity-sum(not m['reserved'] for m in look['palette']);assert 0<remaining<100
    clone={'kind':'appearance.set','mode':'clone','materialId':source,'partIds':[1],'slots':[slot],'patch':{'name':'capacity sample','style':'SolidColor','metallic':.1}}
    write('fill-palette',[{**clone,'patch':{**clone['patch'],'name':'capacity '+str(i)}} for i in range(remaining)])
    full=call('full-palette','appearance.get',{'partIds':ids});r.check('reaches exact public capacity',sum(not m['reserved'] for m in full['palette'])==capacity,{'capacity':capacity,'created':remaining})
    reject('over-capacity',clone,'palette_capacity')
    r.check('global theme unchanged at capacity',call('global-after','appearance.get',{'partIds':[1]})['globalCustomThemeFingerprint']==global_before)
finally:
    call('restore-original','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
    proof=audit(base['xml'],snap('final')['xml']);r.check('complete original restored',proof['equivalent'],proof)
    r.check('global theme unchanged after recovery',call('global-final','appearance.get',{'partIds':[1]})['globalCustomThemeFingerprint']==global_before)
    s=call('final-status','designer.status');r.check('healthy one aircraft',s['sceneIntegrity']['status']=='healthy' and s['sceneIntegrity']['aircraftInstanceCount']==1)
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
