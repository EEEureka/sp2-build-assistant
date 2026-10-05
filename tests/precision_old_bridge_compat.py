"""Actual installed CLI 0.5.0 against actual loaded DLL 0.4.11; no mocks."""
import json,sys,uuid
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1])
def ok(n,c,a=None):
 x=r.call(n,c,a);assert x['success'],x;return x['data']
version=ok('cli-version','version');status=ok('loaded','designer.status')
assert version['version']=='0.5.0' and status['pluginVersion']=='0.4.11'
base=ok('before','craft.snapshot',{'includeXml':True});assert base['name']=='SP2Build 050 Precision Lab C17'
history=ok('history-before','craft.history');selection=ok('selection-before','designer.selection')
identity=base['identity'];guard={'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
reference=json.loads((ROOT/'dev14-endurance-30'/'cycle-00-capture.json').read_text(encoding='utf-8-sig'))['data']['repeatableViews'][0]
queries=[('properties.get',{'id':76}),('properties.describe',{'id':76}),('appearance.get',{'partIds':[4]}),
 ('resources.list',{'category':'fonts'}),('decal.pose.get',{'id':215}),
 ('groups.resolve',{**guard,'selector':{'kind':'parts','partIds':[4]}}),
 ('geometry.measure',{**guard,'partIdsA':[76],'partIdsB':[77]}),
 ('designer.capture',{**guard,'views':[reference]})]
for index,(command,args) in enumerate(queries):
 x=r.call(f'reject-read-{index}',command,args)
 r.check(command+' requires new DLL',not x['success'] and x['error']['code']=='unsupported_bridge_feature' and 'operationId' not in x,x.get('error'))
for kind,args in [('properties.set',{'partId':76,'patch':{'ProceduralWindow[0].height':.721}}),
 ('appearance.set',{'mode':'clone','partIds':[4],'patch':{'color':'FF0000'}}),
 ('transform.apply',{'partIds':[4],'frame':{'kind':'world'},'translation':[.001,0,0]}),
 ('decal.pose.set',{'partId':215,'frame':{'kind':'world'},'position':[0,0,0]})]:
 x=r.call('reject-'+kind,'batch.apply',{**guard,'requestId':uuid.uuid4().hex,'operations':[
  {'kind':'part.update','partId':4,'changes':[{'path':'Part','attribute':'name','value':'MUST NOT APPLY'}]},
  {'kind':kind,**args}]})
 r.check(kind+' mixed batch rejected before old edit',not x['success'] and x['error']['code']=='unsupported_bridge_feature' and 'operationId' not in x,x.get('error'))
after=ok('after','craft.snapshot',{'includeXml':True})
r.check('all rejected commands preserve full XML and identity',after['xml']==base['xml'] and after['identity']==base['identity'])
r.check('native and plugin history unchanged',ok('history-after','craft.history')==history)
r.check('selection unchanged',ok('selection-after','designer.selection')==selection)
# Existing public reads remain usable with the installed current client.
for n,c,a in [('part','parts.get',{'id':76}),('geometry','parts.geometry',{'id':76}),('shape','shape.get',{'id':4})]:
 ok('legacy-'+n,c,a)
ok('final-status','designer.status')
