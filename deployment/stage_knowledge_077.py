"""Stage curated knowledge and contracts, never import audit/private resources."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk'))
from sp2model.knowledge import COMMANDS,Knowledge,bundle_id,BUNDLE_SCHEMA,SOURCE_KEYS
from sp2model.updates import COMMANDS as UPDATE_COMMANDS, RELEASE

def main():
    folder=ROOT/'knowledge/v077';files=[];documents=[]
    for name in ('parts.json','funky.json'):
        p=folder/name;raw=p.read_bytes();documents.append(json.loads(raw))
        files.append({'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    source={k:documents[0]['source'][k] for k in SOURCE_KEYS}
    assert all({k:d['source'][k] for k in SOURCE_KEYS}==source for d in documents),'Source provenance differs'
    manifest={'schemaVersion':BUNDLE_SCHEMA,'datasetId':bundle_id(files),'files':files,**source,
              'productVersion':'0.7.7a1','scope':'Curated versioned knowledge. Not writable-field authority or runtime certification.'}
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf8')
    status=Knowledge(resource_dir=folder).status()
    assert status['available'],status
    target=ROOT/'sdk/sp2model/resources/knowledge/v077';target.mkdir(parents=True,exist_ok=True)
    for name in ('parts.json','funky.json','manifest.json'):shutil.copyfile(folder/name,target/name)
    contracts=ROOT/'sdk/sp2model/resources/contracts.json';catalog=json.loads(contracts.read_text(encoding='utf8'))
    catalog['sourceVersion']=RELEASE['sdkVersion'];catalog['commands'].update(COMMANDS);catalog['commands'].update(UPDATE_COMMANDS)
    contracts.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'datasetId':manifest['datasetId'],'files':files,'collections':status['collections'],'newCommands':sorted(COMMANDS)},ensure_ascii=False))

if __name__=='__main__':main()
