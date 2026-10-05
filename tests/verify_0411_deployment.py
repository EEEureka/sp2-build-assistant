"""Verify installed release and unchanged live state; never mutates the craft."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from jsonschema import Draft202012Validator

ROOT=Path(__file__).parents[1]
OUT=ROOT/'tests/artifacts/releases/0.4.11'
spec=importlib.util.spec_from_file_location('cli',ROOT/'cli/sp2build.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
cmd=shutil.which('sp2build'); assert cmd
def call(name,*args):
    p=subprocess.run([cmd,*args,'--json'],capture_output=True,encoding='utf-8')
    value=json.loads(p.stdout); (OUT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return value
status=call('status-after-deploy','designer','status')
version=call('cli-version','version')
commands=call('commands-list','commands','list')
schema=call('designer-capture-schema','commands','schema','--command','designer.capture')
points=call('parts-get-schema','commands','schema','--command','parts.get')
assert status['success'] and version['data']['version']=='0.4.11'
before=json.loads((OUT/'status-before-deploy.json').read_text(encoding='utf-8'))
assert before['data']['identity']==status['data']['identity']
assert status['data']['pluginVersion']=='0.4.10'
assert status['data']['sceneIntegrity']['status']=='healthy'
request=OUT/'current-camera-input.json'
request.write_text(json.dumps({'craftSessionId':status['data']['identity']['craftSessionId'],'expectedRevision':status['data']['identity']['revision'],'views':['current']}),encoding='utf-8')
guard=call('old-dll-feature-guard','designer','capture','--input',str(request),'--output-dir',str(OUT/'not-yet-captured'))
assert guard['success'] is False and guard['error']['code']=='unsupported_bridge_feature'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
dll=Path('D:/apps/steam/steamapps/common/SimplePlanes 2/BepInEx/plugins/SP2BuildAssistant.dll')
source=ROOT/'bin/SP2BuildAssistant.dll'
assert sha(dll)==sha(source)
installed=Path(os.environ['USERPROFILE'])/'.sp2build/app'
skill=Path(os.environ['USERPROFILE'])/'.agents/skills/sp2-build-assistant'
hashes=[]
for folder,target in [(ROOT/'cli',installed/'cli'),(ROOT/'skills/sp2-build-assistant',skill)]:
    for file in folder.rglob('*'):
        if not file.is_file() or '__pycache__' in file.parts:continue
        dest=target/file.relative_to(folder)
        item={'file':str(file.relative_to(ROOT)),'target':str(dest),'sha256':sha(file),'matchesInstalled':dest.exists() and sha(dest)==sha(file)}
        hashes.append(item);assert item['matchesInstalled'],item
contract_checks=[]
recordings=ROOT/'tests/artifacts/staged-build/direct-0.4.10'
for calls in sorted(recordings.glob('*/calls.jsonl')):
    for line in calls.read_text(encoding='utf-8').splitlines():
        record=json.loads(line);path=calls.parent/record['file']
        envelope=json.loads(path.read_text(encoding='utf-8'))
        errors=list(Draft202012Validator(cli.contracts_module().output_schema(record['command'])).iter_errors(envelope))
        item={'file':str(path.relative_to(recordings)),'command':record['command'],'pass':not errors,'errors':[str(e)[:500] for e in errors[:2]]}
        contract_checks.append(item)
assert all(c['pass'] for c in contract_checks),[c for c in contract_checks if not c['pass']]
(OUT/'recorded-output-contracts.json').write_text(json.dumps({'passed':len(contract_checks),'checks':contract_checks},ensure_ascii=False,indent=2),encoding='utf-8')
report={'releaseVersion':'0.4.11','loadedPluginVersion':status['data']['pluginVersion'],'buildId':status['data']['buildId'],
        'globalCli':cmd,'dllSha256':sha(dll),'identity':status['data']['identity'],'identityUnchanged':True,
        'sceneIntegrity':status['data']['sceneIntegrity'],'installedFiles':hashes,'recordedEnvelopeContractsPassed':len(contract_checks),
        'runtimeAcceptance':'0.4.10 lifecycle/input reads/turboprop verified; 0.4.11 camera rendering/restoration and live attach points await user restart. No automatic restart.'}
(OUT/'deployment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('identity','installedFiles','sceneIntegrity')},ensure_ascii=False))
print('Verified installed files:',len(hashes))
