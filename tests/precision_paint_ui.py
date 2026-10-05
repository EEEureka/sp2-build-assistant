"""Native paint UI parity on an isolated connected fixture; never edit global themes."""
import json, sys, uuid, shutil
from precision_acceptance import Run, ROOT

r = Run(sys.argv[2])

def call(label, command, args=None, **kw):
    x = r.call(label, command, args, **kw)
    assert x['success'], x
    return x['data']

def snap(label):
    s = call(label, 'craft.snapshot', {'includeXml': True})
    assert s['name'] == 'SP2Build 050 Precision Lab F2'
    assert not s['identity']['stateUncertain']
    return s

def guard():
    i = snap('guard-' + str(len(r.calls)))['identity']
    return {'craftSessionId': i['craftSessionId'], 'expectedRevision': i['revision']}

def apply(label, ops):
    return call(label, 'batch.apply', {**guard(), 'requestId': uuid.uuid4().hex, 'operations': ops})

def checkpoint(label):
    return call(label, 'craft.checkpoint.create', {**guard(), 'requestId': uuid.uuid4().hex, 'name': label})['id']

def restore(label, cp):
    call(label, 'craft.rollback', {**guard(), 'requestId': uuid.uuid4().hex, 'checkpointId': cp})

if sys.argv[1] == 'seed':
    # Reuse an already verified fixture and recorded native target. This is
    # setup only: the next target must be created with real native UI actions.
    prep = ROOT/sys.argv[3]
    f = json.loads((prep/'fixture.json').read_text(encoding='utf-8-sig'))
    patch = json.loads((ROOT/sys.argv[4]/'observed-ui-changes.json').read_text(encoding='utf-8-sig'))['target']
    assert snap('before')['partCount'] == 6
    restore('seed-reset', f['checkpointId'])
    apply('seed-material', [{'kind': 'appearance.set', 'mode': 'shared',
        'materialId': f['materialId'], 'patch': patch}])
    snap('prepared')
    call('prepared-appearance', 'appearance.get', {'partIds': f['partIds']})
    f['checkpointId'] = checkpoint('paint-seeded-baseline')
    (r.root/'fixture.json').write_text(json.dumps(f), encoding='utf-8')
    shutil.copyfile(prep/'baseline.json', r.root/'baseline.json')
elif sys.argv[1] == 'prepare':
    base = snap('baseline')
    assert base['partCount'] == 3
    original = checkpoint('original')
    (r.root/'fixture.json').write_text(json.dumps({'originalCheckpointId': original}))
    added = apply('add-three', [{'kind': 'part.add', 'templateId': 'tpl-f748657136c8ca1a',
        'temporaryId': 'p'+str(i), 'position': [4+i*1.4, 2.25, 0]} for i in range(3)])
    ids = [added['temporaryIds']['p'+str(i)] for i in range(3)]
    apply('connect', [{'kind': 'shape.update', 'partId': p, 'symmetric': False,
                      'patch': {'autoResize': False}} for p in ids] +
                    [{'kind': 'connection.connect', 'partA': p, 'partB': 1,
                      'attachPointA': 0, 'attachPointB': 1, 'symmetric': False} for p in ids])
    a = call('before-material', 'appearance.get', {'partIds': ids})
    slots = [s['slot'] for s in a['parts'][0]['slots'] if s['assignable']]
    source = next(s['materialId'] for s in a['parts'][0]['slots'] if s['assignable'])
    m = apply('shared-fixture-material', [{'kind': 'appearance.set', 'mode': 'clone',
        'materialId': source, 'partIds': ids, 'slots': slots,
        'patch': {'name': 'UI Parity', 'style': 'SolidColor',
                  'colors': [{'index': 0, 'rgba': [.8, .8, .8, 1]}],
                  'metallic': .1, 'smoothness': .25}}])['actualChanges'][0]['materialId']
    snap('prepared')
    call('prepared-appearance', 'appearance.get', {'partIds': ids})
    cp = checkpoint('paint-baseline')
    (r.root/'fixture.json').write_text(json.dumps({'checkpointId': cp,
        'originalCheckpointId': original, 'partIds': ids, 'materialId': m}), encoding='utf-8')
    print({'partIds': ids, 'materialId': m})
else:
    prep = ROOT/sys.argv[3]
    f = json.loads((prep/'fixture.json').read_text(encoding='utf-8-sig'))
    ids, mid = f['partIds'], f['materialId']
    base = json.loads((prep/'prepared.json').read_text(encoding='utf-8-sig'))['data']
    before = json.loads((prep/'prepared-appearance.json').read_text(encoding='utf-8-sig'))['data']
    # A failed replay may reuse the frozen, genuinely UI-created target. Never
    # manufacture a native target with CLI writes to make the comparison pass.
    native_source = ROOT/sys.argv[4] if len(sys.argv) > 4 else None
    if native_source:
        for label in ('native-target', 'native-appearance', 'native-views'):
            shutil.copyfile(native_source/(label+'.json'), r.root/(label+'.json'))
        (r.root/'native-evidence-source.json').write_text(json.dumps({'source': str(native_source),
            'meaning': 'Recorded actual native UI target, not fresh calls or a CLI-created target.'}))
        gold = json.loads((r.root/'native-target.json').read_text(encoding='utf-8-sig'))['data']
        native = json.loads((r.root/'native-appearance.json').read_text(encoding='utf-8-sig'))['data']
    else:
        gold = snap('native-target')
        native = call('native-appearance', 'appearance.get', {'partIds': ids})
    old = next(m for m in before['palette'] if m['id'] == mid)
    new = next(m for m in native['palette'] if m['id'] == mid)
    fields = ('name', 'style', 'colors', 'metallic', 'smoothness', 'emissionDay', 'emissionNight',
              'textureId','texturePresetId','textureBlend','textureOffset','textureRotation','textureScale','textureWrapMode')
    patch = {k: new[k] for k in fields if new[k] != old[k]}
    if 'colors' in patch:
        # null explicitly clears a per-colour override. Preserve changed nulls;
        # dropping them would silently miss the native "inherit" operation.
        changes = []
        for color in patch['colors']:
            prior = next(o for o in old['colors'] if o['index'] == color['index'])
            values = {k: v for k, v in color.items() if k != 'index' and v != prior[k]}
            if values:
                changes.append({'index': color['index'], **values})
        patch['colors'] = changes
    assert patch, 'No native material change observed'
    (r.root/'observed-ui-changes.json').write_text(json.dumps({'target': patch}, indent=2))
    r.check('native UI did not alter global theme', before['globalCustomThemeFingerprint'] == native['globalCustomThemeFingerprint'])
    def capture(label, views=None):
        return call(label, 'designer.capture', {**guard(), 'focusPartIds': ids,
            'views': views or [{'view': 'back', 'projection': 'orthographic'},
                               {'view': 'custom', 'azimuthDegrees': -145, 'elevationDegrees': 25, 'projection': 'perspective'}],
            'resolution': {'width': 1280, 'height': 800}}, images=True)
    views = (json.loads((r.root/'native-views.json').read_text(encoding='utf-8-sig'))['data']
             if native_source else capture('native-views'))['repeatableViews']
    try:
        restore('reset', f['checkpointId'])
        r.check('complete baseline restored', snap('reset-baseline')['xml'] == base['xml'])
        result = apply('replay', [{'kind': 'appearance.set', 'mode': 'shared', 'materialId': mid, 'patch': patch}])
        r.check('only three material users affected', sorted(result['actualChanges'][0]['affectedPartIds']) == sorted(ids))
        r.check('complete native target XML parity', snap('cli-target')['xml'] == gold['xml'])
        after = call('cli-appearance', 'appearance.get', {'partIds': ids})
        r.check('full native palette and slots parity', after['palette'] == native['palette'] and after['parts'] == native['parts'])
        r.check('CLI global theme unchanged', after['globalCustomThemeFingerprint'] == before['globalCustomThemeFingerprint'])
        capture('cli-views', views)
    finally:
        restore('restore', f['checkpointId'])
        r.check('complete fixture restored', snap('restored')['xml'] == base['xml'])
        call('final-status', 'designer.status')
