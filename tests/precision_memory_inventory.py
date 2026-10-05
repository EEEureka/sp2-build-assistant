"""Explicit test-only Unity object census. Does not force garbage collection."""
import json,sys,shutil
from pathlib import Path
from precision_acceptance import Run
from process_memory import memory

r=Run(sys.argv[1]);label=sys.argv[2]
config=Path('D:/apps/steam/steamapps/common/SimplePlanes 2/BepInEx/config')
request=config/'sp2build.acceptance-inventory.json'
result=config/'sp2build.acceptance-inventory.result.json'
assert not request.exists(),'Do not overwrite pending request'
before=r.call('before','designer.status');assert before['success']
assert before['data']['registryVersion']=='0.5.0-dev16'
base=r.call('baseline','craft.snapshot',{'includeXml':True});assert base['success']
assert base['data']['name'].startswith('SP2Build 050 Precision Lab')
request.write_text(json.dumps({'label':label}),encoding='utf-8')
try:
    response=r.call('inventory-status','designer.status');assert response['success'],response
    assert not request.exists(),'Test-only request not consumed'
    report=json.loads(result.read_text(encoding='utf-8-sig'));assert report['label']==label
    shutil.copyfile(result,r.root/'unity-object-inventory.json')
finally:
    if request.exists():request.unlink()
after=r.call('after','craft.snapshot',{'includeXml':True});assert after['success']
r.check('inventory leaves full serialized state unchanged',after['data']['xml']==base['data']['xml'])
(r.root/'memory.json').write_text(json.dumps(memory(response['instancePid']),indent=2))
print(json.dumps({'objects':report['totalObjects'],'sumObjectBytes':report['sumObjectBytes'],'largest':report['types'][:8]},indent=2))
