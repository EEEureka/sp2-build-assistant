"""Verify installed files, loaded module identity and distributable archives.

Read-only game probes; invocation requires the exact owned fixture PID.
Does not promote a pending memory or visual gate to passed.
"""
import argparse,hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--instance',required=True)
p.add_argument('--build-audit',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--expected-status',required=True)
p.add_argument('--packages',action='store_true')
p.add_argument('--recorded-live',action='store_true',help='After native shutdown, reuse this output directory\'s previously captured live probes; only files/packages are rechecked now.')
args=p.parse_args();root=Path(__file__).resolve().parents[1];args.out.mkdir(parents=True,exist_ok=True)
cli=shutil.which('sp2build');assert cli,'Global launcher missing'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def call(label,*command):
 if args.recorded_live:
  result=json.loads((args.out/(label+'.json')).read_text(encoding='utf-8'))
  assert result['success'],result
  return result['data']
 result=json.loads(subprocess.check_output([cli,*command,'--instance',args.instance,'--json'],text=True,encoding='utf-8'))
 (args.out/(label+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 assert result['success'],result
 return result['data']
status=call('loaded-status','designer','status');version=call('cli-version','version')
assert version['version']==status['pluginVersion']=='0.5.0'
assert status['releaseStatus']==args.expected_status
lifetime=status['runtimeRetention']['nativeMeshLifetime']
assert lifetime['installed'] and lifetime['conversions']==lifetime['releases'],lifetime
expression=status['runtimeRetention']['expressionLifetime']
assert expression['installed'] and expression['templates']['count']<=expression['templates']['limit'],expression
audit=json.loads(args.build_audit.read_text(encoding='utf-8-sig'))
shipping=next(x for x in audit if not x['acceptanceHooks']);assert shipping['passed']
assert status['buildId']==shipping['buildId'],(status['buildId'],shipping['buildId'])
built=root/'bin/SP2BuildAssistant.dll';installed=Path('D:/apps/steam/steamapps/common/SimplePlanes 2/BepInEx/plugins/SP2BuildAssistant.dll')
assert sha(built)==sha(installed)==shipping['sha256'].lower()
manifest=json.loads((root/'bin/build-manifest.json').read_text(encoding='utf-8-sig'))
assert manifest['acceptanceHooks'] is False and manifest['sha256'].lower()==sha(built)
files=[];app=Path.home()/'.sp2build/app';skill=Path.home()/'.agents/skills/sp2-build-assistant'
for folder,target in [(root/'cli',app/'cli'),(root/'knowledge',app/'knowledge'),
                       (root/'skills',app/'skills'),(root/'skills/sp2-build-assistant',skill)]:
 for src in folder.rglob('*'):
  if not src.is_file() or '__pycache__' in src.parts:continue
  dest=target/src.relative_to(folder)
  row={'source':str(src.relative_to(root)),'target':str(dest),'sha256':sha(src),'matches':dest.is_file() and sha(src)==sha(dest)}
  files.append(row);assert row['matches'],row
archives=[]
if args.packages:
 for name in ['SP2BuildAssistant-0.5.0','SP2BuildAssistant-Skill-0.5.0']:
  file=root/'dist'/(name+'.zip')
  with zipfile.ZipFile(file) as z:
   names=[n.replace('\\','/') for n in z.namelist()]
   forbidden=[n for n in names if any(x in n.split('/') for x in ('tests','__pycache__','Game.dll','SP2AcceptanceHost.dll','SP2HeapProbe.dll','host.json')) or n.endswith('.previous')]
   assert not forbidden,forbidden
   if '-Skill-' not in name:
    assert hashlib.sha256(z.read(name+'/bin/SP2BuildAssistant.dll')).hexdigest()==sha(built)
    assert not json.loads(z.read(name+'/bin/build-manifest.json').decode('utf-8-sig'))['acceptanceHooks']
   for src in (root/'skills/sp2-build-assistant').rglob('*'):
    if not src.is_file():continue
    prefix=name+('/sp2-build-assistant/' if '-Skill-' in name else '/skills/sp2-build-assistant/')
    assert z.read(prefix+src.relative_to(root/'skills/sp2-build-assistant').as_posix())==src.read_bytes()
   archives.append({'path':str(file),'sha256':sha(file),'entries':len(names),'forbidden':forbidden})
report={'globalCli':cli,'version':version,'releaseStatus':status['releaseStatus'],'loadedBuildId':status['buildId'],
        'liveEvidence':'previously captured before native shutdown' if args.recorded_live else 'captured in this invocation',
        'nativeMeshLifetime':lifetime,
        'expressionLifetime':expression,
        'dllSha256':sha(built),'installedFileCount':len(files),'files':files,'archives':archives,
        'scope':'Installed/published bits and loaded module verified; functional gate results are documented separately.'}
(args.out/'deployment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='files'},ensure_ascii=False,indent=2))
