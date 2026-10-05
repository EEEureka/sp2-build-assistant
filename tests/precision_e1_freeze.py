"""Freeze the existing UI-edited E1 fixture; exports public measured targets.

Preparation used CLI primitives. Nose front width/height and window #8 height/
top width were subsequently edited through the native UI. This is a developer
controlled fitting benchmark, not a blind independent-agent study.
"""
import json, sys, uuid
from precision_acceptance import Run

r=Run(sys.argv[1])
s=r.call('gold-state','craft.snapshot',{'includeXml':True})['data']
assert s['name'] in ('SP2Build 050 Precision Lab F2','SP2Build 050 Precision Lab E1') and s['partCount']==10
by={p['id']:p for p in s['parts']};shift=[by[6]['position'][k]-[0,5,1.65][k] for k in range(3)]
i=s['identity'];guard={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
cp=r.call('gold-checkpoint','craft.checkpoint.create',{**guard,'requestId':uuid.uuid4().hex,'name':'E1 native UI edited target'})['data']['id']
(r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp,'provenance':__doc__},indent=2),encoding='utf-8')
for pid in (5,6):
    a=r.call('shape-'+str(pid),'shape.get',{'id':pid});assert a['success'],a
for pid in range(7,11):
    a=r.call('properties-'+str(pid),'properties.get',{'id':pid,'limit':1000});assert a['success'],a
a=r.call('gold-mesh','geometry.section',{**guard,'partIds':list(range(4,11)),'frame':{'kind':'world'},'plane':{'origin':by[6]['position'],'normal':[0,0,1]},'export':True,'exportMeshes':True},images=True);assert a['success'],a
for label,views in [('plan-side',['top','right']),('front',['front'])]:
    a=r.call('gold-'+label,'designer.capture',{**guard,'focusPartIds':list(range(5,11)),
        'views':[{'view':v,'projection':'orthographic','target':[x+y for x,y in zip([0,5,1.25],shift)],'orthographicSize':1.024} for v in views],
        'resolution':{'width':2048,'height':2048}},images=True);assert a['success'],a
r.check('read operations preserve gold fingerprint',r.call('gold-after','craft.snapshot',{'includeXml':True})['data']['xml']==s['xml'])
