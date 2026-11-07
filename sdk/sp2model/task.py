"""Durable, frozen modeling contracts with native evidence and stage gates.

This is external task state, not a prompt-retention guarantee or an autonomous
model generator. It never evaluates task text or replays a submitted plan.
"""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import hashlib,json,os,uuid
from .errors import ModelingError
from .geometry import Frame,number,vector,unit,sub,dot,magnitude
from .geometry import quaternion,rotation_distance_degrees
from .journal import Journal
from .project import label,same_identity
from .transport import canonical_json
from .mesh import MeshEvidence,compare_contours
from .surface import compare_surfaces,triangles

STAGES=('reference','proportions','primary_shape','openings_interfaces','secondary','detail_material','function_delivery')
STOP_REASONS={'within_tolerance','stagnation','insufficient_constraints','representation_limited','measurement_invalid','tool_blocked','budget_exhausted','scene_changed'}


class ModelingTask:
    SCHEMA='sp2model.task/1'

    def __init__(self,session,path,*,name=None,intent=None,max_candidates=8,max_iterations=12,max_native_operations=800,minimum_improvement_m=.001):
        self.session=session;self.path=Path(path).resolve();self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists():
            label(name,'task name')
            if not isinstance(intent,str) or not intent.strip():raise ModelingError('invalid_task','A new task needs the original user shape intent')
            for key,value in (('max_candidates',max_candidates),('max_iterations',max_iterations),('max_native_operations',max_native_operations)):
                if type(value) is not int or value<1:raise ModelingError('invalid_task',key+' must be a positive integer')
            record={'schemaVersion':self.SCHEMA,'taskId':uuid.uuid4().hex,'name':name,'originalIntent':intent,
                    'instanceId':session.client.instance['instanceId'],'initialIdentity':session.identity,
                    'references':{},'components':{},'metrics':{},'candidates':{},'iterations':[],
                    'budget':{'candidates':max_candidates,'iterations':max_iterations,'nativeOperations':max_native_operations,
                              'minimumImprovementMetres':number(minimum_improvement_m,'minimum_improvement_m',0)},
                    'frozen':False,'stage':'reference','state':'draft','contractAmendments':[],'stop':None}
            with self.path.open('xb') as stream:stream.write(canonical_json(record));stream.flush();os.fsync(stream.fileno())
        self.reload()

    def reload(self):
        raw=self.path.read_bytes();self.data=json.loads(raw)
        if self.data.get('schemaVersion')!=self.SCHEMA:raise ModelingError('invalid_task','Unsupported external task schema')
        self._hash=hashlib.sha256(raw).hexdigest();self._contract();return self

    def _contract(self):
        if not self.data.get('frozen'):return
        digest=hashlib.sha256(canonical_json({k:self.data[k] for k in ('references','components','metrics','budget')})).hexdigest()
        required=[id for id,m in self.data['metrics'].items() if m['required']]
        if digest!=self.data.get('contractHash') or sorted(required)!=sorted(self.data.get('requiredMetricIds',[])):
            raise ModelingError('contract_changed','Frozen targets, denominator or budget changed; use a reviewed amendment with original values retained')

    def _reference_changes(self):
        changed=[]
        for id,reference in self.data['references'].items():
            if reference['hashMeaning']!='file bytes':continue
            path=Path(reference['source']);actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            if actual!=reference['sha256']:changed.append({'id':id,'source':str(path),'originalSha256':reference['sha256'],'currentSha256':actual})
        return changed

    def _evidence_fresh(self,identity):
        # Only check() owns this short, read-only batch. Its end fence must
        # succeed before callers receive a passing report. Stored observations
        # keep the capture identity, so a concurrent edit never becomes current.
        batch=getattr(self,'_check_identity',None)
        if batch is None:self.session._fresh(identity)
        elif not same_identity(batch,identity) or not same_identity(batch,self.session.identity):
            raise ModelingError('stale_evidence','Native evidence changed during the read-only check batch')

    @contextmanager
    def _edit(self):
        lock=self.path.with_name(self.path.name+'.lock')
        try:stream=lock.open('xb')
        except FileExistsError:raise ModelingError('task_busy','Another task update holds the external state lock') from None
        before=deepcopy(self.data)
        try:
            with stream:
                if hashlib.sha256(self.path.read_bytes()).hexdigest()!=self._hash:raise ModelingError('task_conflict','Task changed on disk; reload and review')
                self._contract()
                yield
                self._contract()
                Journal.update(self.path,self.data);self._hash=hashlib.sha256(self.path.read_bytes()).hexdigest()
        except Exception:self.data=before;raise
        finally:lock.unlink(missing_ok=True)

    def _draft(self):
        if self.data['frozen']:raise ModelingError('contract_frozen','Goals, tolerances, coverage denominator and budgets are frozen; explicit contract amendment starts a new evaluation')

    def reference(self,id,*,kind,source,subject,units='m',frame=None,uncertainties=()):
        self._draft();label(id,'reference id');label(subject,'selected subject')
        if kind not in ('blender','photo','drawing','verbal','native'):raise ModelingError('invalid_reference','Choose blender, photo, drawing, verbal or native')
        if units not in ('m','cm','mm'):raise ModelingError('invalid_reference','Reference units must be explicit')
        if not isinstance(source,str) or not source.strip():raise ModelingError('invalid_reference','Supply source path/URI or original verbal constraints')
        if isinstance(uncertainties,str):raise ModelingError('invalid_reference','uncertainties must be an explicit list')
        path=Path(source)
        digest=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else hashlib.sha256(source.encode('utf-8')).hexdigest()
        reference={'kind':kind,'source':source,'sha256':digest,'hashMeaning':'file bytes' if path.is_file() else 'source locator or verbal text; remote content not downloaded',
                   'subject':subject,'units':units,'frame':(frame or Frame.world()).to_dict(),'uncertainties':list(uncertainties)}
        with self._edit():self.data['references'][id]=reference
        return self

    def component(self,id,*,intent,strategy,interfaces=(),functional_role=None):
        self._draft();label(id,'component id');label(strategy,'representation strategy')
        if not isinstance(intent,str) or not intent.strip():raise ModelingError('invalid_component','Describe the semantic feature intent')
        if isinstance(interfaces,str):raise ModelingError('invalid_component','interfaces must list shared complete profiles/planes and constraints')
        with self._edit():self.data['components'][id]={'intent':intent,'strategy':strategy,'interfaces':list(interfaces),'functionalRole':functional_role}
        return self

    def metric(self,id,*,component,kind,expected,reference_id,tolerance_m=.002,stage='primary_shape',required=True,frame=None):
        self._draft();label(id,'metric id')
        if component not in self.data['components'] or reference_id not in self.data['references']:raise ModelingError('invalid_metric','Register the semantic component and reference first')
        if kind not in ('mesh_extent','section_contour','point_probe','pose','visual','function','seam','surface','reference_geometry','hard_face'):raise ModelingError('invalid_metric','Choose an explicit geometric, visual or functional metric category')
        if stage not in STAGES or type(required) is not bool:raise ModelingError('invalid_metric','Use a declared stage and boolean required flag')
        tolerance=number(tolerance_m,'tolerance_m',0,1000)
        if not isinstance(expected,dict):raise ModelingError('invalid_metric','expected must define the geometric quantity, units and frame')
        if kind=='hard_face':
            boundary=expected.get('boundary')
            if not isinstance(boundary,(list,tuple)) or not 3<=len(boundary)<=64:raise ModelingError('invalid_metric','Hard face requires a complete convex boundary')
            from .hard_surfaces import validate_face_target
            validate_face_target(boundary,expected.get('normal'),tolerance)
            expected={'boundary':[list(vector(p)) for p in boundary],'normal':list(unit(expected.get('normal'))),
                      'normal_tolerance_deg':number(expected.get('normal_tolerance_deg',.5),'normal tolerance',1e-6,10),
                      'selection_angle_deg':number(expected.get('selection_angle_deg',25),'selection angle',1,80),
                      'selection_distance_m':number(expected.get('selection_distance_m',.05),'selection distance',max(.00001,tolerance),1)}
        elif kind=='mesh_extent':
            expected={'axis':list(unit(expected.get('axis'),'extent axis')),'valueMetres':number(expected.get('value_m'),'extent metres',.000001)}
        elif kind=='section_contour':
            origin=vector(expected.get('origin'),'section origin metres');normal=unit(expected.get('normal'),'section normal')
            segments=expected.get('segments')
            if not isinstance(segments,(list,tuple)) or not segments:raise ModelingError('invalid_metric','A complete reference section requires explicit segments')
            checked=[]
            for segment in segments:
                if len(segment)!=2:raise ModelingError('invalid_metric','Contour segment needs two endpoints')
                pair=[list(vector(p,'reference contour metres')) for p in segment]
                if any(abs(dot(sub(p,origin),normal))>1e-7 for p in pair):raise ModelingError('inconsistent_target','Reference contour vertices are outside the declared section plane')
                checked.append(pair)
            expected={'origin':list(origin),'normal':list(normal),'segments':checked}
        elif kind=='point_probe':
            if type(expected.get('inside')) is not bool:raise ModelingError('invalid_metric','Point probe requires explicit inside boolean')
            expected={'point':list(vector(expected.get('point'),'probe point metres')),'inside':expected['inside']}
        elif kind=='pose':
            if expected.get('position_m') is None and expected.get('rotation_quaternion') is None:raise ModelingError('invalid_metric','Pose needs an explicit position or rotation target')
            expected={**({'positionMetres':list(vector(expected['position_m'],'pose metres'))} if expected.get('position_m') is not None else {}),
                      **({'rotationQuaternion':list(quaternion(expected['rotation_quaternion']))} if expected.get('rotation_quaternion') is not None else {}),
                      'toleranceDegrees':number(expected.get('tolerance_deg',.01),'tolerance_deg',0,180)}
        elif kind=='seam':
            other=expected.get('other_component')
            if other is not None and (other not in self.data['components'] or other==component):raise ModelingError('invalid_interface','Choose a distinct registered opposite semantic component')
            expected={'origin':list(vector(expected.get('origin'),'interface origin metres')),'normal':list(unit(expected.get('normal'),'interface normal')),
                      **({'otherComponent':other} if other is not None else {})}
        elif kind=='surface':
            values=triangles(expected.get('triangles',[]))
            if not values:raise ModelingError('invalid_metric','A complete surface target needs explicit selected reference triangles')
            samples=expected.get('max_samples',50000);tests=expected.get('max_triangle_tests',2000000)
            if type(samples) is not int or not 1<=samples<=1000000 or type(tests) is not int or not 1<=tests<=20000000:raise ModelingError('measurement_budget','Freeze explicit bounded surface measurement costs')
            expected={'triangles':values,'max_samples':samples,'max_triangle_tests':tests}
        elif kind=='reference_geometry':
            from .model_compare import validate_coverage
            if not isinstance(expected.get('reference'),dict) or not isinstance(expected.get('targets'),dict):
                raise ModelingError('invalid_metric','reference_geometry needs a frozen reference and generated target contract')
            if expected['targets'].get('scopeComponents') != [component]:
                raise ModelingError('component_coverage','Each reference metric must target exactly its registered component')
            coverage=validate_coverage(expected['reference'],expected['targets'])
            if coverage.get('status')!='passed':
                raise ModelingError('contract_incomplete','Reference targets need complete declared feature coverage before freezing',coverage)
        frame=frame or Frame.world()
        with self._edit():self.data['metrics'][id]={'component':component,'kind':kind,'expected':deepcopy(expected),'referenceId':reference_id,'toleranceMetres':tolerance,'stage':stage,'required':required,'frame':frame.to_dict()}
        return self

    def freeze(self):
        self._draft()
        if self._reference_changes():raise ModelingError('reference_changed','Reference changed after registration; review and register its current source before freezing')
        if not self.data['references'] or not self.data['components'] or not any(m['required'] for m in self.data['metrics'].values()):raise ModelingError('contract_incomplete','Need references, components and at least one required metric')
        missing=[id for id in self.data['components'] if not any(m['component']==id and m['required'] for m in self.data['metrics'].values())]
        if missing:raise ModelingError('contract_incomplete','Every semantic component needs an explicit required metric',{'components':missing})
        with self._edit():
            self.data.update(frozen=True,state='active',requiredMetricIds=[id for id,m in self.data['metrics'].items() if m['required']])
            self.data['contractHash']=hashlib.sha256(canonical_json({k:self.data[k] for k in ('references','components','metrics','budget')})).hexdigest()
        return self.report()

    def amend_metric(self,path,metric_id,*,reason,expected=None,tolerance_m=None):
        """Create a new draft evaluation; retain the original contract verbatim."""
        self._contract()
        if not self.data['frozen'] or metric_id not in self.data['metrics'] or not isinstance(reason,str) or not reason.strip():raise ModelingError('invalid_amendment','Choose a frozen metric and record why its target is corrected')
        if Path(path).exists():raise ModelingError('task_exists','Amendment needs a new external task path; original evidence is retained')
        updated=type(self)(self.session,path,name=self.data['name'],intent=self.data['originalIntent'])
        source=deepcopy(self.data['metrics'][metric_id]);new_expected=deepcopy(source['expected'] if expected is None else expected)
        if source['kind']=='mesh_extent' and expected is None:new_expected={'axis':new_expected['axis'],'value_m':new_expected['valueMetres']}
        if source['kind']=='pose' and expected is None:new_expected={'position_m':new_expected.get('positionMetres'),'rotation_quaternion':new_expected.get('rotationQuaternion'),'tolerance_deg':new_expected['toleranceDegrees']}
        if source['kind']=='seam' and expected is None and 'otherComponent' in new_expected:new_expected['other_component']=new_expected.pop('otherComponent')
        with updated._edit():
            for field in ('references','components','metrics','budget'):updated.data[field]=deepcopy(self.data[field])
            updated.data['parentContract']={'taskId':self.data['taskId'],'contractHash':self.data['contractHash'],'taskPath':str(self.path),'reason':reason,
                'originalMetric':source,'originalReferences':deepcopy(self.data['references']),'originalBudget':deepcopy(self.data['budget'])}
        updated.metric(metric_id,component=source['component'],kind=source['kind'],expected=new_expected,reference_id=source['referenceId'],
                       tolerance_m=source['toleranceMetres'] if tolerance_m is None else tolerance_m,stage=source['stage'],required=source['required'],
                       frame=Frame(**({'kind':'world'} if source['frame']['kind']=='world' else {'kind':'custom','position':tuple(source['frame']['position']),'rotation_quaternion':tuple(source['frame']['rotationQuaternion'])})))
        return updated

    def extent(self,id,*,component,reference_id,axis,value_m,tolerance_m=.002,stage='proportions'):
        return self.metric(id,component=component,reference_id=reference_id,kind='mesh_extent',expected={'axis':axis,'value_m':value_m},tolerance_m=tolerance_m,stage=stage)

    def contour(self,id,*,component,reference_id,origin,normal,segments,tolerance_m=.002,stage='primary_shape'):
        return self.metric(id,component=component,reference_id=reference_id,kind='section_contour',expected={'origin':origin,'normal':normal,'segments':segments},tolerance_m=tolerance_m,stage=stage)

    def probe(self,id,*,component,reference_id,point,inside,stage='openings_interfaces'):
        return self.metric(id,component=component,reference_id=reference_id,kind='point_probe',expected={'point':point,'inside':inside},stage=stage)

    def pose(self,id,*,component,reference_id,position_m=None,rotation_quaternion=None,tolerance_m=.002,tolerance_deg=.01,stage='proportions',frame=None):
        return self.metric(id,component=component,reference_id=reference_id,kind='pose',expected={'position_m':position_m,'rotation_quaternion':rotation_quaternion,'tolerance_deg':tolerance_deg},tolerance_m=tolerance_m,stage=stage,frame=frame)

    def seam(self,id,*,component,reference_id,origin,normal,other_component=None,tolerance_m=.002,stage='openings_interfaces',frame=None):
        return self.metric(id,component=component,reference_id=reference_id,kind='seam',expected={'origin':origin,'normal':normal,'other_component':other_component},tolerance_m=tolerance_m,stage=stage,frame=frame)

    def candidate(self,id,*,components,strategy,parameters=None,part_budget=100):
        if not self.data['frozen']:raise ModelingError('contract_not_frozen','Freeze goals, denominator and budget before modeling')
        label(id,'candidate id');components=list(components)
        if not components or any(c not in self.data['components'] for c in components) or type(part_budget) is not int or part_budget<1:raise ModelingError('invalid_candidate','Explicit registered components and positive part budget required')
        if id in self.data['candidates']:raise ModelingError('candidate_exists','Candidate IDs cannot be reused')
        if len(self.data['candidates'])>=self.data['budget']['candidates']:raise ModelingError('modeling_budget','Candidate budget exhausted; stop and record the best evidence')
        with self._edit():self.data['candidates'][id]={'components':components,'strategy':strategy,'parameters':deepcopy(parameters or {}),'partBudget':part_budget,'executions':[],'observations':{},'bindings':{},'state':'planned'}
        return self

    def bind(self,candidate_id,component,parts):
        candidate=self.data['candidates'][candidate_id]
        if component not in candidate['components']:raise ModelingError('invalid_component','Candidate does not represent this component')
        parts=list(parts)
        ids=[self.session._resolve_ref(p) for p in parts]
        if not ids or len(ids)!=len(set(ids)):raise ModelingError('invalid_selector','Explicit distinct current component members required')
        rows={p['id']:p for p in self.session._snapshot['parts']}
        with self._edit():candidate.setdefault('bindings',{})[component]=[{'id':p.id,'logicalId':p.logical_id,'lifetimeId':rows[p.id].get('lifetimeId'),'type':p.type,'identity':self.session.identity} for p in parts]
        return self

    def correction_review(self,candidate_id,component):
        """Propose an explicit scope-limited return to a measured failed stage.

        This read-only review is carried by the immutable semantic edit review.
        It cannot turn an unmeasured component into a verified one or permit
        adding detail while a different component's earlier gate is failing.
        """
        self._contract()
        candidate=self.data['candidates'][candidate_id]
        if component not in candidate['components']:raise ModelingError('invalid_component','Choose a component represented by this candidate')
        current=STAGES.index(self.data['stage']);failed=[]
        for id in self.data.get('requiredMetricIds',[]):
            metric=self.data['metrics'][id]
            if metric['component']!=component or STAGES.index(metric['stage'])>=current:continue
            observation=candidate['observations'].get(id)
            if not observation or not same_identity(observation.get('identity',{}),self.session.identity):continue
            result=observation.get('result',{})
            missing=result.get('reasonCode')=='component_unbound' and not candidate.get('bindings',{}).get(component)
            if result.get('status')=='failed' or (result.get('status')=='incomplete' and missing):failed.append(id)
        if not failed:return None
        return {'candidateId':candidate_id,'component':component,'fromStage':self.data['stage'],
                'stage':min((self.data['metrics'][id]['stage'] for id in failed),key=STAGES.index),
                'metricIds':sorted(failed),'identity':self.session.identity,
                'reason':'Correct current measured failures or the explicitly checked missing component; unrelated components remain protected.'}

    def apply(self,candidate_id,plan,*,intent_id=None,bind=None,hypothesis=None,correction=None):
        self._contract()
        payload=plan.to_dict()
        intent_payload={k:payload[k] for k in ('operations','objects','writablePartIds','frame') if k in payload}
        if correction is not None:intent_payload['correction']=correction
        intent_hash=hashlib.sha256(canonical_json(intent_payload)).hexdigest()
        if intent_id is not None:
            label(intent_id,'edit intent id')
            original=next((e for c in self.data['candidates'].values() for e in c['executions'] if e.get('intentId')==intent_id),None)
            if original is not None:
                if original.get('intentHash')!=intent_hash or original.get('candidateId')!=candidate_id:
                    raise ModelingError('intent_conflict','This intent already identifies another edit. Query its original execution; a deliberate new edit requires a new intent ID.')
                return self.resume_edit(intent_id)
        if self._reference_changes():raise ModelingError('reference_changed','Reference content changed; review targets before another write')
        candidate=self.data['candidates'][candidate_id]
        if self.session.client.instance['instanceId']!=self.data['instanceId']:raise ModelingError('instance_conflict','Task belongs to another native instance; review the external state')
        if self.data['stop'] is not None:raise ModelingError('task_stopped','This run has stopped; start a new reviewed evaluation')
        stage=self.data['stage']
        if correction is not None:
            if not isinstance(correction,dict) or not correction.get('component'):
                raise ModelingError('invalid_correction','Use the unchanged correction_review returned for this candidate/component')
            reviewed=self.correction_review(candidate_id,correction['component'])
            if reviewed is None or correction!=reviewed:
                raise ModelingError('correction_changed','The measured correction scope/stage/identity changed; inspect and preview again')
            owned={part['id'] for part in candidate.get('bindings',{}).get(correction['component'],[])}
            if not set(payload.get('writablePartIds',[])).issubset(owned):
                raise ModelingError('correction_scope','Correction may only write its reviewed component')
            if payload['objects'] and (not isinstance(bind,dict) or set(bind)!={correction['component']} or set(bind[correction['component']])!=set(payload['objects'])):
                raise ModelingError('correction_scope','Every newly constructed correction part must bind to the reviewed component')
            stage=correction['stage']
        missing=self._stage_missing(candidate,STAGES.index(stage)-1)
        if missing:raise ModelingError('stage_blocked','Required earlier-stage features are not currently verified',{'metricIds':missing})
        operations=len(payload['operations'])
        used=sum(e['operationCount'] for c in self.data['candidates'].values() for e in c['executions'])
        if used+operations>self.data['budget']['nativeOperations']:raise ModelingError('modeling_budget','Native operation budget exhausted')
        if len(payload['objects'])>candidate['partBudget']:raise ModelingError('modeling_budget','Candidate exceeds its frozen native part budget')
        observer=getattr(self.session,'_on_execution_prepared',None)
        if observer is not None:raise ModelingError('workflow_active','Nested task executions are not supported')
        if bind is not None and (not isinstance(bind,dict) or any(c not in candidate['components'] or not isinstance(names,list) or not names or any(not isinstance(n,str) or n not in payload['objects'] for n in names) for c,names in bind.items())):
            raise ModelingError('invalid_binding','Auto-bind maps registered components to newly planned object names.')
        if intent_id and len(self.data['iterations'])>=self.data['budget']['iterations']:
            raise ModelingError('modeling_budget','Iteration budget exhausted before write')
        execution={'state':'previewing','operationCount':operations,'plan':payload,'journalPath':None,
                   'candidateId':candidate_id,'intentId':intent_id,'intentHash':intent_hash,
                   'autoBind':deepcopy(bind or {}),'hypothesis':hypothesis,'nativeState':'not_submitted','postprocessingState':'pending',
                   'correction':deepcopy(correction)}
        with self._edit():
            candidate['executions'].append(execution)
            if correction is not None:
                self.data['stage']=stage
                self.data.setdefault('stageCorrections',[]).append({**deepcopy(correction),'intentId':intent_id})
        def prepared(path):
            with self._edit():execution.update(journalPath=str(path),state='prepared')
        try:
            preview=plan.preview();self.session._on_execution_prepared=prepared
            receipt=plan.apply(preview.token)
        except Exception as error:
            record=Journal.read(execution['journalPath']) if execution.get('journalPath') else {}
            committed=record.get('state')=='succeeded'
            unknown=record.get('state') in ('prepared','submitted','outcome_unknown')
            public=error.to_dict() if isinstance(error,ModelingError) else {'code':'postprocessing_error','message':str(error)}
            with self._edit():execution.update(state='committed' if committed else 'outcome_unknown' if unknown else 'failed',
                nativeState='committed' if committed else 'outcome_unknown' if unknown else 'not_committed',postprocessingState='failed',error=public)
            raise
        finally:self.session._on_execution_prepared=observer
        with self._edit():execution.update(state='committed',nativeState='committed',receipt=receipt.to_dict());candidate['state']='awaiting_measurement'
        self._finish_edit(execution,receipt)
        return receipt

    def _finish_edit(self,execution,receipt):
        """Only postprocessing. Durable original journals own all native writes."""
        candidate=self.data['candidates'][execution['candidateId']]
        try:
            for component,names in execution.get('autoBind',{}).items():
                if any(name not in receipt.objects for name in names):
                    raise ModelingError('stale_reference','Edit committed but current native bindings are unavailable; inspect current state before explicit reconciliation',{'intentId':execution.get('intentId'),'journalPath':execution['journalPath']})
                self.bind(execution['candidateId'],component,[receipt.objects[name] for name in names])
            with self._edit():
                execution.update(state='succeeded',nativeState='committed',postprocessingState='completed',receipt=receipt.to_dict())
                execution.pop('error',None)
                if execution.get('intentId') and not any(i.get('intentId')==execution['intentId'] for i in self.data['iterations']):
                    self.data['iterations'].append({'candidateId':execution['candidateId'],'intentId':execution['intentId'],
                        'residualKind':'parameters','hypothesis':execution.get('hypothesis') or 'Explicit reviewed semantic edit',
                        'parameterGroup':list(execution.get('autoBind',{})),'cost':{'nativeOperations':execution['operationCount']},
                        'beforeObservations':deepcopy(candidate['observations']),
                        'beforeIdentity':deepcopy(execution['plan'].get('baselineIdentity')),
                        'executionIdentity':deepcopy(receipt.identity),'observations':{},'measuredMetricIds':[],
                        'state':'awaiting_measurement'})
                if execution.get('intentId') and self.data['stage']=='reference':self.data['stage']='proportions'
        except Exception as error:
            with self._edit():execution.update(state='committed',nativeState='committed',postprocessingState='failed',
                error=error.to_dict() if isinstance(error,ModelingError) else {'code':'postprocessing_error','message':str(error)})
            raise

    def resume_edit(self,intent_id):
        """Query one original intent and finish binding; never submit another batch."""
        self.reload()
        execution=next((e for c in self.data['candidates'].values() for e in c['executions'] if e.get('intentId')==intent_id),None)
        if execution is None:raise ModelingError('intent_not_found','No execution exists for this intent ID')
        if not execution.get('journalPath'):raise ModelingError('no_submission_evidence','No request was linked. Inspect the failed preview; do not replay under this intent ID.',{'intentId':intent_id})
        receipt=self.session.resume(execution['journalPath'])
        self._finish_edit(execution,receipt)
        return receipt

    def resume(self):
        """Reload metadata and query linked original requests; never write the craft."""
        self.reload();self.session.inspect()
        if self.session.client.instance['instanceId']!=self.data['instanceId']:
            raise ModelingError('instance_conflict','Task belongs to another native process; reconcile its evidence explicitly')
        pending=[]
        for id,candidate in self.data['candidates'].items():
            for index,execution in enumerate(candidate['executions']):
                if execution['state'] in ('previewing','prepared','outcome_unknown','committed'):
                    if not execution['journalPath']:pending.append({'candidateId':id,'index':index,'status':'no_submission_evidence'});continue
                    try:
                        receipt=self.session.resume(execution['journalPath'])
                        if execution.get('candidateId'):self._finish_edit(execution,receipt)
                        else:
                            with self._edit():execution.update(state='succeeded',receipt=receipt.to_dict())
                    except ModelingError as error:
                        record=Journal.read(execution['journalPath'])
                        if record['state']=='failed':
                            with self._edit():execution.update(state='failed',error=error.to_dict())
                        else:pending.append({'candidateId':id,'index':index,'error':error.to_dict()})
        for index,event in enumerate(self.data.get('lifecycle',[])):
            if event['state'] not in ('preparing','prepared','outcome_unknown'):continue
            if not event.get('journalPath'):
                pending.append({'lifecycleIndex':index,'status':'no_submission_evidence'});continue
            try:
                result=self.session.resume(event['journalPath'])
                with self._edit():
                    event.update(state='succeeded',result=result)
                    if event['action']=='keep_best' and event.get('bestAnchor'):
                        self.data['best']={**deepcopy(event['bestAnchor']),'checkpoint':deepcopy(result)}
            except ModelingError as error:
                record=Journal.read(event['journalPath'])
                if record['state']=='failed':
                    with self._edit():event.update(state='failed',error=error.to_dict())
                else:pending.append({'lifecycleIndex':index,'error':error.to_dict()})
        return {**self.report(),'pendingExecutions':pending,'bindings':self.session.bindings(),
                'contextRetention':'External contract and execution evidence were reloaded; this does not assert prompt retention, comprehension or compliance.'}

    def _lifecycle(self,action,operation,*,metadata=None):
        """Link the native journal before POST, including controls and checkpoints."""
        self._contract()
        if self.session.client.instance['instanceId']!=self.data['instanceId']:
            raise ModelingError('instance_conflict','Task belongs to another native instance')
        pending=[i for i,e in enumerate(self.data.get('lifecycle',[])) if e['state'] in ('preparing','prepared','outcome_unknown')]
        if pending:raise ModelingError('pending_execution','Call task.resume() to query the original lifecycle request first',{'lifecycleIndices':pending})
        observer=getattr(self.session,'_on_native_prepared',None)
        if observer is not None:raise ModelingError('workflow_active','Nested native lifecycle operations are not supported')
        event={'action':action,'state':'preparing','journalPath':None,'baselineIdentity':self.session.identity,**deepcopy(metadata or {})}
        with self._edit():self.data.setdefault('lifecycle',[]).append(event)
        def prepared(path):
            with self._edit():event.update(state='prepared',journalPath=str(path))
        try:
            self.session._on_native_prepared=prepared
            value=operation()
        except ModelingError as error:
            # A successful native request followed by a readback/reporting error
            # still needs original-journal reconciliation, not another POST.
            state='outcome_unknown' if event['journalPath'] else 'failed'
            with self._edit():event.update(state=state,error=error.to_dict())
            raise
        finally:self.session._on_native_prepared=observer
        result=value.last_control if hasattr(value,'last_control') else value
        with self._edit():event.update(state='succeeded',result=deepcopy(result))
        return value

    def parts(self,candidate_id,component):
        """Current bound members only. This never matches historical IDs by name."""
        bindings=self.data['candidates'][candidate_id].get('bindings',{}).get(component,[])
        if not bindings:raise ModelingError('component_coverage','Bind this semantic component before checking it')
        rows={p['id']:p for p in self.session._snapshot['parts']}
        if any(p.get('identity',self.data['initialIdentity']).get('craftSessionId')!=self.session.identity['craftSessionId'] or p['id'] not in rows or not p.get('lifetimeId') or rows[p['id']].get('lifetimeId')!=p['lifetimeId'] for p in bindings):
            raise ModelingError('stale_reference','Component lifetime changed; explicitly task.rebind or bind reviewed current members')
        self._evidence_fresh(self.session.identity)
        return tuple(self.session._part(rows[p['id']],self.session.identity) for p in bindings)

    def rebind(self,candidate_id,*,mapping=None,accept_native_endpoint_roundtrip=False,from_best=False):
        """Explicit project reconciliation followed by atomic task member binding."""
        self._contract();candidate=self.data['candidates'][candidate_id]
        if self.session.client.instance['instanceId']!=self.data['instanceId']:raise ModelingError('instance_conflict','Cannot rebind a task to another process implicitly')
        bindings=candidate.get('bindings',{})
        if any(not bindings.get(c) for c in candidate['components']):raise ModelingError('component_coverage','Every candidate component needs its original explicit binding')
        ids={p.get('logicalId') for values in bindings.values() for p in values}
        if None in ids:raise ModelingError('project_required','Automatic evidence reconciliation needs project logical IDs; explicitly bind reviewed native members instead')
        if type(from_best) is not bool:raise ModelingError('invalid_input','from_best must be boolean')
        if from_best:
            best=self.data.get('best',{});proof=best.get('projectEvidence',{})
            restore=next((e for e in reversed(self.data.get('lifecycle',[])) if e['action']=='restore' and e['state']=='succeeded'),{})
            result=restore.get('result',{});review=self.data.get('restoreReviews',{}).get(restore.get('reviewToken'),{})
            self.session.inspect()
            if (best.get('candidateId')!=candidate_id or not self.session.project or best.get('projectId')!=self.session.project.id or
                not ids.issubset(proof) or review.get('checkpoint',{}).get('id')!=best.get('checkpoint',{}).get('id') or
                result.get('restoration',{}).get('restorationStatus')!='exact' or not same_identity(result.get('identity',{}),self.session.identity)):
                raise ModelingError('checkpoint_binding_review_required','from_best needs this candidate/project, an exact reviewed restore of its checkpoint and unchanged current native identity')
            native_mapping=None if mapping is None else {key:self.session._resolve_ref(part) for key,part in mapping.items()}
            selected=self.session.project.rebind(self.session._snapshot,self.session.client.instance['instanceId'],logical_ids=sorted(ids),mapping=native_mapping,
                accept_native_endpoint_roundtrip=accept_native_endpoint_roundtrip,_evidence_objects={id:proof[id] for id in ids})
            self.session._fresh(self.session.identity)
            current={p['id']:p for p in self.session._snapshot['parts']}
            refs={id:self.session._part(current[native_id],self.session.identity) for id,native_id in selected.items()}
        else:refs=self.session.rebind(sorted(ids),mapping=mapping,accept_native_endpoint_roundtrip=accept_native_endpoint_roundtrip)
        rows={p['id']:p for p in self.session._snapshot['parts']}
        updated={component:[{'id':refs[p['logicalId']].id,'logicalId':p['logicalId'],'lifetimeId':rows[refs[p['logicalId']].id].get('lifetimeId'),'type':refs[p['logicalId']].type,'identity':self.session.identity} for p in values] for component,values in bindings.items()}
        with self._edit():
            candidate['bindings']=updated
            self.data.setdefault('bindingReviews',[]).append({'candidateId':candidate_id,'identity':self.session.identity,'fromBest':from_best,'bindings':deepcopy(updated)})
        return refs

    def check(self,candidate_id,*,metric_ids=None):
        """Fresh native captures, shared per component/frame. No plan or craft writes."""
        self._contract();candidate=self.data['candidates'][candidate_id]
        selected=[id for id in self.data['requiredMetricIds'] if self.data['metrics'][id]['component'] in candidate['components']] if metric_ids is None else list(metric_ids)
        if len(selected)!=len(set(selected)) or any(id not in self.data['metrics'] or self.data['metrics'][id]['component'] not in candidate['components'] for id in selected):
            raise ModelingError('invalid_metric','Choose distinct registered metrics represented by this candidate')
        if getattr(self,'_check_identity',None) is not None:raise ModelingError('workflow_active','Nested check batches are not supported')
        self.session.inspect();baseline=self.session.identity;cache={};members={};results={}
        def parts_for(component):
            if component not in members:members[component]=self.parts(candidate_id,component)
            return members[component]
        def mesh_for(component,frame):
            key=(component,canonical_json(frame))
            if key not in cache:
                value=Frame.world() if frame['kind']=='world' else Frame.custom(frame['position'],frame['rotationQuaternion'])
                cache[key]=self.session.mesh(parts_for(component),frame=value)
            return cache[key]
        self._check_identity=baseline
        self._reference_mesh_cache={}
        try:
            for id in selected:
                metric=self.data['metrics'][id];kind=metric['kind'];component=metric['component']
                if kind=='reference_geometry':
                    if not candidate.get('bindings',{}).get(component):
                        results[id]={'status':'incomplete','reasonCode':'component_unbound','reason':'Component has not been constructed and bound'}
                        with self._edit():
                            candidate['observations'][id]={'identity':self.session.identity,'evidence':{'source':'current_task_binding_check'},'result':deepcopy(results[id]),'partProof':{}}
                            self._update_reference_iteration(candidate_id,id)
                        continue
                    results[id]=self.measure_reference(candidate_id,id)['result'];continue
                if kind=='pose':
                    parts=parts_for(component)
                    if len(parts)!=1:results[id]={'status':'not_assessed','reason':'Choose an explicit pose anchor with measure_pose for a multi-part component'};continue
                    results[id]=self.measure_pose(candidate_id,id,parts[0])['result'];continue
                if kind=='seam' and metric['expected'].get('otherComponent') in candidate['components']:
                    results[id]=self.measure_seam(candidate_id,id,mesh_for(component,metric['frame']),mesh_for(metric['expected']['otherComponent'],metric['frame']))['result'];continue
                if kind not in ('mesh_extent','section_contour','point_probe','surface'):
                    results[id]={'status':'not_assessed','reason':'Use the explicit seam, visual or dynamic evaluator; this helper cannot certify it'};continue
                results[id]=self.measure(candidate_id,id,mesh_for(component,metric['frame']))['result']
            self.session._fresh(baseline)
        finally:
            reference_capture_count=len(self._reference_mesh_cache)
            self._reference_mesh_cache=None
            self._check_identity=None
            # On a failed end fence expose the actual new revision; all stored
            # old-identity observations then remain historical/incomplete.
            self.session.inspect()
        return {'report':self.report(),'results':results,'nativeCaptureCount':len(cache)+reference_capture_count}

    def measure_reference(self,candidate_id,metric_id):
        """Capture current native component meshes against a frozen target contract."""
        from .model_compare import compare_model
        self._contract()
        if self._reference_changes():raise ModelingError('reference_changed','Reference content changed; review original targets')
        metric=self.data['metrics'][metric_id]
        if metric['kind']!='reference_geometry':raise ModelingError('invalid_metric','Choose a reference_geometry metric')
        candidate=self.data['candidates'][candidate_id]
        required={metric['component']}
        for target in metric['expected']['targets']['targets']:
            if target.get('kind')=='relative_pose' and target.get('expected',{}).get('otherComponent'):
                required.add(target['expected']['otherComponent'])
        bindings={name:self.parts(candidate_id,name) for name in required if candidate.get('bindings',{}).get(name)}
        if metric['component'] not in bindings:raise ModelingError('component_coverage','Bind this component before comparison')
        frame=metric['frame'];offset=self.data.get('frameTranslationMetres',[0,0,0])
        native_frame=Frame.custom([a+b for a,b in zip(frame.get('position',[0,0,0]),offset)],frame.get('rotationQuaternion',[0,0,0,1]))
        reference=metric['expected']['reference']
        for source in reference.get('source',{}).get('files',[]):
            path=Path(source['path'])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
                raise ModelingError('reference_changed','Original source file changed after freezing',{'path':str(path)})
        cache=getattr(self,'_reference_mesh_cache',None)
        if cache is None:cache={}
        meshes={}
        for name,parts in bindings.items():
            key=(name,canonical_json(native_frame.to_dict()))
            if key not in cache:cache[key]=self.session.mesh(parts,frame=native_frame)
            mesh=cache[key]
            if {m['partId'] for m in mesh.meshes}!={p.id for p in parts}:
                raise ModelingError('component_coverage','Native capture omitted or added component members')
            if not mesh._artifact_verified or not same_identity(mesh.identity,self.session.identity):
                raise ModelingError('stale_evidence','Capture is unverified or belongs to a different native identity')
            if mesh.frame.to_dict()!=native_frame.to_dict():raise ModelingError('frame_mismatch','Native capture ignored requested common frame')
            meshes[name]=mesh
        result=compare_model(reference,metric['expected']['targets'],{'frameId':reference['frameId'],'components':meshes,'identity':self.session.identity},candidate_id=candidate_id)
        self._evidence_fresh(self.session.identity)
        ids={p.id for parts in bindings.values() for p in parts}
        proof={str(row['id']):{key:row.get(key) for key in ('partFingerprint','lifetimeId')} for row in self.session._snapshot['parts'] if row['id'] in ids}
        observation={'identity':self.session.identity,'evidence':{'source':'verified_native_reference_comparison','frame':native_frame.to_dict()},'result':result,'partProof':proof}
        with self._edit():
            candidate['observations'][metric_id]=observation
            self._update_reference_iteration(candidate_id,metric_id)
        return deepcopy(observation)

    def _comparison_snapshot(self,candidate_id,observations,identity,*,changed=()):
        """A fixed feature denominator for progress, including missing evidence."""
        results=[];residuals=[];changed=set(changed)
        for metric_id in self.data.get('requiredMetricIds',[]):
            metric=self.data['metrics'][metric_id];observation=observations.get(metric_id,{})
            measurement=observation.get('result',{})
            fresh=bool(identity) and same_identity(observation.get('identity',{}),identity) and metric['referenceId'] not in changed
            if metric['kind']=='reference_geometry':
                actual={row.get('targetId'):row for row in measurement.get('results',[])}
                for target in metric['expected']['targets']['targets']:
                    if not target['required']:continue
                    row=deepcopy(actual.get(target['id'],{}))
                    row.update(targetId=metric_id+'/'+target['id'],featureId=metric_id+'/'+target['featureId'],
                        metricId=metric_id,required=True,component=metric['component'],priority=target.get('priority','P0'),
                        viewId=target.get('viewId'),toleranceMetres=target['toleranceMetres'])
                    if not fresh or not actual.get(target['id']):
                        row.update(status='incomplete',reason='No current complete feature measurement at this observation identity')
                    results.append(row)
                for residual in measurement.get('residuals',[]):
                    residual=deepcopy(residual);residual['metricId']=metric_id
                    residual['featureId']=metric_id+'/'+residual['featureId'];residuals.append(residual)
            else:
                row=deepcopy(measurement)
                row.update(targetId=metric_id,featureId=metric_id,metricId=metric_id,required=True,
                           component=metric['component'],priority='P0',toleranceMetres=metric['toleranceMetres'])
                if not fresh:row['status']='incomplete'
                row.setdefault('status','incomplete');results.append(row)
        for row in results:
            if row['status']!='passed' and not any(r['featureId']==row['featureId'] for r in residuals):
                residuals.append({'featureId':row['featureId'],'metricId':row['metricId'],'component':row['component'],
                    'status':row['status'],'priority':row['priority'],'nextAction':'Check this required feature; missing evidence is not a shape pass.'})
        status='failed' if any(row['status']=='failed' for row in results) else 'passed' if results and all(row['status']=='passed' for row in results) else 'incomplete'
        return {'referenceId':'task:'+self.data['taskId'],'referenceVersion':self.data.get('contractHash'),
                'referenceContentHash':self.data.get('contractHash'),'frameId':'task-contract:'+str(self.data.get('contractHash')),
                'targetHash':self.data.get('contractHash'),'candidateId':candidate_id,'identity':deepcopy(identity),
                'status':status,'results':results,'residuals':residuals}

    def _update_reference_iteration(self,candidate_id,metric_id):
        """Called under _edit: rechecks update one edit, never invent iterations."""
        from .model_compare import compare_progress
        iteration=next((row for row in reversed(self.data['iterations']) if row.get('candidateId')==candidate_id and row.get('intentId')),None)
        if iteration is None:return
        # Save/reopen or an external edit cannot rewrite the original iteration.
        expected=iteration.get('executionIdentity')
        if expected and not same_identity(expected,self.session.identity):return
        candidate=self.data['candidates'][candidate_id]
        measured=set(iteration.get('measuredMetricIds',[]));measured.add(metric_id)
        iteration.update(observations=deepcopy(candidate['observations']),measurementIdentity=self.session.identity,
                         measuredMetricIds=sorted(measured))
        required=[id for id in self.data.get('requiredMetricIds',[]) if self.data['metrics'][id]['kind']=='reference_geometry' and self.data['metrics'][id]['component'] in candidate['components']]
        complete=bool(required) and all(id in measured and same_identity(candidate['observations'].get(id,{}).get('identity',{}),self.session.identity) for id in required)
        iteration['state']='measured' if complete else 'partially_measured'
        before=iteration.get('beforeObservations',{})
        before_identity=iteration.get('beforeIdentity') or next((obs.get('identity') for obs in before.values()),None)
        previous=self._comparison_snapshot(candidate_id,before,before_identity) if before else None
        current=self._comparison_snapshot(candidate_id,candidate['observations'],self.session.identity)
        iteration['progress']=compare_progress(previous,current,minimum_improvement_m=self.data['budget']['minimumImprovementMetres'])

    def progress(self,candidate_id,*,stagnation_window=3):
        """Public read-only progress and stopping advice; never creates recovery."""
        self._contract()
        if candidate_id not in self.data['candidates']:raise ModelingError('candidate_not_found','Choose an existing candidate')
        changed={item['id'] for item in self._reference_changes()}
        return self._progress(candidate_id,changed,stagnation_window=stagnation_window)

    def _progress(self,candidate_id,changed,*,stagnation_window=3):
        from .model_compare import compare_progress,convergence_review
        candidate=self.data['candidates'][candidate_id];snapshots=[];indices=[]
        for index,iteration in enumerate(self.data['iterations']):
            if iteration.get('candidateId')!=candidate_id or iteration.get('state') in ('awaiting_measurement','partially_measured'):continue
            observations=iteration.get('observations',{})
            if not observations:continue
            identity=iteration.get('measurementIdentity') or next((obs.get('identity') for obs in observations.values()),None)
            snapshots.append(self._comparison_snapshot(candidate_id,observations,identity));indices.append(index)
        current=self._comparison_snapshot(candidate_id,candidate['observations'],self.session.identity,changed=changed)
        recorded=bool(snapshots) and same_identity(snapshots[-1].get('identity',{}),self.session.identity) and canonical_json(snapshots[-1]['results'])==canonical_json(current['results'])
        previous=snapshots[-2] if recorded and len(snapshots)>1 else None if recorded else snapshots[-1] if snapshots else None
        latest=compare_progress(previous,current,minimum_improvement_m=self.data['budget']['minimumImprovementMetres'])
        history=snapshots if recorded else snapshots+[current]
        if not recorded:indices.append(None)
        review=convergence_review(history,minimum_improvement_m=self.data['budget']['minimumImprovementMetres'],stagnation_window=stagnation_window)
        reason='within_tolerance' if current['status']=='passed' else 'measurement_invalid' if current['status']=='incomplete' else review['stopReason'] if recorded else None
        if changed:reason='scene_changed'
        used=sum(e['operationCount'] for c in self.data['candidates'].values() for e in c['executions'])
        if current['status']!='passed' and (len(self.data['iterations'])>=self.data['budget']['iterations'] or used>=self.data['budget']['nativeOperations']):reason='budget_exhausted'
        best_index=review.get('bestEvidenceIndex');best=None if best_index is None else {
            'candidateId':candidate_id,'iterationIndex':indices[best_index],'identity':review.get('bestEvidenceIdentity'),
            'status':history[best_index]['status'],'restoreAvailable':False,
            'meaning':'Measured geometry evidence only. It does not create a native checkpoint or a saved craft.'}
        retained=self.data.get('best');recovery=None
        if retained and retained.get('candidateId')==candidate_id:
            same_epoch=retained.get('identity',{}).get('craftSessionId')==self.session.identity.get('craftSessionId')
            recovery={'checkpointId':retained.get('checkpoint',{}).get('id'),'identity':deepcopy(retained.get('identity')),
                'availability':'requires_current_restore_preview' if same_epoch else 'expired_craft_epoch',
                'recoverable':False,'nextAction':'restore_preview' if same_epoch else 'Inspect an explicitly preserved native save; diagnostic evidence cannot be restored.'}
        return {'candidateId':candidate_id,'currentStatus':current['status'],'currentIdentity':self.session.identity,
                'latestComparison':latest,'recommendedStopReason':reason,'adviceOnly':True,
                'measuredIterationCount':len(snapshots),'stagnationWindow':stagnation_window,
                'bestEvidence':best,'retainedRecoveryCandidate':recovery,'nextFeatures':review.get('nextFeatures',[]),
                'meaning':'Advice does not stop or restore the task. All required metrics, including non-shape checks, remain delivery gates.'}

    def save(self,name,*,overwrite=False):
        return self._lifecycle('save',lambda:self.session.save(name,overwrite=overwrite))

    def deliver(self,candidate_id,name,*,delivery_id,overwrite=False,allow_incomplete=False):
        from .delivery import deliver_task
        return deliver_task(self,candidate_id,name,delivery_id,overwrite=overwrite,allow_incomplete=allow_incomplete)

    def reopen(self,craft_id,*,discard_current=False):
        """Return a task on a NEW Session; explicit rebind/check still required."""
        session=self._lifecycle('reopen',lambda:self.session.reopen(craft_id,discard_current=discard_current))
        return type(self)(session,self.path)

    def restore_preview(self):
        """Review the retained best checkpoint's whole-craft scope, never restore."""
        if not self.data.get('best'):raise ModelingError('checkpoint_required','Measure and keep_best in this native craft epoch first')
        if self.data['best']['identity']['craftSessionId']!=self.session.identity['craftSessionId']:
            raise ModelingError('session_conflict','Best checkpoint belongs to an earlier craft epoch; keep a new reviewed best after reopening')
        review=self.session.restore_preview(self.data['best']['checkpoint']['id'])
        with self._edit():self.data.setdefault('restoreReviews',{})[review['token']]=deepcopy(review)
        return review

    def restore(self,token,*,accept_whole_craft=False):
        """Apply an explicit current native review; never automatically roll back."""
        review=self.data.get('restoreReviews',{}).get(token)
        if accept_whole_craft is not True or review is None:raise ModelingError('restore_review_required','Use task.restore_preview and explicitly review its whole-craft scope')
        # Durable deduplication also survives a new Python task process.
        original=next((e for e in self.data.get('lifecycle',[]) if e['action']=='restore' and e.get('reviewToken')==token and e.get('journalPath')),None)
        if original is not None:
            result=self.session._restore_delivery(self.session.resume(original['journalPath']))
            with self._edit():original.update(state='succeeded',result=deepcopy(result))
            return result
        current=self.session.restore_preview(review['checkpoint']['id'])
        if current['token']!=token:raise ModelingError('revision_conflict','Saved whole-craft review changed; inspect a new preview before restoring')
        return self._lifecycle('restore',lambda:self.session.restore(token,accept_whole_craft=True),metadata={'reviewToken':token})

    def measure(self,candidate_id,metric_id,mesh):
        self._contract()
        if self._reference_changes():raise ModelingError('reference_changed','Reference content changed; old targets cannot certify current reconstruction')
        candidate=self.data['candidates'][candidate_id];metric=self.data['metrics'][metric_id]
        if metric['component'] not in candidate['components']:raise ModelingError('invalid_measurement','Candidate does not represent this semantic component')
        if not isinstance(mesh,MeshEvidence) or not mesh._artifact_verified or not same_identity(mesh.identity,self.session.identity):raise ModelingError('stale_evidence','Use a current SHA256-verified native MeshEvidence from session.mesh')
        self._evidence_fresh(mesh.identity)
        bindings=candidate.get('bindings',{}).get(metric['component'],[])
        mesh_ids={m['partId'] for m in mesh.meshes};rows={p['id']:p for p in self.session._snapshot['parts']}
        if not bindings or mesh_ids!={p['id'] for p in bindings}:raise ModelingError('component_coverage','Bind the current semantic component and capture exactly its required native members')
        if any(p['id'] not in rows or not p['lifetimeId'] or rows[p['id']].get('lifetimeId')!=p['lifetimeId'] for p in bindings):raise ModelingError('stale_reference','Component binding lifetime changed; inspect and explicitly bind current members')
        if mesh.frame.to_dict()!=metric['frame']:raise ModelingError('frame_mismatch','Metric and measured mesh must use the same declared frame')
        kind=metric['kind'];expected=metric['expected'];tolerance=metric['toleranceMetres']
        points=[p for m in mesh.meshes for p in m['vertices']]
        result={'status':'incomplete','reason':'Required mesh evidence is empty'}
        if points and kind=='hard_face':
            result=mesh.planar_face_region(0,**expected,tolerance_m=tolerance) if len(mesh.meshes)==1 else {'status':'incomplete','reason':'Hard-face metric requires one explicit rendered mesh; bind the face owner separately'}
        elif points and kind=='mesh_extent':
            projections=[dot(p,expected['axis']) for p in points];actual=max(projections)-min(projections);error=abs(actual-expected['valueMetres'])
            result={'status':'passed' if error<=tolerance else 'failed','actualMetres':actual,'errorMetres':error,'coverage':'Native captured vertex extent only; no complete profile/surface inference'}
        elif points and kind=='section_contour':
            section=mesh.section(expected['origin'],expected['normal']);intersecting=[p for p in section['parts'] if p['segments']]
            if len(intersecting)!=1 or not intersecting[0]['closed']:
                result={'status':'incomplete','reason':'Required section is open, missing or requires an explicit inter-part union','section':section}
            else:result=compare_contours(expected['segments'],intersecting[0]['segments'],tolerance_m=tolerance,sample_spacing_m=max(tolerance/4,1e-6))
        elif points and kind=='point_probe':
            from .verification import point_inside,closed_mesh
            triangles=[tuple(m['vertices'][m['indices'][i+j]] for j in range(3)) for m in mesh.meshes for i in range(0,len(m['indices']),3)]
            if closed_mesh(triangles):
                actual=point_inside(triangles,expected['point']);result={'status':'incomplete' if actual is None else 'passed' if actual==expected['inside'] else 'failed','actualInside':actual,'coverage':'Captured closed indexed surface and one explicit probe'}
            else:result={'status':'incomplete','reason':'Closed-surface evidence required for occupancy probe'}
        elif points and kind=='surface':
            if len({m['partId'] for m in mesh.meshes})!=1:
                result={'status':'incomplete','reason':'Full native component surface needs an explicit exterior or union policy for multiple parts; internal overlapping surfaces cannot silently stand in for the exterior'}
            else:
                actual=[tuple(m['vertices'][m['indices'][i+j]] for j in range(3)) for m in mesh.meshes for i in range(0,len(m['indices']),3)]
                result=compare_surfaces(expected['triangles'],actual,tolerance_m=tolerance,max_samples=expected['max_samples'],max_triangle_tests=expected['max_triangle_tests'])
        elif points:result={'status':'not_assessed','reason':'This metric needs its declared pose, visual, seam or dynamic evaluator; mesh extent cannot stand in for it'}
        ids={m['partId'] for m in mesh.meshes}
        proof={str(row['id']):{key:row.get(key) for key in ('partFingerprint','lifetimeId')} for row in self.session._snapshot['parts'] if row['id'] in ids}
        observation={'identity':deepcopy(mesh.identity),'evidence':mesh.to_dict(),'result':result,'partProof':proof}
        with self._edit():candidate['observations'][metric_id]=observation
        return deepcopy(observation)

    def measure_pose(self,candidate_id,metric_id,anchor):
        self._contract()
        if self._reference_changes():raise ModelingError('reference_changed','Reference changed; review this target')
        self.session._resolve_ref(anchor);self._evidence_fresh(self.session.identity)
        candidate=self.data['candidates'][candidate_id];metric=self.data['metrics'][metric_id]
        actual=next(p for p in self.session._snapshot['parts'] if p['id']==anchor.id)
        if metric['kind']!='pose' or not any(p['id']==anchor.id and p['lifetimeId']==actual.get('lifetimeId') for p in candidate.get('bindings',{}).get(metric['component'],[])):raise ModelingError('component_coverage','Bind this current pose anchor to the metric component')
        frame=metric['frame'];frame=Frame.world() if frame['kind']=='world' else Frame.custom(frame['position'],frame['rotationQuaternion'])
        expected=metric['expected'];checks=[]
        if 'positionMetres' in expected:
            error=magnitude(sub(actual['position'],frame.point(expected['positionMetres'])))
            checks.append({'kind':'position','errorMetres':error,'toleranceMetres':metric['toleranceMetres'],'status':'passed' if error<=metric['toleranceMetres'] else 'failed'})
        if 'rotationQuaternion' in expected:
            error=rotation_distance_degrees(actual['rotationQuaternion'],frame.orientation(expected['rotationQuaternion']))
            checks.append({'kind':'rotation','errorDegrees':error,'toleranceDegrees':expected['toleranceDegrees'],'status':'passed' if error<=expected['toleranceDegrees'] else 'failed'})
        result={'status':'passed' if checks and all(c['status']=='passed' for c in checks) else 'failed','checks':checks,'coverage':'One explicit native component anchor pose; no geometry or group rigidity inference'}
        observation={'identity':self.session.identity,'evidence':{'source':'current_native_part_snapshot_pose','partId':anchor.id,'position':actual['position'],'rotationQuaternion':actual['rotationQuaternion']},'result':result,'partProof':{}}
        with self._edit():candidate['observations'][metric_id]=observation
        return deepcopy(observation)

    def measure_seam(self,candidate_id,metric_id,left,right):
        self._contract()
        if self._reference_changes():raise ModelingError('reference_changed','Reference changed; review this interface')
        candidate=self.data['candidates'][candidate_id];metric=self.data['metrics'][metric_id]
        if metric['kind']!='seam' or any(not isinstance(mesh,MeshEvidence) or not mesh._artifact_verified or not same_identity(mesh.identity,self.session.identity) or mesh.frame.to_dict()!=metric['frame'] for mesh in (left,right)):raise ModelingError('stale_evidence','Use two current verified native meshes in the declared interface frame')
        self._evidence_fresh(self.session.identity)
        if {m['partId'] for m in left.meshes}&{m['partId'] for m in right.meshes}:raise ModelingError('invalid_interface','Interface sides must be distinct native members, not a mesh compared to itself')
        ids={m['partId'] for mesh in (left,right) for m in mesh.meshes};bindings=candidate.get('bindings',{}).get(metric['component'],[])
        other=metric['expected'].get('otherComponent')
        if other is not None:
            second=candidate.get('bindings',{}).get(other,[])
            if {m['partId'] for m in left.meshes}!={p['id'] for p in bindings} or {m['partId'] for m in right.meshes}!={p['id'] for p in second}:
                raise ModelingError('component_coverage','Each declared interface side must exactly cover its separately bound semantic component')
            bindings=[*bindings,*second]
        elif ids!={p['id'] for p in bindings}:raise ModelingError('component_coverage','The interface pair must cover its bound native component members exactly; register other_component for separate components',
            {'boundMemberIds':sorted(p['id'] for p in bindings),'capturedMemberIds':sorted(ids),'hint':'A seam between separate semantic components declares other_component before freeze; do not add unrelated members to a frozen shape component to bypass coverage.'})
        rows={p['id']:p for p in self.session._snapshot['parts']}
        if any(p['id'] not in rows or rows[p['id']].get('lifetimeId')!=p['lifetimeId'] for p in bindings):raise ModelingError('stale_reference','Interface member lifetime changed; explicitly review and bind current members')
        expected=metric['expected'];sections=[mesh.section(expected['origin'],expected['normal']) for mesh in (left,right)]
        contours=[[p for p in section['parts'] if p['segments']] for section in sections]
        if any(len(parts)!=1 or not parts[0]['closed'] for parts in contours):result={'status':'incomplete','reason':'Each required interface side needs one complete native contour; missing/open sections or implicit unions cannot pass','sections':sections}
        else:result=compare_contours(contours[0][0]['segments'],contours[1][0]['segments'],tolerance_m=metric['toleranceMetres'],sample_spacing_m=max(metric['toleranceMetres']/4,1e-6))
        result['coverageMeaning']='Complete mutual interface profiles at the declared plane only; external-reference shape and installation pose require their own metrics.'
        observation={'identity':self.session.identity,'evidence':{'left':left.to_dict(),'right':right.to_dict()},'result':result,'partProof':{}}
        with self._edit():candidate['observations'][metric_id]=observation
        return deepcopy(observation)

    def _status(self,observation):
        if observation is None:return 'not_assessed'
        if not same_identity(observation['identity'],self.session.identity):
            # A cutter or host may change geometry without changing the target
            # part's XML. Exact part fingerprints alone cannot certify reuse.
            # Keep the evidence historically, but require a fresh measurement
            # until a complete native impact certificate is available.
            return 'incomplete'
        return observation['result']['status']

    def _stage_missing(self,candidate,index):
        changed={r['id'] for r in self._reference_changes()}
        return [id for id in self.data['requiredMetricIds'] if self.data['metrics'][id]['component'] in candidate['components'] and STAGES.index(self.data['metrics'][id]['stage'])<=index and
                (self.data['metrics'][id]['referenceId'] in changed or self._status(candidate['observations'].get(id))!='passed')]

    def advance(self,candidate_id,stage):
        if stage not in STAGES:raise ModelingError('invalid_stage','Unknown modeling stage')
        old=STAGES.index(self.data['stage']);new=STAGES.index(stage)
        if new!=old+1:raise ModelingError('invalid_stage','Advance one reviewable phase at a time')
        missing=self._stage_missing(self.data['candidates'][candidate_id],new-1)
        if missing:raise ModelingError('stage_blocked','Earlier required features are not verified',{'metricIds':missing})
        with self._edit():self.data['stage']=stage
        return self.report()

    def iteration(self,candidate_id,*,residual_kind,hypothesis,parameter_group,cost,reason=None):
        if residual_kind not in ('reference','measurement','parameters','representation','tool','scene'):raise ModelingError('invalid_iteration','Classify the residual before changing parameters')
        if len(self.data['iterations'])>=self.data['budget']['iterations']:raise ModelingError('modeling_budget','Iteration budget exhausted')
        if not hypothesis or not parameter_group or not isinstance(cost,dict):raise ModelingError('invalid_iteration','Record correction hypothesis, related parameter group and explicit cost')
        candidate=self.data['candidates'][candidate_id]
        prior=next((row for row in reversed(self.data['iterations']) if row.get('candidateId')==candidate_id and row.get('observations')),None)
        previous=prior['observations'] if prior else {}
        differences=[];regressions=[];threshold=self.data['budget']['minimumImprovementMetres']
        for id in self.data['requiredMetricIds']:
            before=previous.get(id,{}).get('result',{});after=candidate['observations'].get(id,{}).get('result',{})
            if before.get('status')=='passed' and after.get('status')!='passed':regressions.append(id)
            old=before.get('errorMetres',before.get('upperBoundMetres'));new=after.get('errorMetres',after.get('upperBoundMetres'))
            if old is not None and new is not None:differences.append({'metricId':id,'beforeMetres':old,'afterMetres':new,'improvementMetres':old-new,'significant':old-new>=threshold})
        diagnostic={'metricDifferences':differences,'regressedRequiredMetricIds':regressions,'minimumImprovementMetres':threshold,
                    'significantImprovement':bool(differences) and any(d['significant'] for d in differences) and not regressions,
                    'comparablePriorIteration':bool(previous),'meaning':'Target changes are separate evaluations; averages never override required-feature regressions.'}
        if any(self.data['metrics'][id]['kind']=='reference_geometry' for id in self.data.get('requiredMetricIds',[])):
            from .model_compare import compare_progress
            before_identity=(prior.get('measurementIdentity') if prior else None) or next((obs.get('identity') for obs in previous.values()),None)
            before=self._comparison_snapshot(candidate_id,previous,before_identity) if previous else None
            current=self._comparison_snapshot(candidate_id,candidate['observations'],self.session.identity)
            feature_progress=compare_progress(before,current,minimum_improvement_m=threshold)
            diagnostic.update(featureProgress=feature_progress,significantImprovement=feature_progress['significantImprovement'],
                              comparablePriorIteration=feature_progress['comparablePriorIteration'])
        with self._edit():self.data['iterations'].append({'candidateId':candidate_id,'residualKind':residual_kind,'hypothesis':hypothesis,'parameterGroup':parameter_group,'cost':deepcopy(cost),'reason':reason,
            'observations':deepcopy(candidate['observations']),'measurementIdentity':self.session.identity,'state':'measured','progress':diagnostic})
        return self.report()

    def retirement_plan(self,candidate_id,old_parts,*,writable):
        candidate=self.data['candidates'][candidate_id]
        missing=self._stage_missing(candidate,len(STAGES)-1)
        if missing:raise ModelingError('retirement_blocked','All required replacement features must pass before old representation is retired',{'metricIds':missing})
        parts=list(old_parts)
        if not parts:raise ModelingError('invalid_selector','Choose explicit current old objects')
        replacement_ids={p['id'] for bindings in candidate.get('bindings',{}).values() for p in bindings}
        if any(p.id in replacement_ids for p in parts):raise ModelingError('retirement_blocked','Verified replacement members cannot be retired as the old representation')
        for part in parts:self.session._resolve_ref(part)
        plan=self.session.plan(writable=writable)
        for part in parts:plan.delete(part)
        return plan

    def keep_best(self,candidate_id):
        candidate=self.data['candidates'][candidate_id]
        self._contract()
        if self._reference_changes():raise ModelingError('reference_changed','Cannot retain a best candidate against changed reference content')
        if not candidate['observations']:raise ModelingError('candidate_unmeasured','Measure the candidate before retaining it')
        self.session._fresh(self.session.identity)
        if any(not same_identity(obs['identity'],self.session.identity) for obs in candidate['observations'].values()):
            raise ModelingError('stale_evidence','Remeasure this candidate at the current native identity before retaining a best anchor')
        previous=self.data.get('best')
        current={id:self._status(obs) for id,obs in candidate['observations'].items()}
        if previous:
            regressions=[id for id,obs in previous['observations'].items() if obs['result']['status']=='passed' and current.get(id)!='passed']
            if regressions:raise ModelingError('candidate_regressed','Previously passed required features cannot be traded for an average improvement',{'metricIds':regressions})
        ids={p.get('logicalId') for values in candidate.get('bindings',{}).values() for p in values}
        evidence={} if not self.session.project else {id:item for id,item in self.session.project.objects.items() if id in ids}
        anchor={'candidateId':candidate_id,'observations':deepcopy(candidate['observations']),'parameters':deepcopy(candidate['parameters']),
                'identity':self.session.identity,'projectId':None if not self.session.project else self.session.project.id,'projectEvidence':evidence,
                'scopeMeaning':'Whole native craft checkpoint. Restoring it requires separate current whole-craft review and does not grant permission over concurrent changes.'}
        checkpoint=self._lifecycle('keep_best',lambda:self.session.checkpoint('model-task-best-'+self.data['taskId'][:8]+'-'+candidate_id,pinned=True),metadata={'candidateId':candidate_id,'bestAnchor':anchor})
        with self._edit():self.data['best']={**anchor,'checkpoint':checkpoint}
        return deepcopy(self.data['best'])

    def stop(self,reason,*,details):
        if reason not in STOP_REASONS:raise ModelingError('invalid_stop_reason','Use a declared modeling stop reason')
        if reason=='within_tolerance':self.session._fresh(self.session.identity)
        if reason=='within_tolerance' and not any(c['allRequiredPassed'] for c in self.report()['candidates'].values()):raise ModelingError('completion_blocked','Required metrics remain incomplete or failed')
        with self._edit():self.data['stop']={'reason':reason,'details':details};self.data['state']='complete' if reason=='within_tolerance' else 'stopped'
        return self.report()

    def report(self):
        self._contract();reference_changes=self._reference_changes();changed={r['id'] for r in reference_changes}
        required=self.data.get('requiredMetricIds',[]);candidates={}
        for id,c in self.data['candidates'].items():
            statuses={m:'incomplete' if self.data['metrics'][m]['referenceId'] in changed else self._status(c['observations'].get(m)) for m in required if self.data['metrics'][m]['component'] in c['components']}
            candidates[id]={'metrics':statuses,'passed':sum(v=='passed' for v in statuses.values()),'representedRequiredCount':len(statuses),
                            'allRequiredPassed':len(statuses)==len(required) and bool(required) and all(v=='passed' for v in statuses.values()),
                            'progress':self._progress(id,changed)}
        best=max(candidates,key=lambda id:candidates[id]['passed']) if candidates else None
        missing=[id for id in required if best is None or candidates[best]['metrics'].get(id)!='passed']
        current_state='needs_review' if self.data['state']=='complete' and missing else self.data['state']
        pending_lifecycle=[{'index':i,'action':e['action'],'state':e['state'],'journalPath':e.get('journalPath')} for i,e in enumerate(self.data.get('lifecycle',[])) if e['state'] in ('preparing','prepared','outcome_unknown')]
        return {'taskPath':str(self.path),'taskId':self.data['taskId'],'state':current_state,'recordedState':self.data['state'],'stage':self.data['stage'],'contractFrozen':self.data['frozen'],
                'budget':deepcopy(self.data['budget']),'usage':{'candidates':len(self.data['candidates']),'iterations':len(self.data['iterations']),'nativeOperations':sum(e['operationCount'] for c in self.data['candidates'].values() for e in c['executions'])},
                'requiredMetricCount':len(required),'candidates':candidates,'bestCandidateId':best,
                'bestCandidateMeaning':'Current metric coverage ranking only; inspect candidates[id].progress.bestEvidence separately from retainedRecoveryCandidate.',
                'remainingMetricIds':missing,'stop':deepcopy(self.data['stop']),
                'pendingLifecycle':pending_lifecycle,'lifecycle':deepcopy(self.data.get('lifecycle',[])),
                'nextChecks':[{'id':id,'kind':self.data['metrics'][id]['kind'],'stage':self.data['metrics'][id]['stage']} for id in missing],
                'identity':self.session.identity,'referenceChanges':reference_changes,'limitations':'Native geometric metrics, declared visual review, dynamic function and user aesthetics are separate. No arbitrary-reference convergence or permanent context guarantee.'}
