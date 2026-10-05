"""Integer render-priority boundaries, separate from wrong-type rejection.

Does not claim native UI occlusion parity. Full craft restoration is audited.
"""
import json,sys,uuid,xml.etree.ElementTree as ET
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1])
def call(n,c,a=None):
    x=r.call(n,c,a);assert x['success'],x;return x['data']
def guard(s):
    i=s['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab C17'
fields=[(215,'TextDecal[0].RenderPriority'),(218,'TextureDecal[0].RenderPriority')]
for pid,key in fields:
    d=call('describe-'+str(pid),'properties.get',{'id':pid,'fields':[key]})['parts'][0]['fields'][0]
    assert d['type']=='integer' and d['limits']['min']==-50 and d['limits']['max']==50,d
cp=call('checkpoint','craft.checkpoint.create',{**guard(base),'requestId':uuid.uuid4().hex,'name':'integer priority boundary baseline'})['id']
for pid,key in fields:
    for value in (-51,51):
        label=f'invalid-{pid}-{value}'
        x=r.call(label,'batch.preview',{**guard(base),'operations':[{'kind':'properties.set','partId':pid,'symmetric':False,'patch':{key:value}}]})
        r.check(label+' integer outside range',not x['success'] and x['error']['code']=='property_out_of_range',x.get('error'))
        assert not x['success'] and x['error']['code']=='property_out_of_range',x
now=call('after-previews','craft.snapshot',{'includeXml':True})
r.check('integer range rejections leave full state and revision unchanged',base['xml']==now['xml'] and base['identity']==now['identity'])
try:
    for value in (-50,50):
        call('apply-'+str(value),'batch.apply',{**guard(now),'requestId':uuid.uuid4().hex,'operations':[{'kind':'properties.set','partId':pid,'symmetric':False,'patch':{key:value}} for pid,key in fields]})
        now=call('state-'+str(value),'craft.snapshot',{'includeXml':True})
        expected=ET.fromstring(base['xml'])
        for pid,key in fields:
            part=next(p for p in expected.findall('./Assembly/Parts/Part') if int(p.get('id'))==pid)
            nodes=[n for n in part if 'priority' in n.attrib];assert len(nodes)==1,[n.tag for n in nodes]
            nodes[0].set('priority',str(value))
            f=call(f'effective-{pid}-{value}','properties.get',{'id':pid,'fields':[key]})['parts'][0]['fields'][0]
            r.check(f'effective integer {pid} {value}',f['value']==value,f['value'])
        a=audit(ET.tostring(expected,encoding='unicode'),now['xml']);r.check('full scope at '+str(value),a['equivalent'],a);assert a['equivalent'],a
finally:
    current=call('cleanup-status','designer.status');assert not current['identity']['stateUncertain']
    call('restore','craft.rollback',{**guard(current),'requestId':uuid.uuid4().hex,'checkpointId':cp})
    final=call('final','craft.snapshot',{'includeXml':True});a=audit(base['xml'],final['xml']);r.check('full baseline restored',a['equivalent'],a);assert a['equivalent'],a
    status=call('final-status','designer.status');r.check('healthy single instance',status['sceneIntegrity']['status']=='healthy' and status['sceneIntegrity']['aircraftInstanceCount']==1)
