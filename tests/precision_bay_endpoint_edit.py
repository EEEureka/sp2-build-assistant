"""Apply the real UI-tested manual hinge target, retaining Animator/input XML."""
import json,sys,uuid,xml.etree.ElementTree as ET
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1])
s=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert s['name']=='SP2Build 050 Precision Lab F2' and len(s['parts'])==11
def guard():
 i=r.call('guard-'+str(len(r.calls)),'craft.snapshot',{'includeXml':True})['data']['identity']
 return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex}
cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'name':'Bay endpoint baseline'})['data']['id']
(r.root/'fixture.json').write_text(json.dumps({'originalCheckpointId':cp}),encoding='utf-8')
patch=json.loads((ROOT/'dev9-bay-manual-ui-parity/observed-ui-changes.json').read_text())['target']
auto=patch.pop('GearBay[0].autoHingeAxis')
ops=[{'kind':'properties.set','partId':10,'symmetric':False,'patch':{'GearBay[0].autoHingeAxis':auto}},
 {'kind':'properties.set','partId':10,'symmetric':False,'patch':patch}]
x=r.call('edit','batch.apply',{**guard(),'operations':ops});assert x['success'],x
a=r.call('after','craft.snapshot',{'includeXml':True})['data']
def preserved(xml):
 root=ET.fromstring(xml)
 return [(p.attrib['id'],ET.tostring(e,encoding='unicode')) for p in root.findall('./Assembly/Parts/Part') for e in p if e.tag.startswith(('Animator.','InputController.'))]
r.check('all Animator and input subtrees preserved exactly',preserved(s['xml'])==preserved(a['xml']))
