"""Local reference commands; numerical work is isolated from the edit CLI."""
from __future__ import annotations

import json
from pathlib import Path
import build_review_cli
import build_guidance

FOUNDATIONS = {
    'reference.create': 'project.create', 'reference.inspect': 'project.read',
    'reference.validate': 'project.validate', 'reference.add': 'source.add',
    'reference.freeze': 'profile.freeze', 'reference.bind': 'bind',
    'reference.rebind': 'rebind', 'reference.changes': 'changes', 'reference.merge': 'binding.threeWay',
    'structure.set': 'structure.set', 'structure.plan': 'structure.plan', 'structure.impact': 'structure.impact',
    'structure.replace': 'structure.run', 'structure.status': 'structure.status',
    'structure.reconcile': 'structure.reconcile', 'shape.plan': 'shape.plan',
    'structure.restore': 'structure.restore',
    'representation.check': 'representation.check', 'quality.evaluate': 'quality.evaluate',
}
WORKER = {'reference.' + x for x in ('annotate', 'constraints', 'calibrate', 'project', 'render', 'compare')} | {
    'fit.' + x for x in ('plan', 'evaluate', 'verify')}
PROVIDERS = {prefix + '.' + action for prefix in ('mesh', 'blender') for action in ('inspect', 'load')} | {'image.inspect', 'image.normalize'}
COMMANDS = set(FOUNDATIONS) | WORKER | PROVIDERS | {'reference.doctor', 'feature.setup', 'features.list', 'fit.apply', 'structure.reshape', 'knowledge.capabilityaudit'} | build_review_cli.COMMANDS | build_guidance.COMMANDS
MUTATES = {'reference.create', 'reference.add', 'reference.freeze', 'reference.bind', 'reference.rebind',
           'structure.set', 'structure.plan', 'structure.replace', 'structure.reconcile', 'structure.restore', 'fit.apply', 'feature.setup'}
MUTATES |= build_review_cli.MUTATES | {'structure.reshape'}
LIVE = {'structure.replace', 'structure.reconcile', 'structure.restore', 'fit.apply', 'structure.reshape'} | build_review_cli.LIVE | build_guidance.LIVE

# Full nested objects are validated by their owning subsystem. Explicit scalar
# types here also make flags and --input share one discoverable contract.
FIELDS = {
    'project':'string', 'path':'string', 'name':'string', 'action':'string', 'sourceId':'string',
    'source':'object', 'sources':'array', 'scope':'object', 'structures':'array', 'structure':'object',
    'role':'string', 'roles':'array', 'locks':'array', 'units':'string', 'unit':'string',
    'upAxis':'string', 'forwardAxis':'string', 'scale':'number', 'selection':['object','array'],
    'includeHidden':'boolean', 'includeExcluded':'boolean', 'snapshot':'object', 'baseline':'object',
    'current':'object', 'target':'object', 'identity':'object', 'anchors':'array',
    'referencePoints':'array', 'craftPoints':'array', 'transform':'array', 'binding':'object',
    'allowSessionChange':'boolean', 'allowTranslation':'boolean', 'toleranceMetres':'number',
    'plan':'object', 'planPath':'string', 'journalPath':'string', 'runId':'string',
    'operations':'array', 'oldPartIds':'array', 'newParts':'array', 'dependencies':'array',
    'parameters':'array', 'constraints':'array', 'measurements':'array', 'metrics':'object',
    'profile':'object', 'budget':'object', 'shape':'object', 'family':'string', 'points':['object','array'],
    'lower':'array', 'upper':'array', 'thickness':'number', 'style':'string',
    'image':'string', 'annotations':'array', 'features':'array', 'ignoreRegions':'array',
    'camera':'object', 'intrinsics':'object', 'worldPoints':'array', 'imagePoints':'array',
    'projection':'string', 'knownScale':'number', 'resolution':'object', 'outputDir':'string',
    'mesh':['object','string'], 'reference':'object', 'actual':'object', 'regions':'array',
    'referenceMesh':['object','string'], 'actualMesh':['object','string'], 'referencePath':'string', 'actualPath':'string',
    'candidate':'object', 'model':'object', 'targets':'array', 'bounds':'object',
    'maxEvaluations':'integer', 'seed':'integer', 'frozen':'array', 'proxy':'object',
    'workerPython':'string', 'installDir':'string', 'python':'string', 'offline':'boolean',
    'wheelhouse':'string', 'verifyHashes':'boolean', 'requestId':'string',
    'imagePath':'string', 'outputPath':'string', 'outputDirectory':'string',
    'worldToCamera':'array', 'width':'integer', 'height':'integer', 'scaleKnown':'boolean',
    'focalBounds':'array', 'pixel':'array', 'plane':'object', 'depth':'number',
    'includeBuffers':'boolean', 'selfTest':'boolean', 'basePython':'string', 'force':'boolean',
    'overwrite':'boolean', 'coordinateSystem':'object', 'changeLocks':'boolean',
    'partIds':'array', 'affectedPartIds':'array', 'reusedPartIds':'array',
    'referenceToCraft':'object', 'partMapping':'object', 'base':'object', 'proposed':'object',
    'evidence':['object','string'], 'qualityProfile':['object','string'], 'output':'string',
    'createOperations':'array', 'migrationOperations':'array', 'referencePaths':'array',
    'materialIntent':'object', 'geometryEvidence':'object', 'finalEvidence':'object',
    'lowerStart':'array', 'lowerEnd':'array', 'upperStart':'array', 'upperEnd':'array',
    'partBudget':'integer', 'templateId':'string', 'nativeDomain':'object', 'temporaryPrefix':'string',
    'sections':'array', 'cameraFrozen':'boolean', 'expectedCameraHash':'string',
    'referenceMask':['string','array'], 'ignoreMask':['string','array'],
    'sampleCount':'integer', 'sampleSpacing':'number', 'compareSurface':'boolean',
    'actualIdentity':'object', 'geometryStamp':['object','string'], 'tolerances':'object',
    'proxyCalibration':['object','null'], 'requireNativePrecision':'boolean',
    'gameVersion':'string', 'shapeFamily':'string', 'frozenPartIds':'array',
    'robustScale':'number', 'regularization':'number', 'nativeValidation':'object',
    'proxyComparison':'object', 'parameterTolerance':'number', 'requireIndependentView':'boolean',
    'validation':'object', 'rollbackOnFailure':'boolean', 'downloadBase':'string',
    'metersPerUnit':'number',
    'lockedPartIds':'array', 'boundaryPartIds':'array', 'finalizeOperations':'array',
    'structureId':'string', 'expectedChanges':'object', 'operationId':'string',
    'nativeDependencyEvidence':'object','targetingEvidence':'object','proxyErrorBudgetMetres':'number',
    'nativeSectionCount':'integer','probeBridge':'boolean',
    'batchSize':'integer','splitDiagonal':'string','frame':'object','degradationTolerance':'number',
    'originalSize':'array','originalToPreview':'array','near':'number','far':'number',
    'depthOffset':'number','maxResidualPx':'number','robustScalePx':'number','fyRatio':'number',
    'cx':'number','cy':'number','maxAxisNonOrthogonality':'number','focalCandidates':'integer',
    'referenceVersion':['string','object'],'unobserved':'array',
    'ransac':'boolean','ransacThresholdPx':'number','allowRejectedAnchors':'boolean',
    'mode':'string','editOperations':'array','pluginVersion':'string','loopJournalPath':'string',
    'loopReview':'object','visualEvidence':'object','semanticMapping':'object','protectedFieldMapping':'array',
    'ownershipMapping':'array','cases':'array','versions':'object','catalogEvidence':'object','versionEvidence':'object',
}
for _field,_field_type in build_review_cli.FIELDS.items():
    FIELDS.setdefault(_field,_field_type)
for _field,_field_type in build_guidance.FIELDS.items():
    FIELDS.setdefault(_field,_field_type)

def input_schema(command):
    if command in build_guidance.COMMANDS:
        return build_guidance.input_schema(command)
    if command in build_review_cli.COMMANDS:
        return build_review_cli.input_schema(command)
    properties = {key:{'type':value} for key,value in FIELDS.items()}
    required = ['project'] if command in {
        'reference.create','reference.inspect','reference.validate','reference.add','reference.freeze',
        'reference.bind','reference.rebind','reference.changes','structure.set'} else []
    return {'type':'object','properties':properties,'required':required,'additionalProperties':False,
            'description':'Versioned local reference request. Numerical commands require the installed CPU worker; ordinary commands never download dependencies.'}

def output_schema(command):
    if command in build_review_cli.COMMANDS:
        return build_review_cli.output_schema(command)
    return {'type':'object','required':['success','schemaVersion'],
            'properties':{'success':{'type':'boolean'},'schemaVersion':{'const':'1'},
                          'data':{'type':'object'},'error':{'type':'object'}},
            'oneOf':[{'properties':{'success':{'const':True}},'required':['data']},
                     {'properties':{'success':{'const':False}},'required':['error']}]}

def dispatch(command, payload, live):
    if command in build_guidance.COMMANDS:
        return build_guidance.dispatch(command, payload, live)
    if command=='knowledge.capabilityaudit':
        from native_capability_audit import dispatch as capability_dispatch
        return capability_dispatch(command,payload,context={'live':live})
    if command in build_review_cli.COMMANDS:
        return build_review_cli.dispatch(command,payload,live)
    if command=='structure.reshape':
        from reference_storage import ReferenceError,read_json
        plan=payload.get('plan') or (read_json(payload['planPath']) if payload.get('planPath') else {})
        if plan.get('mode')!='reshape':
            raise ReferenceError('invalid_plan','structure reshape requires a mode=reshape plan; create it with structure plan')
        from reference_project import dispatch as project_dispatch
        return project_dispatch('structure.run',{**payload,'plan':plan},context={'live':live})
    if command in FOUNDATIONS:
        from reference_project import dispatch as project_dispatch
        return project_dispatch(FOUNDATIONS[command],payload,context={'live':live})
    if command in WORKER:
        from dependencies import worker_call
        return worker_call(command,payload)
    if command in PROVIDERS:
        from reference_providers import dispatch as provider_dispatch
        return provider_dispatch(command,payload)
    if command=='reference.doctor':
        from dependencies import doctor
        return doctor(payload)
    if command=='feature.setup':
        from dependencies import setup
        return setup(payload)
    if command=='features.list':
        from feature_registry import discover
        bridge=None
        if payload.get('probeBridge'):
            try: bridge=live('designer.status',{})
            except Exception as error: bridge={'success':False,'error':{'code':getattr(error,'code','bridge_unavailable'),'message':str(error)}}
        return discover(payload,bridge=bridge)
    if command=='fit.apply':
        from fit_runner import apply
        from dependencies import worker_call
        from native_fit_bridge import make_live
        return apply(payload,live=make_live(live,payload),worker_call=worker_call)
    raise ValueError('Unsupported local reference command: '+command)
