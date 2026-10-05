"""Validate recorded build outputs and 0.4.9 additive input-controller contracts.

New-field examples are synthetic contract tests, not new-DLL runtime acceptance.
"""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('cli', ROOT / 'cli/sp2build.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
contracts = cli.contracts_module()
recordings = ROOT / 'tests/artifacts/staged-build/direct-0.4.8'
checks = []

def check(name, command, data, valid=True):
    validator = Draft202012Validator(contracts.output_schema(command))
    errors = list(validator.iter_errors(data))
    checks.append({'name': name, 'pass': (not errors) == valid,
                   'errors': [str(e)[:800] for e in errors[:2]] if valid else []})

for calls in sorted(recordings.glob('*/calls.jsonl')):
    for line in calls.read_text(encoding='utf-8').splitlines():
        record = json.loads(line)
        path = calls.parent / record['file']
        check(str(path.relative_to(recordings)), record['command'], json.loads(path.read_text(encoding='utf-8')))
recorded_count = len(checks)

fixture = next(recordings.glob('S09-brakeflap-finish/*parts.get.json'))
part = json.loads(fixture.read_text(encoding='utf-8'))
controller = {'index': 0, 'path': 'InputController.State[0]', 'name': 'flap', 'description': None,
              'input': 'Disabled', 'activationGroup': '0', 'invert': False, 'invertType': 'Axis',
              'min': -1, 'max': 1, 'zeroOnDeactivate': True, 'invertOnMirror': False,
              'serializedAttributes': ['input', 'activationGroup', 'invert', 'min', 'max'],
              'valueSource': 'live_part_modifier'}
controllers = [controller, {**controller, 'index': 1, 'path': 'InputController.State[1]', 'name': 'brake', 'input': 'Brake'}]
part['data']['part']['inputControllers'] = controllers
check('typed default omitted from XML and two indexed controllers', 'parts.get', part)
check('shape shares typed controller rows', 'shape.get', cli.ok({'identity': part['data']['identity'], 'partId': 21, 'shape': {'family': 'controlSurface', 'inputControllers': controllers}}))
catalog = json.loads(next(recordings.glob('S07/*catalog.schema.json')).read_text(encoding='utf-8'))
catalog['data']['templates'][0]['parts'][0]['inputControllers'] = [{**controller, 'valueSource': 'isolated_template_modifier'}]
check('unused catalog template has same typed effective values', 'catalog.schema', catalog)
for label, field, invalid in [('boolean is not a string', 'zeroOnDeactivate', 'true'),
                              ('index is nonnegative', 'index', -1),
                              ('path selects controller occurrence', 'path', 'InputController.State.foo'),
                              ('source is explicit', 'valueSource', 'guessed_xml_default')]:
    wrong = deepcopy(part)
    wrong['data']['part']['inputControllers'][0][field] = invalid
    check(label, 'parts.get', wrong, False)
out = ROOT / 'tests/artifacts/contracts-0.4.9/input-controller-and-build.json'
out.parent.mkdir(parents=True, exist_ok=True)
report = {'recordedEnvelopeCount': recorded_count, 'syntheticNewContractCount': len(checks) - recorded_count,
          'passed': sum(c['pass'] for c in checks), 'total': len(checks), 'checks': checks}
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({**{k: v for k, v in report.items() if k != 'checks'}, 'failures': [c for c in checks if not c['pass']]}, ensure_ascii=False))
raise SystemExit(any(not c['pass'] for c in checks))
