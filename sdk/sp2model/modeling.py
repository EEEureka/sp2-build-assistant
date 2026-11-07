"""Short semantic operations backed by the public Session/ModelingTask state.

No script evaluation, automatic guessing of reference identity, or native replay.
Constructors persist an immutable review; applying that review has one intent ID.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

from .errors import ModelingError
from .geometry import Frame
from .journal import Journal
from .transport import canonical_json
from .reference_registry import ReferenceRegistry
from .model_geometry import compile_loft, compile_prism, compile_recess, GeometryCompilation, refine_loft
from .model_compare import reference_targets, validate_coverage, render_overlay, render_overlay_png
from .project import same_identity


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


class ModelingWorkspace:
    def __init__(self, directory, session=None):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session = session
        if session is not None:
            from .project import Project
            project_path = self.directory / 'project.json'
            if session.project is None:
                session.project = Project(project_path)
                session.inspect()
            elif session.project.path.resolve() != project_path:
                raise ModelingError('workspace_project_mismatch',
                    'Use the workspace project.json when attaching this Session so SDK and structured commands share the same bindings.',
                    {'expectedProjectPath': str(project_path), 'actualProjectPath': str(session.project.path)})
        self.references = ReferenceRegistry(self.directory / 'references.json')
        self.task_path = self.directory / 'task.json'

    def task(self):
        if self.session is None:
            raise ModelingError('session_required', 'Attach the explicit game instance and currently loaded craft.')
        if not self.task_path.is_file():
            raise ModelingError('task_required', 'Use task.create with a reviewed reference before modeling.')
        return self.session.task(self.task_path)

    def reference(self, task):
        contract = task.data.get('semanticReference')
        if not contract:
            raise ModelingError('reference_required', 'Task has no frozen semantic reference.')
        current = self.references.require_ready(contract['referenceId'])
        if current['contentHash'] != contract['contentHash'] or current['version'] != contract['version']:
            raise ModelingError('reference_changed', 'Reference version changed. Start a reviewed new task instead of silently replacing its geometry.')
        return current

    def create(self, *, name, intent, reference_id, tolerance_m=.01, part_budget=100,
               max_iterations=12, max_native_operations=800):
        if self.session is None:
            raise ModelingError('session_required', 'Task creation captures the intended native instance.')
        if self.task_path.exists():
            raise ModelingError('task_exists', 'This workspace already has a task; use task.status or a new workspace.')
        reference = self.references.require_ready(reference_id)
        components = sorted({f['component'] for f in reference['features']})
        if not components:
            raise ModelingError('contract_incomplete', 'Reference needs explicit semantic features and component scopes.')
        contracts = {name: reference_targets(reference, tolerance_m=tolerance_m, component=name) for name in components}
        for component, targets in contracts.items():
            coverage = validate_coverage(reference, targets)
            if coverage['status'] != 'passed':
                raise ModelingError('contract_incomplete', 'Resolve reference coverage before native modeling.', {'component': component, 'coverage': coverage})
        source = self.directory / 'frozen-reference.json'
        Journal.update(source, reference)
        task = self.session.task(self.task_path, name=name, intent=intent, max_candidates=1,
                                 max_iterations=max_iterations, max_native_operations=max_native_operations)
        task.reference('source', kind='native', source=str(source), subject=reference_id,
                       uncertainties=reference.get('uncertainties', []))
        for component, targets in contracts.items():
            task.component(component, intent='Preserve declared reference features: ' + component,
                           strategy='reviewed semantic native construction')
            task.metric(component + '.geometry', component=component, kind='reference_geometry', reference_id='source',
                        expected={'reference': reference, 'targets': targets}, tolerance_m=tolerance_m)
        with task._edit():
            task.data['semanticReference'] = {key: reference[key] for key in ('referenceId', 'version', 'contentHash', 'frameId')}
        task.freeze()
        task.candidate('model', components=components, strategy='native semantic components', part_budget=part_budget)
        return task.report()

    def _frame(self, task):
        return Frame.custom(task.data.get('frameTranslationMetres', [0, 0, 0]))

    def _plan(self, task, operation, arguments):
        reference = self.reference(task)
        component = arguments['component']
        if component not in task.data['components']:
            raise ModelingError('component_not_found', 'Choose a component from the frozen task.', {'components': list(task.data['components'])})
        candidate = task.data['candidates']['model']
        existing = list(task.parts('model', component)) if candidate['bindings'].get(component) else []
        creation = operation in ('model.loft', 'model.prism', 'model.recess')
        if creation and existing and not arguments.get('replace', False):
            raise ModelingError('component_exists', 'Use model.patch/move/rotate/scale or explicitly review replace:true for this component.')
        if not creation and not existing:
            raise ModelingError('component_unbound', 'Build this component before editing it.')
        plan = self.session.plan(frame=self._frame(task), writable=existing)
        compilation = None
        bindings = None
        if creation:
            params = deepcopy(arguments['shape'])
            params['reference'] = reference
            builder = {'model.loft': compile_loft, 'model.prism': compile_prism, 'model.recess': compile_recess}[operation]
            compilation = builder(**params)
            for part in existing:
                plan.delete(part)
            compiled = compilation.append_to(plan)
            names = list(plan.objects)
            bindings = {component: names}
            retained = {p['id'] for c, values in candidate['bindings'].items() if c != component for p in values}
            if len(retained) + len(names) > candidate['partBudget']:
                raise ModelingError('modeling_budget', 'Whole candidate exceeds its frozen native part budget.')
        elif operation == 'model.move':
            plan.move(existing, arguments['translation'])
        elif operation == 'model.rotate':
            plan.rotate(existing, arguments['axis'], angle_deg=arguments['angle_deg'], pivot=arguments.get('pivot'))
        elif operation == 'model.scale':
            factors = arguments['factors']
            pivot = arguments['pivot']
            from .geometry import vector, number
            factors=vector(factors,'scale factors');pivot=vector(pivot,'shared pivot metres')
            for value in factors:number(value,'positive scale factor',.000001,1000000)
            if max(factors)-min(factors)>1e-10:
                raise ModelingError('unsupported_representation','Shared-frame nonuniform scaling of rotated components requires an explicit native fit. This helper currently accepts uniform factors only.')
            # Shared task-frame pivot, not independent scaling around each part.
            from .geometry import rotate, sub
            frame = self._frame(task)
            inverse = tuple(-v if i < 3 else v for i, v in enumerate(frame.rotation_quaternion))
            for part in existing:
                current = rotate(inverse, sub(part._pose['position'], frame.position))
                translation = [(current[i] - pivot[i]) * (factors[i] - 1) for i in range(3)]
                plan.move([part], translation)
            plan.scale(existing, factors)
        elif operation == 'model.patch':
            for part in existing:
                plan.shape(part, arguments['patch'])
        elif operation == 'model.refine':
            definition, parts = self.session.semantic(arguments['name'])
            if {p.id for p in parts} != {p.id for p in existing}:
                raise ModelingError('geometry_binding_mismatch', 'The named compiled shape must exactly match this task component.')
            previous = definition.get('compilation')
            if previous is None:
                raise ModelingError('unsupported_representation', 'Local station refinement requires a saved semantic loft compilation.')
            compilation = refine_loft(previous, arguments['station_updates'],
                                      protected_station_ids=arguments.get('protected_station_ids', ()))
            compilation.patch_existing(plan, parts, previous)
        else:
            raise ModelingError('unknown_operation', 'Unsupported semantic editing operation.')
        return plan, bindings, None if compilation is None else compilation.to_dict()

    def preview(self, operation, arguments):
        task = self.task()
        plan, bindings, compilation = self._plan(task, operation, arguments)
        preview = plan.preview()
        review = {'schemaVersion': 'sp2model.semantic-review/1', 'operation': operation,
                  'arguments': deepcopy(arguments), 'instanceId': self.session.client.instance['instanceId'],
                  'baselineIdentity': self.session.identity, 'taskId': task.data['taskId'],
                  'contractHash': task.data['contractHash'], 'planHash': digest(plan.to_dict()),
                  'reference': task.data['semanticReference'], 'autoBind': bindings,
                  'compilation': compilation, 'nativePreview': preview.report}
        correction = task.correction_review('model', arguments['component'])
        if correction is not None:
            review['correction'] = correction
        review_id = digest(review)
        path = self.directory / 'reviews' / (review_id + '.json')
        path.parent.mkdir(exist_ok=True)
        if not path.exists():
            Journal.update(path, {**review, 'reviewId': review_id})
        return {'reviewId': review_id, 'reviewPath': str(path), 'intentId': review_id,
                'baselineIdentity': review['baselineIdentity'], 'component': arguments['component'],
                'pieceCount': None if compilation is None else compilation['pieceCount'],
                'operations': len(plan.operations), 'compilation': compilation,
                'correction': correction,
                'nextAction': 'edit.apply', 'nativeWrites': 0, 'geometryStatus': 'not_assessed'}

    def apply(self, review_id):
        if not isinstance(review_id, str) or len(review_id) != 64 or any(c not in '0123456789abcdef' for c in review_id):
            raise ModelingError('invalid_review', 'Use the exact reviewId returned by the preview.')
        path = self.directory / 'reviews' / (review_id + '.json')
        if not path.is_file():
            raise ModelingError('review_not_found', 'Preview does not exist in this workspace.')
        review = json.loads(path.read_text(encoding='utf-8'))
        if review.pop('reviewId') != review_id or digest(review) != review_id:
            raise ModelingError('review_changed', 'Saved review was changed; generate a new review.')
        task = self.task()
        if review['taskId'] != task.data['taskId'] or review['contractHash'] != task.data['contractHash']:
            raise ModelingError('task_conflict', 'Review belongs to a different frozen task.')
        original = next((e for e in task.data['candidates']['model']['executions'] if e.get('intentId') == review_id), None)
        if original is not None:
            receipt = task.resume_edit(review_id)
            return {'replayed': False, 'resumed': True, 'receipt': receipt.to_dict(), 'task': task.report()}
        if review['instanceId'] != self.session.client.instance['instanceId'] or not same_identity(review['baselineIdentity'], self.session.identity):
            raise ModelingError('revision_conflict', 'Review baseline changed; inspect and create a new explicit review. This review was not submitted.')
        plan, bindings, compilation = self._plan(task, review['operation'], review['arguments'])
        if digest(plan.to_dict()) != review['planHash']:
            raise ModelingError('preview_mismatch', 'Reconstructed plan differs from the reviewed plan.')
        if task.correction_review('model', review['arguments']['component']) != review.get('correction'):
            raise ModelingError('preview_mismatch', 'Required correction stage changed. Inspect and review the current evidence before applying.')
        receipt = task.apply('model', plan, intent_id=review_id, bind=bindings,
                             hypothesis=review['arguments'].get('hypothesis'), correction=review.get('correction'))
        return {'replayed': False, 'resumed': False, 'receipt': receipt.to_dict(), 'task': task.report()}

    def compare(self, *, component=None):
        task = self.task()
        self.reference(task)
        ids = None if component is None else [component + '.geometry']
        checked = task.check('model', metric_ids=ids)
        overlays = {}
        for metric_id, report in checked['results'].items():
            if report.get('results'):
                destination = self.directory / 'evidence' / (digest(report)[:20] + '.svg')
                destination.parent.mkdir(exist_ok=True)
                overlays[metric_id] = {'svg': render_overlay(report, destination),
                                       'png': render_overlay_png(report, destination.with_suffix('.png'))}
        if task.report()['candidates']['model']['allRequiredPassed']:
            from .task import STAGES
            while task.data['stage'] != STAGES[-1]:
                task.advance('model', STAGES[STAGES.index(task.data['stage']) + 1])
        return {**checked, 'report': task.report(), 'overlays': overlays}

    def status(self):
        if self.session is not None and self.task_path.exists():
            task = self.task()
            return {**task.report(), 'reference': task.data.get('semanticReference'),
                    'executions': [{k: e.get(k) for k in ('intentId', 'state', 'nativeState', 'postprocessingState', 'journalPath', 'error')}
                                   for c in task.data['candidates'].values() for e in c['executions']],
                    'nextActions': ['edit.resume', 'model.compare', 'task.deliver']}
        if not self.task_path.exists():
            return {'state': 'not_created', 'nextActions': ['reference.bind', 'task.create']}
        data = json.loads(self.task_path.read_text(encoding='utf-8'))
        return {'taskId': data['taskId'], 'stage': data['stage'], 'recordedState': data['state'],
                'nativeFreshness': 'not_checked', 'reference': data.get('semanticReference'),
                'executions': [{k: e.get(k) for k in ('intentId', 'state', 'nativeState', 'postprocessingState', 'journalPath', 'error')}
                               for c in data['candidates'].values() for e in c['executions']],
                'nextActions': ['Attach explicit current instance/craft for native comparison or original execution queries.']}
