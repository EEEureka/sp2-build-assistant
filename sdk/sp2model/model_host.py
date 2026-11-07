"""Structured semantic commands: sp2model model OP --input-file request.json."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import uuid

from .errors import ModelingError
from .session import Session
from .modeling import ModelingWorkspace
from .model_help import register_operation, operation_help, capabilities, validate_arguments, compact_state
from .journal import Journal
from .reference_import import measure_mesh, bind_mesh_reference


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


TEXT = {'type': 'string', 'minLength': 1}
NUM = {'type': 'number'}
VEC = {'type': 'array', 'items': NUM, 'minItems': 3, 'maxItems': 3}
BOOL = {'type': 'boolean'}
CORNER = obj({'kind': {'enum': ['sharp', 'chamfer', 'round']}, 'distance': NUM, 'samples': {'type': 'integer'}}, ('kind',))
PROFILE = obj({'width': NUM, 'height': NUM, 'corner': CORNER, 'corner_radius': {}, 'corner_stretch': {},
               'trapezium': {}, 'edge_curvature': {}, 'cutting': {}, 'smoothing': {}, 'sync_adjacent': {}, 'thickness_fraction': NUM})
STATION = obj({'id': TEXT, 'center': VEC, 'normal': VEC, 'width': NUM, 'height': NUM, 'profile': PROFILE,
               'featureId': TEXT, 'referenceRegion': {}}, ('center',))
FRAME = obj({'units': {'enum': ['m', 'cm', 'mm']}, 'scale': NUM, 'origin': VEC,
             'axes': obj({'x': TEXT, 'y': TEXT, 'z': TEXT}, ('x', 'y', 'z')), 'handedness': {'enum': ['right', 'left']},
             'scaleSource': {'enum': ['measured', 'user', 'inferred']}, 'rotationQuaternion': {'type': 'array', 'minItems': 4, 'maxItems': 4},
             'basis': {'type': 'array', 'minItems': 3, 'maxItems': 3, 'items': VEC}},
            ('units', 'scale', 'origin', 'axes', 'handedness', 'scaleSource'))
REFERENCE = {'type': 'object', 'required': ['source', 'frame', 'features'], 'properties': {
    'source': {'type': 'object', 'required': ['kind', 'locator'], 'properties': {'kind': {'enum': ['mesh', 'blender', 'photos', 'text']},
        'locator': TEXT, 'text': TEXT, 'files': {'type': 'array'}, 'contentFingerprint': TEXT}},
    'frame': FRAME, 'scope': {'type': 'array', 'items': TEXT},
    'features': {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'required': ['id', 'component', 'kind', 'evidenceKind'],
        'properties': {'id': TEXT, 'component': TEXT, 'kind': {'enum': ['section_contour', 'section_center', 'section_boundary', 'relative_pose', 'negative_space', 'surface', 'mesh_extent', 'visual']},
            'evidenceKind': {'enum': ['measured', 'user', 'inferred', 'assumption']},
            'geometry': {'type': 'object', 'description': 'Per-kind dictionaries: resources/skill/references/Modeling-Reference-Features.md. Prefer reference.measure_mesh for measured indexed meshes.'},
            'expected': {'type': 'object', 'description': 'Same per-kind contract as geometry; see Modeling-Reference-Features.md.'}, 'tolerance_m': NUM, 'assumptionAccepted': BOOL}}},
    'candidates': {'type': 'array'}, 'selectedCandidateIds': {'type': 'array', 'items': TEXT}, 'selectionReason': TEXT,
    'constraints': {'type': 'array'}, 'uncertainties': {'type': 'array'}, 'assumptions': {'type': 'array'},
    'unresolved': {'type': 'array'}, 'views': {'type': 'array'}}}

IDENTIFIER = {'oneOf': [TEXT, {'type': 'integer'}]}
PART_IDS = {'type': 'array', 'items': IDENTIFIER, 'minItems': 1}
MESH_NAMES = {'type': 'array', 'items': TEXT, 'minItems': 1}
SELECTION = {**obj({'partIds': PART_IDS, 'meshNames': MESH_NAMES}),
             'oneOf': [{'required': ['partIds']}, {'required': ['meshNames']}]}
MEASUREMENT_SECTION = {**obj({'id': TEXT, 'component': TEXT, 'partIds': PART_IDS, 'meshNames': MESH_NAMES,
    'origin': VEC, 'normal': VEC, 'axis': VEC, 'fractions': {'type': 'array', 'minItems': 1, 'maxItems': 32,
        'items': {'type': 'number', 'minimum': 0, 'maximum': 1}}, 'up': VEC,
    'tolerance_m': {'type': 'number', 'minimum': 1e-6, 'maximum': 1000}, 'viewId': TEXT,
    'geometryFrame': {'const': 'task_metres'}, 'boundaryRule': {'enum': ['planar_union', 'single_part', 'cap_boundary']},
    'parameters': {'type': 'array', 'items': TEXT}, 'required': BOOL, 'assumptionAccepted': BOOL}, ('id', 'component')),
    'allOf': [
        {'oneOf': [{'required': ['partIds']}, {'required': ['meshNames']}]},
        {'oneOf': [{'required': ['origin', 'normal'], 'not': {'anyOf': [{'required': ['axis']}, {'required': ['fractions']}]}},
                   {'required': ['axis', 'fractions'], 'not': {'anyOf': [{'required': ['origin']}, {'required': ['normal']}]}}]}]}
MEASUREMENT_SECTIONS = {'type': 'array', 'minItems': 1, 'maxItems': 32, 'items': MEASUREMENT_SECTION}
MESH_REFERENCE = deepcopy(REFERENCE)
MESH_REFERENCE['required'] = ['source', 'frame', 'candidates', 'selectedCandidateIds', 'selectionReason']
MESH_REFERENCE['properties']['features']['minItems'] = 0
MESH_REFERENCE['properties']['source']['properties']['kind'] = {'enum': ['mesh', 'blender']}
MESH_REFERENCE['properties']['candidates'] = {'type': 'array', 'minItems': 1, 'items': obj({
    'id': TEXT, 'locator': TEXT, 'transform': {}, 'selection': {'oneOf': [SELECTION, PART_IDS]},
    'preview': {}, 'description': TEXT}, ('id', 'locator', 'transform', 'selection'))}
MESH_REFERENCE['properties']['selectedCandidateIds']['minItems'] = 1

EXAMPLES = {'reference.bind': 'semantic_reference.json', 'reference.measure_mesh': 'semantic_measure_mesh.json',
            'reference.bind_mesh': 'semantic_bind_mesh.json', 'task.create': 'semantic_task.json',
            'model.prism': 'semantic_prism.json', 'model.loft': 'semantic_loft.json', 'model.recess': 'semantic_recess.json',
            'model.refine': 'semantic_refine.json',
            'task.deliver': 'semantic_deliver.json', 'help': 'semantic_help.json'}


def _example(operation):
    filename = EXAMPLES.get(operation)
    if filename is None:
        raise ModelingError('example_unavailable', 'This operation has no static request example; inspect its current contract.', {'operation': operation, 'available': sorted(EXAMPLES)})
    locations = [Path(__file__).parent / 'resources' / 'skill' / 'examples' / filename,
                 Path(__file__).resolve().parents[1] / 'examples' / filename]
    for path in locations:
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8-sig'))
    raise ModelingError('example_unavailable', 'The installed generic example file is missing.', {'operation': operation, 'filename': filename})


def _contracts():
    values = {
        'capabilities': (obj({'prefix': TEXT, 'scene': TEXT, 'cursor': {'type': 'integer', 'minimum': 0},
            'max_chars': {'type': 'integer', 'minimum': 1024, 'maximum': 8191}, 'include_native': BOOL}),
            'List semantic operations without connecting to the game; use nextCursor and prefix for bounded discovery.'),
        'help': (obj({'operation': TEXT, 'topic': TEXT}, ('operation',)), 'Read one short operation contract; use topic for nested fields.'),
        'operation.example': (obj({'operation': {'enum': sorted(EXAMPLES)}}, ('operation',)), 'Read one validated generic request example without opening a session; no model-specific measurements.'),
        'reference.bind': (obj({'reference_id': TEXT, 'spec': REFERENCE, 'replace': BOOL}, ('reference_id', 'spec')), 'Freeze a reviewed source/selection/frame/features. Text and photos do not need Blender.'),
        'reference.measure_mesh': (obj({'mesh_path': TEXT, 'frame': FRAME, 'sections': MEASUREMENT_SECTIONS,
            'weld_tolerance_m': {'type': 'number', 'minimum': 1e-10, 'maximum': .01}}, ('mesh_path', 'frame')),
            'Read-only mesh inventory or exact selected-plane measurements. Source vertices transform once; planes use task metres. No game session or Blender required.'),
        'reference.bind_mesh': (obj({'reference_id': TEXT, 'spec': MESH_REFERENCE, 'mesh_path': TEXT,
            'sections': MEASUREMENT_SECTIONS, 'replace': BOOL}, ('reference_id', 'spec', 'mesh_path', 'sections')),
            'Measure selected source mesh sections and freeze contour/centre/boundary features; requires explicit candidate selection, never native writes.'),
        'reference.inspect': (obj({'reference_id': TEXT}, ('reference_id',)), 'Inspect frozen reference and verify available source hashes.'),
        'task.create': (obj({'name': TEXT, 'intent': TEXT, 'reference_id': TEXT, 'tolerance_m': NUM,
            'part_budget': {'type': 'integer', 'minimum': 1}, 'max_iterations': {'type': 'integer', 'minimum': 1},
            'max_native_operations': {'type': 'integer', 'minimum': 1}}, ('name', 'intent', 'reference_id')), 'Create and freeze a public ModelingTask with per-component geometry targets.'),
        'task.status': (obj({}), 'Read authoritative task/intent state. Without an instance native freshness stays unchecked.'),
        'edit.apply': (obj({'review_id': TEXT}, ('review_id',)), 'Apply the immutable reviewed intent once. Repeating the same ID only queries its original request.'),
        'edit.resume': (obj({'intent_id': TEXT}, ('intent_id',)), 'Query the original execution and finish postprocessing; never resubmit relative transforms.'),
        'model.compare': (obj({'component': TEXT}), 'Compare fresh native geometry against frozen targets and save same-frame overlays.'),
        'surface.inspect': (obj({'part_ids':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'integer'}},'vertex_attributes':{'type':'array','minItems':1,'uniqueItems':True,'items':{'enum':['normals','tangents']}}},('part_ids',)), 'Read final native render positions and actual shading attributes into a hashed result artifact; no mesh mutation.'),
        'surface.check': (obj({'part_id':{'type':'integer'},'mesh_index':{'type':'integer','minimum':0},'boundary':{'type':'array','minItems':3,'maxItems':64,'items':VEC},'normal':VEC,'tolerance_m':NUM,'normal_tolerance_deg':NUM,'selection_angle_deg':NUM,'selection_distance_m':NUM},('part_id','boundary','normal')), 'Check the whole convex face footprint, plane and actual shading normals on a fresh capture in world metres. Search corridor is separate from acceptance tolerances.'),
        'model.refine': (obj({'component': TEXT, 'name': TEXT, 'station_updates': {'type': 'object', 'minProperties': 1,
            'additionalProperties': {**obj({'center': VEC, 'width': NUM, 'height': NUM, 'profile': PROFILE}), 'minProperties': 1}},
            'protected_station_ids': {'type': 'array', 'items': TEXT, 'uniqueItems': True}, 'hypothesis': TEXT},
            ('component', 'name', 'station_updates')),
            'Preview equal-topology station refinement of the named compiled loft. Current native shape/pose must match; protected stations and unmentioned fields remain intact.'),
        'task.deliver': (obj({'name': TEXT, 'delivery_id': TEXT, 'overwrite': BOOL, 'allow_incomplete': BOOL}, ('name', 'delivery_id')),
                         'Save, reopen, explicitly rebind and remeasure. Partial save requires allow_incomplete:true and is never complete delivery.'),
    }
    common = {'name': TEXT, 'normal': VEC, 'up': VEC, 'max_parts': {'type': 'integer', 'minimum': 1, 'maximum': 20}}
    shapes = {
        'model.loft': obj({**common, 'stations': {'type': 'array', 'minItems': 2, 'items': STATION}}, ('name', 'stations')),
        'model.prism': obj({**common, 'start': VEC, 'end': VEC, 'width': NUM, 'height': NUM, 'profile': PROFILE}, ('name', 'start', 'end', 'width', 'height')),
        'model.recess': obj({**common, 'start': VEC, 'end': VEC, 'width': NUM, 'height': NUM,
            'opening_width': NUM, 'floor_height': NUM, 'opening_center': NUM}, ('name', 'start', 'end', 'width', 'height', 'opening_width', 'floor_height')),
    }
    for operation, shape in shapes.items():
        values[operation] = (obj({'component': TEXT, 'shape': shape, 'replace': BOOL, 'hypothesis': TEXT}, ('component', 'shape')),
                             'Compile and preview native geometry only. Inspect the review, then edit.apply. Independent centres and per-section dimensions are retained.')
    for operation, fields in {
        'model.move': {'translation': VEC}, 'model.rotate': {'axis': VEC, 'angle_deg': NUM, 'pivot': VEC},
        'model.scale': {'factors': VEC, 'pivot': VEC}, 'model.patch': {'patch': {'type': 'object', 'minProperties': 1}}
    }.items():
        values[operation] = (obj({'component': TEXT, 'hypothesis': TEXT, **fields}, ('component', *fields)),
                             'Preview a current bound component edit in the task frame. No native write until edit.apply.')
    for name, (schema, summary) in values.items():
        register_operation(name, schema, summary=summary,
                           example=_example(name) if name in EXAMPLES else None,
                           mutates=name in ('edit.apply', 'task.deliver'),
                           next_actions=['help', 'task.status'])
    return values


def execute(argv, *, session_factory=None):
    contracts = _contracts()
    session = None
    before = set()
    workspace = None
    operation = None
    try:
        parser = argparse.ArgumentParser(prog='sp2model model')
        parser.add_argument('operation', nargs='?', default='capabilities', choices=sorted(contracts))
        parser.add_argument('--workspace', default=None)
        source = parser.add_mutually_exclusive_group()
        source.add_argument('--input-file')
        source.add_argument('--input')
        parser.add_argument('--instance')
        parser.add_argument('--craft')
        parser.add_argument('--discovery-dir')
        parser.add_argument('--timeout', type=float, default=30)
        parser.add_argument('--full', action='store_true')
        args = parser.parse_args(argv)
        operation = args.operation
        data = json.loads(Path(args.input_file).read_text(encoding='utf-8-sig') if args.input_file else args.input or '{}')
        validate_arguments(data, contracts[operation][0], operation=operation)
        if operation == 'capabilities':
            result = capabilities(**data)
        elif operation == 'help':
            result = operation_help(data['operation'], topic=data.get('topic'))
        elif operation == 'operation.example':
            result = {'operation': data['operation'], 'example': _example(data['operation']),
                      'source': 'packaged generic sdk/examples request',
                      'nextAction': 'Copy the request, replace paths and component targets, then review before any edit.apply.',
                      'featureDocumentation': 'resources/skill/references/Modeling-Reference-Features.md'}
        else:
            if not args.workspace:
                raise ModelingError('workspace_required', 'Choose a persistent task directory with --workspace.')
            offline = operation in ('reference.bind', 'reference.inspect', 'reference.measure_mesh', 'reference.bind_mesh')
            needs_session = not offline and (operation != 'task.status' or bool(args.instance or args.craft))
            if needs_session:
                if not args.instance or not args.craft:
                    raise ModelingError('session_required', 'Supply both explicit --instance and --craft.')
                root = Path(args.workspace).resolve()
                session = (session_factory or Session.attach)(instance=args.instance, craft=args.craft,
                    discovery_dir=args.discovery_dir, timeout=args.timeout, journal_dir=root / 'executions', project_path=root / 'project.json')
                session._host_initial_craft = session.identity['craftSessionId']
                from .host import _journals
                before = {row['path'] for row in _journals(session)}
            workspace = ModelingWorkspace(args.workspace, session)
            if operation == 'reference.bind':
                result = workspace.references.bind(**data)
            elif operation == 'reference.measure_mesh':
                result = measure_mesh(**data)
            elif operation == 'reference.bind_mesh':
                result = bind_mesh_reference(workspace.references, **data)
            elif operation == 'reference.inspect':
                result = {'reference': workspace.references.inspect(data['reference_id']), 'verification': workspace.references.verify(data['reference_id'])}
            elif operation == 'task.create':
                result = workspace.create(**data)
            elif operation == 'task.status':
                result = workspace.status()
            elif operation == 'edit.apply':
                result = workspace.apply(data['review_id'])
            elif operation == 'edit.resume':
                task = workspace.task()
                result = {'receipt': task.resume_edit(data['intent_id']).to_dict(), 'task': task.report(), 'replayed': False}
            elif operation == 'model.compare':
                result = workspace.compare(**data)
            elif operation == 'surface.inspect':
                scene=session.inspect();parts=[scene.part(id=i) for i in data['part_ids']]
                result=session.mesh(parts,vertex_attributes=data.get('vertex_attributes',['normals'])).to_dict(include_geometry=True)
            elif operation == 'surface.check':
                options=deepcopy(data);part_id=options.pop('part_id');mesh_index=options.pop('mesh_index',0)
                scene=session.inspect();mesh=session.mesh([scene.part(id=part_id)],vertex_attributes=['normals'])
                result=mesh.planar_face_region(mesh_index,**options)
            elif operation == 'task.deliver':
                from .delivery import deliver_task
                result = deliver_task(workspace.task(), 'model', **data)
            else:
                result = workspace.preview(operation, data)
        from .host import to_jsonable, _phases
        envelope = {'schemaVersion': 'sp2model.semantic-host/1', 'ok': True, 'operation': operation,
                    'result': to_jsonable(result), 'execution': _phases(session, before, script_ok=True)}
        if session is not None:
            envelope['transport'] = getattr(session.client, 'statistics', {'status': 'unavailable'})
        if workspace is not None:
            result_path = workspace.directory / 'results' / (uuid.uuid4().hex + '.json')
            result_path.parent.mkdir(exist_ok=True)
            Journal.update(result_path, envelope)
            if not args.full and len(json.dumps(envelope, ensure_ascii=False)) > 6000:
                envelope['result'] = compact_state(envelope['result'], max_chars=4500, source=str(result_path))
            envelope['resultFile'] = str(result_path)
        from .updates import decorate as update_notices
        return 0, update_notices(envelope, session.client if session is not None else None)
    except SystemExit as error:
        if error.code == 0:
            return 0, None
        from .updates import decorate as update_notices
        return 1, update_notices({'ok': False, 'error': {'code': 'invalid_arguments', 'message': 'Use sp2model model --help.'}})
    except Exception as error:
        from .host import _phases
        public = error.to_dict() if isinstance(error, ModelingError) else {'code': 'semantic_error', 'message': str(error), 'details': {'type': type(error).__name__}}
        envelope = {'schemaVersion': 'sp2model.semantic-host/1', 'ok': False, 'operation': operation, 'error': public,
                    'execution': _phases(session, before, script_ok=False), 'recovery': 'Inspect original intent and journal. Do not replay relative writes.'}
        if workspace is not None:
            envelope['workspace'] = str(workspace.directory)
        from .updates import decorate as update_notices
        return 1, update_notices(envelope, session.client if session is not None else None)
