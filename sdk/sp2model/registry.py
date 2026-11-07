"""Versioned public native/service contracts, independent of the retired CLI."""
from copy import deepcopy
import json
from pathlib import Path
from .errors import ModelingError
from .transport import canonical_json

RESOURCES = Path(__file__).resolve().parent / 'resources'
_CATALOG = json.loads((RESOURCES / 'contracts.json').read_text(encoding='utf-8'))
from .knowledge import COMMANDS as _KNOWLEDGE_COMMANDS
_CATALOG['commands'].update(deepcopy(_KNOWLEDGE_COMMANDS))
from .updates import COMMANDS as _UPDATE_COMMANDS
_CATALOG['commands'].update(deepcopy(_UPDATE_COMMANDS))
for _row in _CATALOG['commands'].values():
    _scope = _row['inputSchema'].get('properties', {}).get('modelScope')
    if isinstance(_scope, dict):
        _scope['properties']['writableMaterialIds'] = {'type': 'array', 'maxItems': 50, 'uniqueItems': True, 'items': {'type': 'integer', 'minimum': 0}}
ALIASES = {name: row['operationKind'] for name, row in _CATALOG['commands'].items() if row.get('operationKind')}
SDK_ONLY = {
    'scope.capture': 'Session.scope(parts,boundary=(),owner_id=...)', 'scope.release': 'NativeScope.release()',
    'scoped.batch.apply': 'NativeScope.preview()/apply()', 'craft.undo': 'Session.undo_preview()/undo()',
    'craft.rollback': 'Session.restore_preview()/restore()', 'craft.checkpoint.create': 'Session.checkpoint()',
    'craft.checkpoint.prune': 'Session.prune_checkpoints()',
}


def public_path(name, row):
    if name in _UPDATE_COMMANDS: return 'Runtime.updates.%s(...) or Runtime.call(%r, arguments)' % (name.split('.')[1], name)
    if name in _KNOWLEDGE_COMMANDS: return 'Runtime.knowledge.%s(...) or Runtime.call(%r, arguments)' % (name.split('.')[1], name)
    if name in SDK_ONLY: return SDK_ONLY[name]
    if name in ALIASES or name in ('batch.apply', 'batch.preview'): return 'Session.native_plan(...).preview()/apply() or reviewed CLI batch'
    if name == 'designer.control': return 'Runtime.control(...) or guarded CLI designer control'
    if name.startswith('operation.'): return 'Runtime.operation(id,action=%r)' % name.split('.')[1]
    return ('Session.service(%r, **arguments)' if row['execution'] == 'local_with_live' else 'Runtime.call(%r, arguments)') % name


def commands(*, include_test_only=False):
    return [{'name': name, 'execution': row['execution'], 'mutates': row['mutates'],
             'operationKind': row.get('operationKind'),
             'invocation': None if name in SDK_ONLY else 'sp2model ' + name.replace('.', ' '),
             'python': public_path(name, row), 'cliAvailable': name not in SDK_ONLY and row['execution'] != 'testOnly',
             'schemaQuery': 'sp2model commands schema --command ' + name}
            for name, row in sorted(_CATALOG['commands'].items())
            if include_test_only or row['execution'] != 'testOnly']


def contract(name, *, operation=False):
    table = _CATALOG['operations' if operation else 'commands']
    if name not in table:
        raise ModelingError('unsupported_command', 'Unknown operation kind or command.', {'name': name})
    value = deepcopy(table[name])
    if not operation:
        if name in ALIASES:
            value['inputSchema']['properties']['modelScope'] = deepcopy(_CATALOG['commands']['batch.apply']['inputSchema']['properties']['modelScope'])
            value['inputSchema']['required'].append('modelScope')
            value['inputSchema']['properties'].pop('requestId', None)
        if name in ALIASES or name in ('batch.apply', 'batch.preview'):
            value['inputSchema']['properties']['modelScope']['required'] = ['writablePartIds']
            if 'modelScope' not in value['inputSchema']['required']: value['inputSchema']['required'].append('modelScope')
        original = value['outputSchema']
        value['nativeEnvelopeSchema'] = original
        value['outputSchema'] = {'type': 'object', 'required': ['schemaVersion', 'ok', 'action'],
            'properties': {'schemaVersion': {'const': 'sp2model.host/1'}, 'ok': {'type': 'boolean'}, 'action': {'type': ['string', 'null']},
                           'result': original.get('properties', {}).get('data', {}), 'error': {'type': 'object'}, 'transport': {'type': 'object'},
                           'notices': {'type': 'array', 'items': {'type': 'object'}, 'description': 'Bounded local update policy. Preserves the original result; not player acknowledgement or install authorization.'}},
            'oneOf': [{'properties': {'ok': {'const': True}}, 'required': ['result']}, {'properties': {'ok': {'const': False}}, 'required': ['error']}],
            '$defs': original.get('$defs', {})}
        value['publicPath'] = public_path(name, value)
        value['pythonResult'] = 'Unwrapped native/service data; the command host adds ok/result/transport.'
    return value


def schema(name, *, operation=False):
    return contract(name, operation=operation) if operation else contract(name)['inputSchema']


def validate(value, spec, path='$'):
    """Validate request structure; native semantic/domain checks remain decisive.

    Covers the bundled input contracts, including conditions and alternatives.
    Does not claim to implement arbitrary third-party JSON Schema documents.
    """
    canonical_json(value)
    def fail(reason):
        raise ModelingError('invalid_input', reason, {'path': path})
    for key in ('oneOf', 'anyOf'):
        if key in spec:
            count = 0
            for option in spec[key]:
                try: validate(value, option, path); count += 1
                except ModelingError: pass
            if not count or key == 'oneOf' and count != 1: fail('Value does not match ' + key)
    for option in spec.get('allOf', []): validate(value, option, path)
    if 'not' in spec:
        try: validate(value, spec['not'], path)
        except ModelingError: pass
        else: fail('Value matches a forbidden combination')
    if 'if' in spec:
        try: validate(value, spec['if'], path); branch = 'then'
        except ModelingError: branch = 'else'
        validate(value, spec.get(branch, {}), path)
    types = spec.get('type')
    if types:
        checks = {'object': isinstance(value, dict), 'array': isinstance(value, (list, tuple)),
                  'string': isinstance(value, str), 'boolean': type(value) is bool,
                  'integer': type(value) is int, 'number': type(value) in (int, float), 'null': value is None}
        if not any(checks.get(t, False) for t in ([types] if isinstance(types, str) else types)): fail('Unexpected value type')
    if 'const' in spec and value != spec['const']: fail('Unexpected constant')
    if 'enum' in spec and value not in spec['enum']: fail('Value outside enum')
    if isinstance(value, dict):
        missing = set(spec.get('required', [])) - value.keys()
        if missing: fail('Missing fields: ' + ', '.join(sorted(missing)))
        fields = spec.get('properties', {})
        if spec.get('additionalProperties') is False and value.keys() - fields.keys(): fail('Unknown fields: ' + ', '.join(sorted(value.keys() - fields.keys())))
        for key, child in value.items(): validate(child, fields.get(key, {}), path + '.' + key)
        for key, compare in (('minProperties', lambda n: len(value) < n), ('maxProperties', lambda n: len(value) > n)):
            if key in spec and compare(spec[key]): fail(key)
    if isinstance(value, (list, tuple)):
        if len(value) < spec.get('minItems', 0) or len(value) > spec.get('maxItems', float('inf')): fail('Array size outside bounds')
        if spec.get('uniqueItems') and len({canonical_json(v) for v in value}) != len(value): fail('Array members must be unique')
        if isinstance(spec.get('items'), dict):
            for index, child in enumerate(value): validate(child, spec['items'], path + '[%s]' % index)
    if isinstance(value, str):
        import re
        if len(value) < spec.get('minLength', 0) or len(value) > spec.get('maxLength', float('inf')): fail('String length outside bounds')
        if 'pattern' in spec and not re.search(spec['pattern'], value): fail('String does not match pattern')
    if type(value) in (int, float):
        if value < spec.get('minimum', -float('inf')) or value > spec.get('maximum', float('inf')): fail('Number outside bounds')
        if 'exclusiveMinimum' in spec and value <= spec['exclusiveMinimum']: fail('Number below exclusiveMinimum')
        if 'exclusiveMaximum' in spec and value >= spec['exclusiveMaximum']: fail('Number above exclusiveMaximum')
    return value
