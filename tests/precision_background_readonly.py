"""Background diagnostic controls on the current craft; no edits or desktop input.

These small samples distinguish idle/query/render costs. They are not a leak
test or a substitute for the frozen 30/160-cycle acceptance workloads.
"""
import json
import sys
import time
from precision_acceptance import Run
from process_memory import memory

r = Run(sys.argv[1])
count = int(sys.argv[2]) if len(sys.argv) > 2 else 6
assert 1 <= count <= 30

def call(label, command, args=None, images=False):
    result = r.call(label, command, args, images=images)
    assert result['success'], result.get('error')
    return result

base = call('baseline', 'craft.snapshot', {'includeXml': True})['data']
status = call('initial-status', 'designer.status')
pid = status['instancePid']
assert status['data']['sceneIntegrity']['status'] == 'healthy'
guard = {k: base['identity'][v] for k, v in (
    ('craftSessionId', 'craftSessionId'), ('expectedRevision', 'revision'))}
samples = []
first_id = base['parts'][0]['id']

def sample(phase, index, native=None):
    samples.append({'phase': phase, 'index': index, 'os': memory(pid), 'runtimeRetention': native})
    (r.root / 'samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')

def unchanged(label):
    now = call(label, 'craft.snapshot', {'includeXml': True})['data']
    same = now['identity'] == base['identity'] and now['xml'] == base['xml']
    r.check(label + ' full state and identity unchanged', same)
    assert same, 'Craft changed; stop without undoing possible player edits.'

for phase in ('idle', 'properties', 'snapshot', 'capture'):
    s = call(phase + '-status-before', 'designer.status')['data']
    sample(phase, -1, s['runtimeRetention'])
    for i in range(count):
        label = f'{phase}-{i:02}'
        if phase == 'idle':
            time.sleep(3)
        elif phase == 'properties':
            call(label, 'properties.get', {'id': first_id, 'limit': 30})
        elif phase == 'snapshot':
            call(label, 'craft.snapshot', {'includeXml': True})
        else:
            cap = call(label, 'designer.capture', {**guard,
                'views': [{'view': 'current', 'projection': 'current'}],
                'resolution': {'width': 960, 'height': 600}}, images=True)['data']
            r.check(label + ' camera restored', cap['cameraRestored'])
        sample(phase, i)
    unchanged(phase + '-after')
    s = call(phase + '-status-after', 'designer.status')['data']
    r.check(phase + ' healthy single instance', s['sceneIntegrity']['status'] == 'healthy'
            and s['sceneIntegrity']['aircraftInstanceCount'] == 1)
    sample(phase, count, s['runtimeRetention'])

summary = {'craft': base['name'], 'partCount': base['partCount'], 'cyclesPerPhase': count,
    'evidence': 'read_only_background_diagnostic', 'desktopInputUsed': False,
    'meaning': 'Sequential diagnostic phases, not randomized causal attribution or leak certification.',
    'phases': []}
for phase in ('idle', 'properties', 'snapshot', 'capture'):
    rows = [x for x in samples if x['phase'] == phase]
    summary['phases'].append({'phase': phase,
        'privateBytesDelta': rows[-1]['os']['privateBytes'] - rows[0]['os']['privateBytes'],
        'seconds': rows[-1]['os']['time'] - rows[0]['os']['time']})
(r.root / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary), flush=True)
