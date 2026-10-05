"""Opt-in, separate background test host. Not a production craft loader."""
import json
import os
from pathlib import Path
import time
import uuid


def execute(options, error):
    if not options.get('host'):
        raise error('invalid_input', 'Test host requires --host DIRECTORY returned by its controlled launcher.')
    root = Path(options['host']).resolve()
    info = json.loads((root / 'host.json').read_text(encoding='utf-8-sig'))
    if info.get('protocol') != 1 or info.get('batchMode') is not True:
        raise error('invalid_input', 'Not an opted-in batch-mode acceptance host.')
    action = options.get('action', 'status')
    if action not in ('status', 'load', 'load-function-tree-control', 'shutdown', 'lighting', 'modifier-symmetry', 'heap-inventory', 'mesh-lifetime-reference', 'expression-template-reference'):
        raise error('invalid_input', 'Unknown test-host action.')
    request = {'token': info['token'], 'action': action}
    if action in ('heap-inventory','mesh-lifetime-reference','expression-template-reference'):
        craft = options.get('expected-craft-name', '')
        if not craft.startswith('SP2Build 050 Precision Lab '):
            raise error('invalid_input', 'Heap metadata probe is limited to an exact native test fixture.')
        request['expectedCraftName'] = craft
    if action in ('load','load-function-tree-control'):
        if options.get('fixture') not in ('F2', 'C17', 'E1', 'E2', 'E3') or not options.get('expected-craft-name'):
            raise error('invalid_input', 'Loading is limited to fixed acceptance fixtures with an exact current craft guard.')
        request.update(fixture=options['fixture'], expectedCraftName=options['expected-craft-name'])
    if action == 'lighting':
        value=float(options.get('day-night-value', 'nan'))
        if not 0 <= value <= 1 or not options.get('expected-craft-name'):
            raise error('invalid_input', 'Lighting probe requires native dayNightValue in [0,1] and exact current test craft name.')
        request.update(dayNightValue=value,expectedCraftName=options['expected-craft-name'])
    if action == 'modifier-symmetry':
        if options.get('enabled') not in ('true', 'false') or options.get('expected-craft-name')!='SP2Build 050 Precision Lab F2':
            raise error('invalid_input', 'Native modifier toggle requires --enabled true/false and exact F2 lab name.')
        try: part_id=int(options['part-id'])
        except (KeyError,ValueError,TypeError): raise error('invalid_input', 'Native modifier toggle needs --part-id INTEGER.')
        request.update(partId=part_id,enabled=options['enabled']=='true',expectedCraftName=options['expected-craft-name'])
    identity = uuid.uuid4().hex
    path = root / ('request-' + identity + '.json')
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(request), encoding='utf-8')
    os.replace(temp, path)
    limit = time.monotonic() + min(float(options.get('timeout', 30)), 300)
    result = root / ('result-' + identity + '.json')
    while time.monotonic() < limit:
        if result.is_file():
            return json.loads(result.read_text(encoding='utf-8-sig'))
        time.sleep(.1)
    # A timed-out load may already have started; do not resubmit it blindly.
    raise error('wait_timeout', 'Test host did not answer; query status before retrying.', requestId=identity)
