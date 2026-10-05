"""Native API reference checks without computer use, only on a three-part F2.

Requires a loaded dev17 acceptance DLL. No save file is read, written or loaded.
The callback result is compared against the public setter and complete XML.
"""
import json
import sys
import uuid
from precision_acceptance import Run
from review_restore_state import audit

r = Run(sys.argv[1])
name = 'SP2Build 050 Precision Lab F2'

def call(label, command, args=None):
    result = r.call(label, command, args)
    assert result['success'], result
    return result['data']

def snap(label):
    s = call(label, 'craft.snapshot', {'includeXml': True})
    assert s['name'] == name and not s['identity']['stateUncertain']
    return s

def guard(s=None):
    s = s or snap('guard-' + str(len(r.calls)))
    return {'craftSessionId': s['identity']['craftSessionId'], 'expectedRevision': s['identity']['revision']}

def native(label, action, **kwargs):
    return call(label, 'acceptance.native', {**guard(), 'requestId': uuid.uuid4().hex,
        'expectedCraftName': name, 'action': action, **kwargs})

def same(label, first, second):
    result = audit(first['xml'], second['xml'])
    r.check(label, result['equivalent'], result)
    assert result['equivalent'], result

status = call('status', 'designer.status')
assert status.get('acceptanceNative', {}).get('available'), 'Load the dev17 acceptance DLL first.'
base = snap('baseline')
assert base['partCount'] == 3
cp = call('checkpoint', 'craft.checkpoint.create', {**guard(base), 'requestId': uuid.uuid4().hex, 'name': 'background native original'})['id']
try:
    added = call('add-window', 'batch.apply', {**guard(), 'requestId': uuid.uuid4().hex,
        'operations': [{'kind': 'part.add', 'templateId': 'tpl-a0c296e1a01292ad',
            'temporaryId': 'native-window', 'position': [4, 4, 0]}]})
    part = added['temporaryIds']['native-window']
    prepared = snap('prepared')
    controls = native('inspect', 'inspect', partId=part, modifierType='ProceduralWindowData')
    height = next(c for c in controls['controls'] if c['member'] == '_height')
    assert height['referenceSetterSupported'] and height['visible']
    target = 0.731 if abs(height['value'] - 0.731) > 0.01 else 0.813
    native('native-set', 'property', partId=part, modifierType='ProceduralWindowData', member='_height', value=target)
    expected = snap('native-target')
    native('native-undo', 'undo')
    same('native Undo restores prepared state', prepared, snap('after-undo'))
    native('native-redo', 'redo')
    same('native Redo restores native target', expected, snap('after-redo'))
    native('native-undo-again', 'undo')
    call('public-set', 'batch.apply', {**guard(), 'requestId': uuid.uuid4().hex,
        'operations': [{'kind': 'properties.set', 'partId': part, 'symmetric': False,
            'patch': {'ProceduralWindow[0].height': target}}]})
    same('public setter matches independent native callbacks', expected, snap('public-target'))
finally:
    # Explicit content recovery. Never roll back into another craft or session.
    now = call('before-cleanup', 'craft.snapshot', {'includeXml': True})
    assert now['name'] == name and now['identity']['craftSessionId'] == base['identity']['craftSessionId']
    call('cleanup', 'craft.rollback', {**guard(now), 'requestId': uuid.uuid4().hex, 'checkpointId': cp})
    same('original three-part fixture recovered', base, snap('clean'))

before_reload = snap('before-reload')
native('reload-live-test-craft', 'reload')
after_reload = snap('after-reload')
same('native reload preserves current complete content', before_reload, after_reload)
r.check('native reload changes session', before_reload['identity']['craftSessionId'] != after_reload['identity']['craftSessionId'])
stale = r.call('reject-old-session', 'acceptance.native', {**guard(before_reload),
    'requestId': uuid.uuid4().hex, 'expectedCraftName': name, 'action': 'reload'})
r.check('old session rejected before native action', not stale['success'] and stale.get('error', {}).get('code') == 'session_conflict')
same('stale rejection preserves current content', after_reload, snap('final'))
(r.root / 'evidence-kind.json').write_text(json.dumps({'source': 'native_api_callback_not_desktop_ui',
    'desktopInputUsed': False, 'meaning': 'Does not certify pointer hit testing or UI widgets.'}, indent=2), encoding='utf-8')
