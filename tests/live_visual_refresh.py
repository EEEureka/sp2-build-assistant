"""Authorized designer acceptance: async capture, cancellation and temporary shape refresh.

Requires a selected part. Uses the installed CLI and restores a checkpoint in finally.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).parent / 'artifacts' / ('visual-refresh-' + uuid.uuid4().hex[:8])
ROOT.mkdir(parents=True)
CLI = shutil.which('sp2build')
if not CLI:
    raise SystemExit('Global sp2build is required')
checks = []
seq = 0
unknown = False


def call(command, args=None, extra=(), require=True):
    global seq, unknown
    seq += 1
    target = ROOT / f'{seq:03d}-{command.replace(" ", "-")}'
    argv = [CLI, *command.split(), '--timeout', '90', '--output', str(target.with_suffix('.json')), *extra]
    if args is not None:
        request = target.with_suffix('.input.json')
        request.write_text(json.dumps(args), encoding='utf-8')
        argv += ['--input', str(request)]
    try:
        subprocess.run(argv, capture_output=True, timeout=115)
        result = json.loads(target.with_suffix('.json').read_text(encoding='utf-8-sig'))
    except Exception:
        unknown = True
        raise
    if result.get('error', {}).get('code') in ('wait_timeout', 'bridge_unreachable'):
        unknown = True
    if require and not result.get('success'):
        raise RuntimeError(result)
    return result


def check(name, condition):
    checks.append({'name': name, 'pass': bool(condition)})
    print(json.dumps(checks[-1]), flush=True)
    (ROOT / 'report.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')


def guard():
    i = call('designer status')['data']['identity']
    return {'craftSessionId': i['craftSessionId'], 'expectedRevision': i['revision']}


def write(command, **args):
    return call(command, {**guard(), 'requestId': uuid.uuid4().hex, **args})['data']


def capture(part_id):
    data = call('visual capture', {**guard(), 'groups': [{'name': 'fixture', 'selector': {'kind': 'parts', 'partIds': [part_id]}}],
                'resolution': {'width': 384, 'height': 384}}, extra=('--output-dir', str(ROOT / 'images')))['data']
    return data, json.loads(Path(data['manifestPath']).read_text())


before = call('craft snapshot', {'includeXml': True})['data']
history = call('craft history')['data']
selected = call('visual capture', {**guard(), 'resolution': {'width': 384, 'height': 384}}, extra=('--async',))['data']
check('async-returns-operation-without-artifacts', 'operationId' in selected and 'manifestPath' not in selected)
done = call('operation wait', extra=('--id', selected['operationId'], '--output-dir', str(ROOT / 'images')))['data']
manifest = json.loads(Path(done['manifestPath']).read_text())
check('selected-scope-and-async-download', [p['partId'] for p in manifest['parts']] == [before['selectedPartId']] and before['selectedPartId'] is not None)
retry = call('operation result', extra=('--id', selected['operationId'], '--output-dir', str(ROOT / 'retry')))['data']
check('result-can-download-immutable-artifacts-again', Path(done['manifestPath']).read_bytes() == Path(retry['manifestPath']).read_bytes())
cancel = call('visual capture', {**guard(), 'groups': [{'name': 'whole', 'selector': {'kind': 'craft'}}],
              'views': ['front', 'right', 'top', 'isometric', 'back', 'left', 'bottom'], 'resolution': {'width': 1024, 'height': 1024}}, extra=('--async',))['data']
call('operation cancel', extra=('--id', cancel['operationId']))
cancel_result = call('operation wait', extra=('--id', cancel['operationId']), require=False)
check('capture-cancels-with-terminal-error', not cancel_result['success'] and cancel_result.get('error', {}).get('code') == 'cancelled')
readback = call('craft snapshot', {'includeXml': True})['data']
check('async-and-cancel-preserve-aircraft-selection-history', readback['xml'] == before['xml'] and readback['selectedPartId'] == before['selectedPartId'] and call('craft history')['data'] == history)

checkpoint = write('craft checkpoint create', name='Before visual refresh acceptance')['id']
(ROOT / 'recovery.json').write_text(json.dumps({'checkpointId': checkpoint, **guard()}), encoding='utf-8')
error = None
try:
    catalog = call('catalog list', {'limit': 1000})['data']['listing']['items']
    template = next(p['id'] for p in catalog if p['creatable'] and p['partTypes'] == ['JFuselage-1'])
    added = write('batch apply', operations=[{'kind': 'part.add', 'templateId': template, 'temporaryId': 'body', 'position': [20, 15, 0], 'rotation': [0, 0, 0]}])
    part_id = added['temporaryIds']['body']
    original, m1 = capture(part_id)
    saved_hash = hashlib.sha256(Path(original['manifestPath']).read_bytes()).hexdigest()
    write('batch apply', operations=[{'kind': 'shape.update', 'partId': part_id, 'symmetric': False, 'patch': {'length': 6}}])
    expanded, m2 = capture(part_id)
    check('edit-refreshes-real-mesh-and-revision', m2['geometryStamp'] != m1['geometryStamp'] and m2['identity']['revision'] > m1['identity']['revision'] and abs(m2['bounds']['size'][2] - 6) < .001 and not m2['staleAtDelivery'])
    check('previous-download-is-immutable', hashlib.sha256(Path(original['manifestPath']).read_bytes()).hexdigest() == saved_hash)
    ray = call('designer raycast', {'origin': [20,20,2], 'direction': [0,-1,0], 'distance': 20})['data']['hits']
    check('edited-mesh-has-collider-at-sampled-point', any(h['partId'] == part_id for h in ray))
    write('craft undo')
    undone, m3 = capture(part_id)
    check('undo-restores-visual-geometry', m3['geometryStamp'] == m1['geometryStamp'] and m3['bounds'] == m1['bounds'])
    write('batch apply', operations=[{'kind': 'part.update', 'partId': part_id, 'changes': [{'path': '', 'attribute': 'position', 'value': '24,15,0'}]}])
    moved, m4 = capture(part_id)
    check('transform-refreshes-world-spatial-data', abs(m4['bounds']['center'][0] - m3['bounds']['center'][0] - 4) < .001)
    expired = call('visual pick', {'captureId': original['captureId'], 'view': 'front', 'x': 0, 'y': 0}, require=False)
    check('bounded-retention-expires-old-capture', expired.get('error', {}).get('code') == 'artifact_expired')
except Exception as exc:
    error = str(exc)
finally:
    if not unknown:
        restored = write('craft rollback', checkpointId=checkpoint)
        after = call('craft snapshot', {'includeXml': True})['data']
        check('baseline-restoration-verified', restored['validation']['restorationVerified'] and after['partCount'] == before['partCount'] and after['selectedPartId'] == before['selectedPartId'])
    report = {'root': str(ROOT.resolve()), 'passed': sum(c['pass'] for c in checks), 'total': len(checks), 'error': error, 'unknown': unknown}
    (ROOT / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
