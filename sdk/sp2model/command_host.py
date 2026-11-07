"""Thin public command interface to Runtime and reviewed native SDK plans.

Parsing and execution are owned here, not delegated to an old CLI main.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from .errors import ModelingError
from .runtime import Runtime
from . import registry
from .transport import canonical_json


def _parse(argv):
    words, options = [], {}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg.startswith('--') or arg == '-h':
            key = 'help' if arg == '-h' else arg[2:]
            if key in options: raise ModelingError('invalid_input', 'Duplicate option --' + key)
            if key in ('help', 'json', 'async', 'live'):
                options[key] = True
            else:
                index += 1
                if index == len(argv) or argv[index].startswith('--'): raise ModelingError('invalid_input', 'Missing value for --' + key)
                options[key] = argv[index]
        else: words.append(arg)
        index += 1
    return '.'.join(words), options


def _arguments(command, options):
    if 'input' in options:
        try:
            raw = sys.stdin.read() if options['input'] == '-' else Path(options['input']).read_text(encoding='utf-8-sig')
            args = json.loads(raw)
        except (OSError, ValueError) as error: raise ModelingError('invalid_input', 'Cannot read input JSON: ' + str(error)) from error
        if not isinstance(args, dict): raise ModelingError('invalid_input', 'Input must be a JSON object.')
    else: args = {}
    if command.startswith('updates.') and options.get('live'):
        if 'live' in args: raise ModelingError('invalid_input', 'Do not duplicate live in flags and input.')
        args['live'] = True
    fields = registry.schema(command).get('properties', {}) if command in registry._CATALOG['commands'] else {}
    host_options = {'input', 'output', 'output-dir', 'instance', 'craft', 'discovery-dir', 'journal-dir', 'timeout', 'async', 'json', 'help', 'review', 'live', 'request-id'}
    for key, value in options.items():
        if key in host_options: continue
        camel = key.split('-')[0] + ''.join(word.title() for word in key.split('-')[1:])
        if camel not in fields: raise ModelingError('invalid_input', 'Unknown option --' + key, {'command': command})
        if camel in args: raise ModelingError('invalid_input', 'Do not duplicate input fields with flags: ' + camel)
        types = fields[camel].get('type')
        if types == 'string' or types is None and 'enum' in fields[camel]: args[camel] = value
        else:
            try: args[camel] = json.loads(value)
            except ValueError: raise ModelingError('invalid_input', 'Flag --' + key + ' needs a JSON value.') from None
    return args


def _batch(runtime, command, args, options):
    from .session import Preview, _digest
    from .native import NativePlan
    args = deepcopy(args)
    key = args.pop('requestId', None)
    if key or options.get('request-id'):
        raise ModelingError('invalid_input', 'Native plans own durable request identities. Resume their returned journals instead of injecting another request ID.')
    kind = registry.ALIASES.get(command)
    if kind:
        operation = args.pop('operation', None)
        if not isinstance(operation, dict): raise ModelingError('invalid_input', 'Shortcut requires operation object.')
        args['operations'] = [{**operation, 'kind': kind}]
        command = 'batch.apply'
    if args.keys() - {'craftSessionId', 'expectedRevision', 'operations', 'modelScope'}:
        raise ModelingError('invalid_input', 'Unexpected batch fields.', {'fields': sorted(args.keys() - {'craftSessionId', 'expectedRevision', 'operations', 'modelScope'})})
    model_scope_spec = deepcopy(registry.schema('batch.apply')['properties']['modelScope'])
    # CLI supplies the SDK version stamp; authorization still must be explicit.
    model_scope_spec['required'] = ['writablePartIds']
    model_scope_spec['properties']['writableMaterialIds'] = {'type': 'array', 'uniqueItems': True, 'items': {'type': 'integer', 'minimum': 0}, 'maxItems': 50}
    registry.validate(args.get('modelScope'), model_scope_spec)
    review, marker = None, None
    if command == 'batch.apply' and options.get('review'):
        review = json.loads(Path(options['review']).read_text(encoding='utf-8-sig'))
        expected_hash = review.pop('reviewHash', None)
        if expected_hash != _digest(review) or review.get('schemaVersion') != 'sp2model.review/1': raise ModelingError('invalid_review', 'Review content was changed.')
        original = review['plan']
        if (review['instance']['instanceId'] != runtime.client.instance['instanceId'] or
            original['operations'] != args.get('operations') or original['baselineIdentity']['craftSessionId'] != args.get('craftSessionId') or
            original['baselineIdentity']['revision'] != args.get('expectedRevision') or
            original['writablePartIds'] != sorted(args.get('modelScope', {}).get('writablePartIds', [])) or
            original.get('variableNames', []) != sorted(args.get('modelScope', {}).get('variableNames', [])) or
            original.get('writableMaterialIds', []) != sorted(args.get('modelScope', {}).get('writableMaterialIds', []))):
            raise ModelingError('preview_mismatch', 'Review differs from the requested plan, scope, instance or baseline.')
        marker = runtime.journal.directory / 'reviews' / (expected_hash + '.json')
        if marker.exists():
            saved = json.loads(marker.read_text(encoding='utf-8'))
            session = runtime.session(options.get('craft') or args.get('craftSessionId'))
            receipt = session.resume(saved['journalPath'])
            return receipt.to_dict() if hasattr(receipt, 'to_dict') else receipt
    model_scope = args.get('modelScope', {})
    if not isinstance(model_scope.get('writablePartIds'), list):
        raise ModelingError('scope_required', 'Input modelScope.writablePartIds must list explicit reviewed IDs; [] permits creation only.')
    session = runtime.session(options.get('craft') or args.get('craftSessionId'))
    if args.get('craftSessionId') != session.identity['craftSessionId'] or args.get('expectedRevision') != session.identity['revision']:
        raise ModelingError('revision_conflict', 'Input baseline differs from the current native craft.')
    scene = session.inspect()
    parts = [scene.part(id=i) for i in model_scope['writablePartIds']]
    plan = NativePlan(session, args.get('operations'), writable=parts, variables=model_scope.get('variableNames', []), material_ids=model_scope.get('writableMaterialIds', []))
    if command == 'batch.preview':
        preview = plan.preview()
        review = {'schemaVersion': 'sp2model.review/1', 'instance': runtime.client.instance,
                  'plan': plan.to_dict(), 'planHash': _digest(plan.to_dict()), 'preview': {'token': preview.token, 'report': preview.report}}
        review['reviewHash'] = _digest(review)
        return review
    if not options.get('review'): raise ModelingError('review_required', 'Review batch preview output, then supply --review FILE with identical input.')
    if review['instance']['instanceId'] != runtime.client.instance['instanceId'] or review.get('planHash') != _digest(plan.to_dict()): raise ModelingError('preview_mismatch', 'Review belongs to another plan, instance or baseline.')
    token = review['preview']['token']
    session._previews[token] = Preview(token, review['planHash'], tuple(model_scope['writablePartIds']), review['preview']['report'])
    # Persist token -> execution before POST, and recover that same request on
    # subsequent invocations instead of replaying relative operations.
    from .journal import Journal
    marker.parent.mkdir(parents=True, exist_ok=True)
    session._on_execution_prepared = lambda path: Journal(marker.parent).create({'requestId': expected_hash, 'reviewHash': expected_hash, 'journalPath': str(path)})
    receipt = plan.apply(token)
    return receipt.to_dict() if hasattr(receipt, 'to_dict') else receipt


def execute(argv, *, runtime_factory=Runtime):
    command, options = None, {}
    runtime = None
    try:
        command, options = _parse(argv)
        if options.get('help') or not command:
            names = registry.commands()
            result = {'usage': 'sp2model run SCRIPT --instance ID --craft NAME | sp2model GROUP COMMAND [--input JSON] [--instance ID]',
                      'commands': [row for row in names if not command or row['name'] == command or row['name'].startswith(command + '.')],
                      'management': 'Runtime/commands outside run/inspect/resume do not require --craft in MainMenu or offline.',
                      'writes': 'Use Python Plan/NativePlan.preview/apply or batch preview --output REVIEW then batch apply --review REVIEW. Native scene control requires current guards.',
                      'python': 'from sp2model import Runtime; runtime=Runtime(instance=...); runtime.control(...); session=runtime.session(CRAFT)',
                      'additional': ['doctor [--live]', 'history inspect --path FILE', 'history reconcile --path FILE', 'runtime resume --journal FILE']}
            if command in registry._CATALOG['commands']: result['contract'] = registry.contract(command)
        else:
            runtime = runtime_factory(instance=options.get('instance'), discovery_dir=options.get('discovery-dir'),
                                      journal_dir=options.get('journal-dir'), timeout=float(options.get('timeout', 30)))
            if command.startswith('history.'):
                if set(options) - {'path', 'instance', 'discovery-dir', 'journal-dir', 'timeout', 'output', 'json'}: raise ModelingError('invalid_input', 'Unknown history option')
                result = runtime.history(options['path'], reconcile=command == 'history.reconcile')
            elif command == 'runtime.resume': result = runtime.resume(options['journal'])
            elif command == 'doctor': result = runtime.doctor(live=bool(options.get('live')))
            else:
                args = _arguments(command, options)
                if command in registry.ALIASES or command in ('batch.apply', 'batch.preview'):
                    result = _batch(runtime, command, args, options)
                elif command == 'designer.control':
                    request = args.pop('requestId', None) or options.get('request-id')
                    if not request: raise ModelingError('request_id_required', 'Native control requires the retained requestId and explicit scene/craft guards from designer status.')
                    registry.validate({**args, 'requestId': request}, registry.schema(command))
                    result = runtime._execute(command, args, request, kind='control', wait=not options.get('async'))
                else:
                    session = runtime.session(options['craft']) if options.get('craft') else None
                    if options.get('async'):
                        from .transport import READ_COMMANDS
                        if command not in READ_COMMANDS: raise ModelingError('invalid_input', '--async is supported for native reads/control; native edits use durable plan journals.')
                        registry.validate(args, registry.schema(command))
                        result = runtime._execute(command, args, options.get('request-id'), wait=False)
                    else: result = runtime.call(command, args, session=session)
                if options.get('output-dir'): result = runtime.artifacts(result, options['output-dir'])
        envelope = {'schemaVersion': 'sp2model.host/1', 'ok': True, 'action': command, 'result': result,
                    'transport': runtime.statistics if runtime else {'commandPostAttempts': 0}}
        from ._services.build_guidance import decorate
        hint = decorate(command or '', {'success': True, 'data': result})
        if hint.get('guidance'): envelope['guidance'] = hint['guidance']
        canonical_json(envelope)
        if options.get('output'):
            path = Path(options['output']).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(canonical_json(result))
            envelope['result'] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        from .updates import decorate as update_notices
        return 0, update_notices(envelope, getattr(runtime, '_client', None))
    except Exception as error:
        if not isinstance(error, ModelingError): error = ModelingError('host_error', str(error), {'type': type(error).__name__})
        envelope = {'schemaVersion': 'sp2model.host/1', 'ok': False, 'action': command, 'error': error.to_dict(),
                   'transport': runtime.statistics if runtime else {'commandPostAttempts': 0},
                   'recovery': 'No write automatically replayed. Query the original request or its durable journal.'}
        from ._services.build_guidance import decorate
        hint = decorate(command or '', {'success': False, 'error': error.to_dict()})
        if hint.get('guidance'): envelope['guidance'] = hint['guidance']
        from .updates import decorate as update_notices
        return 1, update_notices(envelope, getattr(runtime, '_client', None))
