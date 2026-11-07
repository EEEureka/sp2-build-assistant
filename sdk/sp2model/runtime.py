"""Public administration, query, reference, async and historical services.

No craft is necessary for offline commands or MainMenu management. Native
editing still belongs to a guarded Session/Plan, never a renamed CLI process.
"""
from copy import deepcopy
import hashlib
import json
import os
import re
from pathlib import Path
import uuid
from .errors import ModelingError
from .journal import Journal
from .transport import BridgeClient, READ_COMMANDS, canonical_json
from . import registry


def _hash(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


class Runtime:
    def __init__(self, instance=None, *, discovery_dir=None, journal_dir=None, timeout=30, client=None):
        self._selector, self._discovery_dir, self.timeout = instance, discovery_dir, timeout
        self._client = client
        root = Path(os.environ.get('SP2MODEL_HOME') or Path.home() / '.sp2build')
        self._journal_directory = journal_dir or root / 'runtime-journals'
        self._journal = None
        self._knowledge = None
        self._updates = None

    @property
    def journal(self):
        # Offline information queries must not create a global journal folder.
        if self._journal is None:
            self._journal = Journal(self._journal_directory)
        return self._journal

    @journal.setter
    def journal(self, value):
        # Preserve the original injectable public journal attribute.
        self._journal = value

    @property
    def knowledge(self):
        """Versioned offline knowledge; only explicit refresh connects live."""
        if self._knowledge is None:
            from .knowledge import Knowledge
            self._knowledge = Knowledge(self)
        return self._knowledge

    @property
    def updates(self):
        """Release notices; offline status/guide never discover a game."""
        if self._updates is None:
            from .updates import Updates
            self._updates = Updates(self)
        return self._updates

    @property
    def client(self):
        if self._client is None:
            try:
                self.updates.schedule()
            except Exception:
                pass  # optional update checks cannot block a native operation
            self._client = BridgeClient.discover(self._selector, self._discovery_dir, self.timeout)
        return self._client

    @property
    def statistics(self):
        return self._client.statistics if self._client is not None else {'commandPostAttempts': 0, 'commands': {}}

    @staticmethod
    def instances(discovery_dir=None):
        directory = Path(discovery_dir) if discovery_dir else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'SP2BuildAssistant/instances'
        rows = {}
        for path in sorted(directory.glob('*.json')):
            try:
                if path.stat().st_size > 65536: continue
                raw = json.loads(path.read_text(encoding='utf-8-sig'))
                client = BridgeClient.discover(raw['instanceId'], directory, timeout=1)
                rows[client.instance['instanceId']] = client.instance
            except (ModelingError, OSError, ValueError, KeyError): continue
        return list(rows.values())

    def session(self, craft, *, project_path=None, summary_only=False):
        from .session import Session
        return Session(self.client, craft=craft, journal_dir=self.journal.directory / 'sessions', project_path=project_path, summary_only=summary_only)

    def status(self):
        status = self.client.call('designer.status')
        if status.get('identity') and not (status.get('craftName') or status.get('name')):
            current = self.client.call('craft.status')
            from .session import _same
            if not _same(current.get('identity', {}), status['identity']):
                raise ModelingError('revision_conflict', 'Craft changed while reading scene and name; inspect again before control.')
            status['craftName'] = current['name']
        return status

    def control(self, action, *, expected_craft=None, **options):
        """Native enter/new/load/save/select/delete/menu/quit with fresh guards.

        On Designer/Terrain require the intended current craft explicitly;
        replacement/quit additionally require discardCurrent=True. Deletion
        requires the saved name and modified time discovered from crafts.
        """
        status = self.status()
        ident = status.get('identity')
        if ident:
            if expected_craft is None or expected_craft not in (status.get('craftName'), status.get('name'), ident.get('craftSessionId')):
                raise ModelingError('craft_mismatch', 'Specify expected_craft before a control action on an open craft.')
        args = {'action': action, 'expectedScene': status['scene'], **options}
        if ident:
            args.update(craftSessionId=ident['craftSessionId'], expectedRevision=ident['revision'],
                        expectedCraftName=status.get('craftName', status.get('name')))
        request = uuid.uuid4().hex
        registry.validate({**args, 'requestId': request}, registry.schema('designer.control'))
        return self._execute('designer.control', args, request, kind='control')

    def _execute(self, command, args, request_id=None, *, kind='native', wait=True, evidence=None, prepared=None):
        request_id = request_id or uuid.uuid4().hex
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request_id):
            raise ModelingError('invalid_input', 'Durable request_id must be a simple 1..128 character identifier.')
        path = self.journal.directory / (request_id + '.json')
        if path.exists():
            existing = Journal.read(path, schema='sp2model.runtime/1')
            if existing.get('command') != command or existing.get('payloadHash') != _hash(args):
                raise ModelingError('request_id_conflict', 'Saved request belongs to different arguments.')
            return self.resume(path, wait=wait)
        if command not in READ_COMMANDS:
            pending = []
            for existing_path in self.journal.directory.glob('*.json'):
                existing = json.loads(existing_path.read_text(encoding='utf-8'))
                if existing.get('schemaVersion') != 'sp2model.runtime/1': continue
                if existing['instance']['instanceId'] == self.client.instance['instanceId'] and existing['state'] in ('prepared', 'submitted', 'outcome_unknown'):
                    pending.append(str(existing_path))
            if pending: raise ModelingError('pending_execution', 'Reconcile earlier native requests before another write.', {'journals': pending})
            if args.get('craftSessionId'):
                pending = self.journal.pending(self.client.instance['instanceId'], args['craftSessionId'])
                if pending: raise ModelingError('pending_execution', 'Reconcile nested Session/scoped executions before native control.', {'journals': pending})
        record = {'schemaVersion': 'sp2model.runtime/1', 'kind': kind, 'command': command, 'args': deepcopy(args),
                  'payloadHash': _hash(args), 'requestId': request_id, 'operationId': None,
                  'instance': self.client.instance, 'state': 'prepared'}
        if evidence is not None: record['review'] = deepcopy(evidence)
        path = self.journal.create(record)  # fsync BEFORE POST
        if prepared is not None: prepared(str(path))
        try:
            record.update(operationId=self.client.submit(command, args, request_id=request_id), state='submitted')
            Journal.update(path, record)
            if not wait: return {**deepcopy(record), 'journalPath': str(path)}
            return self.resume(path)
        except ModelingError as error:
            if record['state'] != 'succeeded':
                record.update(state='outcome_unknown' if error.details.get('outcome') == 'unknown' else 'failed', error=error.to_dict())
                Journal.update(path, record)
            error.details['journalPath'] = str(path)
            raise

    def resume(self, path, *, wait=True):
        record = Journal.read(path, schema='sp2model.runtime/1')
        if record['instance']['instanceId'] != self.client.instance['instanceId']:
            raise ModelingError('instance_mismatch', 'Query this original request on its original instance.', {'original': record['instance']})
        if record.get('payloadHash') != _hash(record.get('args')):
            raise ModelingError('invalid_journal', 'Saved arguments were changed; preserve the original journal.')
        if record['state'] == 'succeeded': return {**deepcopy(record['result']), 'journalPath': str(Path(path).resolve())}
        if not record.get('operationId'):
            record['operationId'] = self.client.lookup_request(record['requestId'])['operationId']
            Journal.update(path, record)
        if not wait: return {**self.client.status(record['operationId']), 'journalPath': str(Path(path).resolve())}
        try: result = self.client.wait(record['operationId'])
        except ModelingError as error:
            record.update(state='outcome_unknown' if error.details.get('outcome') == 'unknown' else 'failed', error=error.to_dict())
            Journal.update(path, record)
            error.details['journalPath'] = str(path)
            raise
        record.update(state='succeeded', result=result)
        Journal.update(path, record)
        return {**deepcopy(result), 'journalPath': str(Path(path).resolve())}

    def operation(self, operation_id, *, action='status', timeout=None):
        if action == 'status': return self.client.status(operation_id)
        if action in ('wait', 'result'): return self.client.wait(operation_id, timeout=timeout)
        if action == 'cancel':
            record = {'schemaVersion': 'sp2model.cancel/1', 'requestId': uuid.uuid4().hex,
                      'instance': self.client.instance, 'operationId': operation_id, 'state': 'prepared'}
            path = self.journal.create(record)
            try:
                result = self.client.cancel(operation_id)
                record.update(state='requested', result=result)
            except ModelingError as error:
                record.update(state='outcome_unknown', error=error.to_dict())
                Journal.update(path, record)
                error.details['journalPath'] = str(path)
                raise
            Journal.update(path, record)
            return {**result, 'journalPath': str(path)}
        raise ModelingError('invalid_input', 'action must be status/wait/result/cancel')

    def history(self, path, *, reconcile=False):
        """Read old append-only journals and projects without rewriting originals."""
        from ._services import run_journal
        target = Path(path).expanduser().resolve()
        try:
            text = target.read_text(encoding='utf-8-sig')
            try: document = json.loads(text)
            except ValueError: document = None
            if isinstance(document, dict):
                kind = document.get('kind') or document.get('schemaVersion')
                return {'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                        'kind': kind, 'document': document, 'modified': False,
                        'continuation': 'Use session.resume/runtime.resume for execution journals; reference.inspect/build.loop.status for supported projects. Unknown formats are read-only.'}
            result = run_journal.status(target)
            if reconcile:
                for row in result['pendingWrites']:
                    row['originalStatus'] = (self.client.status(row['operationId']) if row.get('operationId')
                                             else self.client.lookup_request(row['requestId']))
            return {**result, 'modified': False, 'replayed': False}
        except (OSError, ValueError) as error:
            raise ModelingError(getattr(error, 'code', 'history_unreadable'), str(error), {'path': str(target), 'originalPreserved': True}) from error

    def artifacts(self, result, directory):
        """Download authenticated immutable artifacts with hash/size checks."""
        from .artifacts import download
        return download(self.client, result, directory)

    def call(self, command, arguments=None, *, session=None, request_id=None, wait=True, native_scope=None):
        """Public schema-driven services. Batch writes need preview/apply.

        Native reads may run without a Session. Reference/structure live services
        require an explicitly selected Session; their guarded orchestration is
        retained and every native write gets a separate durable runtime journal.
        """
        from .knowledge import COMMANDS as KNOWLEDGE_COMMANDS
        if command in KNOWLEDGE_COMMANDS:
            return self.knowledge.call(command, arguments)
        from .updates import COMMANDS as UPDATE_COMMANDS
        if command in UPDATE_COMMANDS:
            return self.updates.call(command, arguments)
        args = deepcopy(arguments or {})
        if command == 'version':
            registry.validate(args, registry.schema(command))
            from . import __version__
            import sys
            return {'version': __version__, 'python': sys.version.split()[0], 'contract': 'sp2model/1'}
        if command == 'commands.list':
            registry.validate(args, registry.schema(command))
            return {'commands': registry.commands(), 'operationKinds': sorted(registry._CATALOG['operations'])}
        if command == 'commands.schema':
            registry.validate(args, registry.schema(command))
            operation = args.get('operation')
            return registry.contract(operation or args.get('command'), operation=bool(operation))
        if command == 'instances.list':
            registry.validate(args, registry.schema(command))
            return {'instances': self.instances(self._discovery_dir)}
        if command == 'skill.path':
            registry.validate(args, registry.schema(command))
            return {'path': str(registry.RESOURCES / 'skill')}
        if command.startswith('knowledge.') and command != 'knowledge.capabilityaudit':
            registry.validate(args, registry.schema(command))
            name = {'knowledge.catalog': 'catalog', 'knowledge.funky': 'funky', 'knowledge.complex': 'complex-parts'}.get(command)
            if not name: raise ModelingError('unsupported_command', command)
            data = json.loads((registry.RESOURCES / 'knowledge' / (name + '.json')).read_text(encoding='utf-8-sig'))
            if args.get('family'):
                data['families'] = [f for f in data['families'] if f['id'] == args['family']]
                if not data['families']: raise ModelingError('invalid_input', 'Unknown complex part family')
            return {'dataSource': 'versioned_offline_knowledge', 'knowledge': data,
                    'legacy': {'scope': 'Legacy curated overview; not the 0.7.7 complete collection index.',
                               'collectionIndex': 'knowledge.status', 'search': 'knowledge.search',
                               'detail': 'knowledge.get', 'export': 'knowledge.export'}}
        row = registry.contract(command)
        if row['execution'] == 'testOnly': raise ModelingError('test_only', 'Not available in the production public tool.')
        if command.startswith('operation.'):
            registry.validate(args, row['inputSchema'])
            return self.operation(args['id'], action=command.split('.')[1])
        if command in registry.ALIASES or command in ('batch.apply', 'batch.preview'):
            raise ModelingError('review_required', 'Use session.native_plan(operations, writable=...).preview()/apply(token), or CLI --review workflow.')
        registry.validate(args, row['inputSchema'])
        from ._services import reference_cli
        if command in reference_cli.COMMANDS:
            if command in {'structure.replace', 'structure.reconcile', 'structure.restore', 'fit.apply', 'structure.reshape'} and session is None:
                raise ModelingError('session_required', 'This service needs an explicitly selected native Session.')
            def live(name, body):
                body = deepcopy(body)
                key = body.pop('requestId', None)
                if name.startswith('operation.'):
                    return {'success': True, 'data': self.operation(body['id'], action=name.split('.')[1])}
                if name in READ_COMMANDS: data = self.client.call(name, body)
                else:
                    if session is None: raise ModelingError('session_required', 'Native orchestration writes need an explicitly selected Session.')
                    pending = session.journal.pending(self.client.instance['instanceId'], session.identity['craftSessionId'])
                    if pending: raise ModelingError('pending_execution', 'Reconcile original Session/service requests before orchestration writes.', {'journals': pending})
                    if not key: raise ModelingError('request_id_required', 'Orchestrated writes must retain their original request ID.')
                    baseline = session.identity
                    if body.get('craftSessionId') != baseline['craftSessionId']:
                        raise ModelingError('craft_mismatch', 'Orchestration targets another craft epoch.')
                    review = None
                    if name == 'batch.apply':
                        from .session import Session
                        declared = deepcopy(native_scope) if native_scope is not None else {
                            'version': 'sp2model.scope/1', 'writablePartIds': Session._writes({
                                'operations': body['operations'], 'writablePartIds': None}), 'variableNames': [],
                            'paletteAppend': any(op.get('kind') == 'appearance.set' and op.get('mode') == 'clone' for op in body['operations'])}
                        if not isinstance(declared, dict) or declared.get('version') != 'sp2model.scope/1':
                            raise ModelingError('invalid_input', 'native_scope must be an explicit sp2model.scope/1 document.')
                        body['modelScope'] = declared
                        review = self.client.call('batch.preview', body)
                    data = self._execute(name, body, key, kind='orchestration', evidence=review)
                if 'artifactBase' in data:
                    data = self.artifacts(data, args.get('outputDir') or self.journal.directory / 'artifacts')
                return {'success': True, 'schemaVersion': '1', 'data': data}
            try:
                result = reference_cli.dispatch(command, args, live)
                if isinstance(result, dict) and result.get('success') is False:
                    err = result['error']; raise ModelingError(err.get('code', 'service_failed'), err.get('message', 'Service failed'), err.get('details'))
                if session is not None and command in reference_cli.LIVE: session.inspect()
                return result.get('data', result) if isinstance(result, dict) and result.get('success') is True else result
            except ModelingError: raise
            except (ValueError, OSError, KeyError, TypeError) as error:
                raise ModelingError(getattr(error, 'code', 'invalid_input'), str(error), getattr(error, 'details', {})) from error
        if command in READ_COMMANDS:
            if not wait or request_id is not None: return self._execute(command, args, request_id, wait=wait)
            if command == 'designer.status': return self.status()
            return self.client.call(command, args)
        raise ModelingError('review_required', 'Native control/recovery/scope mutations need their dedicated reviewed public methods.', {'command': command})

    def doctor(self, *, live=False):
        from ._services.dependencies import doctor
        from . import __version__
        result = {'sdkVersion': __version__, 'contract': 'sp2model/1', 'worker': doctor(),
                  'offline': not live, 'downloadsAttempted': False,
                  'resourceRoot': str(registry.RESOURCES), 'oldCliFallback': False}
        if live:
            result['loaded'] = self.client.call('capabilities')
            result['instance'] = self.client.instance
            advertised = result['loaded'].get('modelingSdk', {})
            result['compatibility'] = {'status': 'matched' if advertised.get('version') == __version__ and advertised.get('contract') == 'sp2model/1' else 'mismatch',
                                       'sdkVersion': __version__, 'loadedSdkVersion': advertised.get('version'),
                                       'meaning': 'Compare actual loaded DLL after restart; installing Python or copying a DLL does not reload the game.'}
        return result
