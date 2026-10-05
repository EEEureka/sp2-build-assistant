"""Read the native preview state selected through the visible designer UI."""
import sys
from precision_acceptance import Run
r=Run(sys.argv[1]);ids=list(map(int,sys.argv[2].split(',')))
s=r.call('snapshot','craft.snapshot',{'includeXml':True})
assert s['success'] and s['data']['name']=='SP2Build 050 Precision Lab F2'
i=s['data']['identity'];guard={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
r.call('selection','designer.selection')
for pid in ids:r.call('properties-'+str(pid),'properties.get',{'id':pid,'limit':1000})
x=r.call('mesh','geometry.section',{**guard,'partIds':ids,'frame':{'kind':'world'},'plane':{'origin':[0,0,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True)
assert x['success'],x
x=r.call('views','designer.capture',{**guard,'focusPartIds':ids,'views':[{'view':'back','projection':'orthographic'},{'view':'right','projection':'orthographic'},{'view':'custom','azimuthDegrees':215,'elevationDegrees':20,'projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True)
assert x['success'],x
after=r.call('after','craft.snapshot',{'includeXml':True})
r.check('read preserves complete serialized state',s['data']['xml']==after['data']['xml'])
