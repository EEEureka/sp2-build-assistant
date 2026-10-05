"""Installed CLI feature gating against a currently older DLL, without writes."""
import sys
import uuid
from precision_acceptance import Run

r = Run(sys.argv[1])
before = r.call('baseline', 'craft.snapshot', {'includeXml': True})
assert before['success']
s = r.call('status', 'designer.status')
assert s['success'] and not s['data'].get('acceptanceNative', {}).get('available')
b = before['data']
x = r.call('reject-unloaded-native-action', 'acceptance.native', {
    'craftSessionId': b['identity']['craftSessionId'], 'expectedRevision': b['identity']['revision'],
    'expectedCraftName': 'SP2Build 050 Precision Lab F2', 'requestId': uuid.uuid4().hex, 'action': 'reload'})
r.check('unloaded feature rejected before native action', not x['success'] and x.get('error', {}).get('code') == 'acceptance_build_required')
after = r.call('after', 'craft.snapshot', {'includeXml': True})
assert after['success']
r.check('current player craft complete state and identity unchanged', after['data']['xml'] == b['xml'] and after['data']['identity'] == b['identity'])
schema = r.call('native-schema', 'commands.schema', extra_args=('--command', 'acceptance.native'))
r.check('installed native schema is available offline', schema['success'] and bool(schema['data']['outputSchema']['properties']['data']['properties'].get('controls')))
assert all(c['status'] == 'pass' for c in r.checks)
