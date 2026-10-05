"""Small read-only acceptance of the final release guards and artifact delivery."""
import json
from pathlib import Path
import shutil
import subprocess
import uuid

root = Path(__file__).parent / 'artifacts' / ('visual-release-' + uuid.uuid4().hex[:8])
root.mkdir(parents=True)
cli = shutil.which('sp2build')
checks = []


def call(name, command, args=None):
    argv = [cli, *command.split(), '--output', str(root / (name + '.json')), '--timeout', '90']
    if args is not None:
        path = root / (name + '.input.json')
        path.write_text(json.dumps(args), encoding='utf-8')
        argv += ['--input', str(path)]
    if command == 'visual capture':
        argv += ['--output-dir', str(root / 'images')]
    subprocess.run(argv, capture_output=True, timeout=115)
    return json.loads((root / (name + '.json')).read_text())


def check(name, passed):
    checks.append({'name': name, 'pass': bool(passed)})
    print(json.dumps(checks[-1]), flush=True)


status = call('status', 'designer status')['data']
check('release-build-loaded', status['buildId'] == '3c86faf6-5b70-4667-8b7f-a32f96b3392f' and status['designerReady'])
before = call('before', 'craft snapshot', {'includeXml': True})['data']
history = call('history-before', 'craft history')['data']
guard = {'craftSessionId': before['identity']['craftSessionId'], 'expectedRevision': before['identity']['revision']}
ids = [p['id'] for p in before['parts'][:2]]
groups = [{'name': 'part-' + str(id), 'selector': {'kind': 'parts', 'partIds': [id]}} for id in ids]
for name in ('overview', 'con'):
    bad = call('reserved-' + name, 'visual capture', {**guard, 'groups': groups[:1], 'views': [{'name': name, 'direction': [0,0,-1], 'up': [0,1,0]}]})
    check('reject-reserved-' + name, bad.get('error', {}).get('code') == 'invalid_view')
bad = call('odd-overview-budget', 'visual capture', {**guard, 'groups': groups, 'views': ['front','right','top','left','bottom'], 'details': 'perGroup', 'resolution': {'width':880,'height':880}})
check('reject-actual-pixel-count-over-budget', bad.get('error', {}).get('code') == 'render_budget')
body = next(p['id'] for p in before['parts'] if p['type'] == 'JFuselage-1')
capture = call('current-fuselage', 'visual capture', {**guard, 'groups': [{'name': 'body', 'selector': {'kind': 'parts', 'partIds': [body]}}], 'details':'perGroup', 'resolution':{'width':384,'height':384}})
check('release-download-and-complete-geometry', capture.get('success') and capture['data']['complete'] and not capture['data']['staleAtDelivery'] and Path(capture['data']['manifestPath']).is_file())
after = call('after', 'craft snapshot', {'includeXml': True})['data']
check('release-preserves-current-craft-and-history', before['xml'] == after['xml'] and before['selectedPartId'] == after['selectedPartId'] and history == call('history-after','craft history')['data'])
report = {'root':str(root.resolve()),'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks}
(root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
