"""Verify a staged/installed global SDK and SDK-first skill, without game writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
from email.parser import Parser
import sp2model

def main():
    p=argparse.ArgumentParser();p.add_argument('--wheel',required=True);p.add_argument('--skill',required=True);p.add_argument('--output')
    a=p.parse_args();skill=Path(a.skill).resolve();entry=(skill/'SKILL.md').read_text(encoding='utf-8-sig')
    assert 'name: sp2-build-assistant' in entry and len(entry)<8192
    core=re.search(r'<!-- core:start -->\n(.*?)\n<!-- core:end -->',entry,re.S).group(1)
    assert re.findall(r'^C\d\d\.',core,re.M)==[f'C{i:02d}.' for i in range(1,9)]
    assert 'related impact' in core and 'installed `sp2model`' in core
    assert 'never a substitute Python entrypoint' not in entry
    for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)',entry):
        assert (skill/target).is_file(),target
    with zipfile.ZipFile(a.wheel) as wheel:
        installed=Path(sp2model.__file__).parent;modules=[]
        metadata_name=next(name for name in wheel.namelist() if name.endswith('.dist-info/METADATA'))
        wheel_version=Parser().parsestr(wheel.read(metadata_name).decode())['Version']
        for name in wheel.namelist():
            if name.startswith('sp2model/') and name.endswith('.py'):
                assert (installed/Path(name).relative_to('sp2model')).read_bytes()==wheel.read(name),name
                modules.append(name)
            elif name.startswith('sp2model/') and not name.endswith('/'):
                assert (installed/Path(name).relative_to('sp2model')).read_bytes()==wheel.read(name),name
    assert sp2model.__version__==wheel_version
    assert {path.relative_to(installed).as_posix() for path in installed.rglob('*.py')}=={Path(name).relative_to('sp2model').as_posix() for name in modules}
    if wheel_version.startswith('0.7.2'):
        assert len(modules)==20 and hasattr(sp2model.Session,'task') and hasattr(sp2model.Plan,'wing_sections')
        assert (skill/'references/Modeling-Workflow.md').is_file() and (skill/'references/Advanced-Native.md').is_file()
    if wheel_version.startswith(('0.7.3', '0.7.4', '0.7.6', '0.7.7', '0.7.8')):
        assert hasattr(sp2model, 'Runtime') and hasattr(sp2model.Session, 'native_plan')
        assert (skill/'references/Services.md').is_file()
        assert 'sp2build ' not in entry and '`sp2build`' not in entry
        assert not (installed/'_services/sp2build.py').exists()
    if wheel_version.startswith(('0.7.4','0.7.6','0.7.7','0.7.8')):
        assert (skill/'references/Modeling-Semantic-Workflow.md').is_file()
        assert (skill/'examples/semantic_reference.json').is_file()
        assert all((installed/(name+'.py')).is_file() for name in ('modeling','model_host','model_help','model_geometry','model_compare','reference_registry','delivery'))
        assert 'sp2model model capabilities' in entry
    if wheel_version.startswith(('0.7.7','0.7.8')):
        from sp2model import Runtime
        journal = Path(a.output or a.wheel).parent/'must-not-be-created'
        assert not journal.exists()
        knowledge = Runtime(journal_dir=journal).call('knowledge.status')
        assert not journal.exists()
        assert knowledge['available'] and knowledge['collections']['templates'] == 160
        assert knowledge['collections']['sourceFields'] == 1318
        assert knowledge['collections']['functions'] == 35
        assert (skill/'references/Knowledge.md').is_file() and (skill/'references/Knowledge-Funky.md').is_file()
        assert 'knowledge index' in entry
    if wheel_version.startswith('0.7.8'):
        assert hasattr(sp2model.Runtime, 'updates')
        assert (skill/'references/Updates.md').is_file()
        assert 'sp2model updates guide' in entry
    migration=json.loads((skill/'references/rule-migration.json').read_text(encoding='utf-8-sig'))
    if wheel_version.startswith(('0.7.6','0.7.7','0.7.8')):
        assert hasattr(sp2model.Plan, 'clip_plane')
        assert (installed/'hard_surfaces.py').is_file()
        assert (skill/'references/Hard-Surfaces.md').is_file()
        assert 'expectation' in core and 'revise locally and remeasure' in core
    digest=hashlib.sha256(core.encode()).hexdigest()
    assert migration['topics']['core']['sha256']==digest
    report={'status':'passed','sdkVersion':sp2model.__version__,'installedSdk':str(installed),'modulesCompared':modules,
        'wheelSha256':hashlib.sha256(Path(a.wheel).read_bytes()).hexdigest(),'skill':str(skill),
        'skillSha256':hashlib.sha256((skill/'SKILL.md').read_bytes()).hexdigest(),'skillCharacters':len(entry),'coreSha256':digest}
    if a.output:Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
