"""Schema-driven native batches extend the modeling plan's existing guards."""
from copy import deepcopy
from .errors import ModelingError
from .plan import Plan
from . import registry


class NativePlan(Plan):
    """Explicit native operations with mandatory reviewed writable scope.

    Modeling constructors remain preferable for shapes and transformations.
    This escape hatch covers all published native kinds without reflection.
    Part IDs are native IDs; new temporary IDs remain local to the batch.
    """
    def __init__(self, session, operations, *, writable, variables=(), material_ids=()):
        if writable is None:
            raise ModelingError('scope_required', 'List the reviewed writable parts explicitly; [] allows creation only.')
        super().__init__(session, writable=writable, variables=variables)
        operations = deepcopy(operations)
        if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
            raise ModelingError('invalid_input', 'A native plan contains 1..100 operations.')
        for operation in operations:
            if not isinstance(operation, dict): raise ModelingError('invalid_input', 'Operation must be an object.')
            registry.validate(operation, registry.schema(operation.get('kind'), operation=True))
        self.operations = operations
        self.material_ids = tuple(material_ids)
        if any(type(i) is not int or i < 0 for i in self.material_ids): raise ModelingError('invalid_input', 'material_ids must list nonnegative palette IDs.')
        session._writes(self.to_dict())  # Fail outside scope before preview I/O.

    def to_dict(self):
        value = super().to_dict()
        value['writableMaterialIds'] = sorted(self.material_ids)
        return value


class NativeScope:
    def __init__(self, session, parts, *, boundary=(), owner_id):
        self.session = session
        self.parts = tuple(parts)
        self.part_ids = [session._resolve_ref(p) for p in self.parts]
        args = {
            'craftSessionId': session.identity['craftSessionId'], 'expectedRevision': session.identity['revision'],
            'partIds': self.part_ids, 'ownerId': owner_id}
        boundary_ids = [session._resolve_ref(p) for p in boundary]
        if boundary_ids: args['boundaryPartIds'] = boundary_ids
        registry.validate(args, registry.schema('scope.capture'))
        self.result = session._native_command('scope.capture', args)
        self.scope_id = self.result['scopeId']
        self._epoch = session.identity['craftSessionId']
        self._executions = {}
        self._reviews = {}
        from .runtime import Runtime
        self._runtime = Runtime(client=session.client, journal_dir=session.journal.directory / 'scopes' / self.scope_id)

    def inspect(self):
        return self.session.client.call('scope.get', {'scopeId': self.scope_id, 'craftSessionId': self._epoch})

    def preview(self, operations):
        self.inspect()  # Check scope/epoch existence without recapturing its content.
        scene = self.session.inspect()
        if self.session.identity['craftSessionId'] != self._epoch: raise ModelingError('session_conflict', 'Scope belongs to another craft epoch.')
        plan = NativePlan(self.session, operations, writable=[scene.part(id=i) for i in self.part_ids])
        from . import registry
        registry.validate({'craftSessionId': self._epoch, 'scopeId': self.scope_id, 'operations': operations}, registry.schema('scoped.batch.apply'))
        preview = plan.preview()
        self._reviews[preview.token] = deepcopy(operations)
        return preview

    def apply(self, operations, *, preview_token, chunk_size=1, wait=True):
        if preview_token in self._executions:
            if self._reviews.get(preview_token) != operations: raise ModelingError('preview_mismatch', 'Token belongs to different operations.')
            result = self._runtime.resume(self._executions[preview_token], wait=wait)
            return self._deliver(result, self._executions[preview_token]) if wait else result
        if self._reviews.get(preview_token) != operations:
            raise ModelingError('preview_mismatch', 'Review scope.preview(operations), then supply its token unchanged.')
        pending = self.session.journal.pending(self.session.client.instance['instanceId'], self._epoch)
        if pending: raise ModelingError('pending_execution', 'Reconcile earlier Session executions before scoped edits.', {'journals': pending})
        args = {'craftSessionId': self._epoch, 'scopeId': self.scope_id, 'operations': deepcopy(operations), 'chunkSize': chunk_size}
        from .registry import validate, schema
        validate(args, schema('scoped.batch.apply'))
        before = self.session.inspect().to_dict()
        from .project import evidence
        proof = ({str(row['id']): evidence(row, before) for row in self.session._snapshot['parts'] if row['id'] in self.part_ids}
                 if self.session.project is not None else {})
        result = self._runtime._execute('scoped.batch.apply', args, wait=wait, kind='scoped',
            evidence={'scopeId': self.scope_id, 'previewToken': preview_token, 'operations': operations,
                      'baselineIdentity': self.session.identity, 'scopedBeforeEvidence': proof,
                      'writablePartIds': self.part_ids, 'scopedCraftFrame': self.session._snapshot['craftFrame'],
                      'projectPath': str(self.session.project.path) if self.session.project is not None else None},
            prepared=lambda path: self._executions.__setitem__(preview_token, path))
        return self._deliver(result, self._executions[preview_token]) if wait else result

    def _deliver(self, result, path):
        from .journal import Journal
        record = Journal.read(path, schema='sp2model.runtime/1')
        return deliver_scoped(self.session, result, record)

    def release(self):
        return self._runtime._execute('scope.release', {'scopeId': self.scope_id, 'craftSessionId': self._epoch}, kind='scoped')


def deliver_scoped(session, result, record):
    """Consume original scoped evidence without absorbing concurrent edits."""
    from .session import _same
    snapshot = session.client.call('craft.snapshot')
    if _same(result.get('identity', {}), snapshot['identity']):
        project = session.project
        proof = record.get('review', {})
        if proof.get('scopeId') != record['args'].get('scopeId'):
            raise ModelingError('invalid_journal', 'Scoped review and original native request differ.')
        if project is not None and proof.get('projectPath') == str(project.path):
            project.after_execution(snapshot, session.client.instance['instanceId'], proof['baselineIdentity'], result,
                {**proof, 'scoped': True, 'objects': {}, 'groups': {}, 'semanticShapes': {}})
        session._snapshot = snapshot
        return {**result, 'bindingDelivery': 'current_native_scoped_readback; concurrent changed objects are not rebound'}
    session.inspect()
    return {**result, 'bindingDelivery': 'historical_result; current state changed, no bindings advanced'}
