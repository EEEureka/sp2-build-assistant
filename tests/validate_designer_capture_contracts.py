"""Validate native screenshot discovery/request/response examples, without game writes."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('cli',ROOT/'cli/sp2build.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
schema=cli.schema('designer.capture');Draft202012Validator.check_schema(schema)
v=Draft202012Validator(schema);checks=[]
def check(name,value):
    checks.append({'name':name,'pass':bool(value)})
    if not value:raise AssertionError(name)
for name,payload,valid in [
 ('default',{},True),('current',{'views':['current']},True),
 ('three views',{'views':[{'view':x,'projection':'orthographic'} for x in ('front','right','top')]},True),
 ('custom',{'views':[{'name':'engine-angle','view':'custom','azimuthDegrees':50,'elevationDegrees':20,'projection':'perspective','distance':10,'fieldOfViewDegrees':45}]},True),
 ('fixed scale',{'focusPartIds':[1,3],'views':[{'view':'front','projection':'orthographic','target':[1,2,3],'orthographicSize':2}]},True),
 ('missing custom angle',{'views':[{'view':'custom','azimuthDegrees':30}]},False),
 ('current distance',{'views':[{'distance':30}]},False),
 ('angles require custom',{'views':[{'view':'front','azimuthDegrees':30}]},False),
 ('perspective half height',{'views':[{'projection':'perspective','orthographicSize':2}]},False),
 ('bad resolution',{'resolution':{'width':256}},False),
 ('path traversal',{'views':[{'view':'front','name':'../file'}]},False),
 ('saved file forbidden',{'file':'Aircraft.xml'},False),
]:check(name,v.is_valid({'craftSessionId':'session',**payload})==valid)
camera={'positionWorld':[0,0,10],'targetWorld':[0,0,0],'forwardWorld':[0,0,-1],'upWorld':[0,1,0],
        'rotationQuaternion':[0,1,0,0],'projection':'orthographic','fieldOfViewDegrees':60,'orthographicSize':4,
        'aspect':1.6,'nearClipMetres':.01,'farClipMetres':1000,'worldToCameraRows':[[1,0,0,0]]*4,'projectionRows':[[1,0,0,0]]*4}
status=json.loads((ROOT/'tests/artifacts/staged-build/direct-0.4.10/final-verification/0031-designer.status.json').read_text())['data']
data={'identity':status['identity'],'captureId':'a'*32,'backend':'native_designer_camera','nativeMaterials':True,'includesUi':False,'includesGizmos':False,
      'cameraRestored':True,'sceneIntegrity':status['sceneIntegrity'],'views':[{'name':'front','view':'front','file':'front.png','width':1280,'height':800,'camera':camera,'autoDistance':True,'autoOrthographicSize':False}],
      'artifactBase':'v1/visual/'+'a'*32+'/', 'files':[{'name':'front.png','bytes':100,'sha256':'b'*64}],
      'recommendedImages':['front.png'],'warnings':[],'retention':'example'}
out=cli.contracts_module().output_schema('designer.capture');Draft202012Validator.check_schema(out)
check('typed success example',Draft202012Validator(out).is_valid(cli.ok(data)))
data['views'][0]['camera']['positionWorld']='wrong'
check('wrong camera vector rejected',not Draft202012Validator(out).is_valid(cli.ok(data)))
part=json.loads((ROOT/'tests/artifacts/staged-build/direct-0.4.10/final-verification/0022-part-35.json').read_text())
point=part['data']['part']['attachPoints'][0]
point['positionSource']='live_attach_point_transform'
point['definitionLocalPosition']=[0,.1141,-.2663]
pv=Draft202012Validator(cli.contracts_module().output_schema('parts.get'))
check('additive live attach point source',pv.is_valid(part))
fallback=deepcopy(part)
fallback['data']['part']['attachPoints'][0]['positionSource']='native_part_definition'
check('explicit definition fallback source',pv.is_valid(fallback))
point['definitionLocalPosition']='not a vector'
check('attach point definition vector typed',not pv.is_valid(part))
p=ROOT/'tests/artifacts/designer-capture-0.4.11/contracts.json';p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2))
print('Designer screenshot contracts:',len(checks),'passed')
