using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.EventSystems;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private sealed class ScopedYieldSignal : Exception
        {
            internal readonly string Reason;
            internal ScopedYieldSignal(string reason) : base(reason) { Reason=reason; }
        }
        private sealed class ScopeLease
        {
            internal string Id,Session,Owner,ActiveJob;
            internal long Revision;
            internal int[] Boundaries;
            internal double Margin;
            internal ScopeState State;
            internal Dictionary<int,PartData> Bindings;
        }
        private sealed class ScopedRun
        {
            internal ScopeLease Lease;
            internal JArray Operations,Chunks=new JArray();
            internal int Cursor,ChunkSize;
            internal double MaxSliceMs,LastSliceMs;
            internal readonly Stopwatch Clock=Stopwatch.StartNew();
        }
        private readonly Dictionary<string,ScopeLease> scopeLeases=new Dictionary<string,ScopeLease>();
        private readonly Dictionary<string,ScopedRun> scopedRuns=new Dictionary<string,ScopedRun>();
        private readonly FrameDiagnostics frameDiagnostics=new FrameDiagnostics();
        private int inputWindowUntilFrame;

        private JObject SchedulingCapability()
        {
            return new JObject{["scopedCommands"]=new JArray("scope.capture","scope.get","scope.release","scoped.batch.apply"),
                ["policy"]="FIFO cooperative chunks; one native writer at a time; unrelated scope revisions may advance after exact content validation.",
                ["defaultChunkSize"]=1,["maximumChunkSize"]=4,["minimumInputFramesBetweenChunks"]=1,
                ["legacyBatch"]="batch.apply/undo/rollback remain strict whole-revision atomic operations. Their native rebuild boundary is not preemptible.",
                ["scopedFailure"]="Completed chunks remain committed. Only the currently executing atomic chunk can recover its own before-state; no automatic whole-job rollback.",
                ["nativeBoundary"]="Native setters, rebuild, geometry settlement, cache refresh and history commit are atomic per chunk; rendering continues across waits but designer mutation input is paused during that boundary. Synchronous native work cannot be preempted.",
                ["scopeLimitations"]=new JArray("In-place edits only; topology/add/delete and palette clone/shared edits require legacy strict batches.","Caller must declare non-near expected shared boundaries; spatial bounds add conservative guard candidates, not proof of contact.","Global craft/variable/theme/symmetry state is guarded conservatively; shared-state changes require scope recapture."),
                ["frames"]=frameDiagnostics.View()};
        }
        private int[] SpatialScopeCandidates(IEnumerable<int> ids,double margin)
        {
            var all=Current().Aircraft.Aircraft.Assembly.Parts;
            var source=new HashSet<int>(ids);var boxes=new List<Bounds>();
            foreach(var p in all.Where(p=>source.Contains(p.Id)))foreach(var r in p.PartScript.GetComponentsInChildren<Renderer>(true))if(r!=null){var b=r.bounds;b.Expand((float)(margin*2));boxes.Add(b);}
            return all.Where(p=>!source.Contains(p.Id)&&p.PartScript.GetComponentsInChildren<Renderer>(true).Any(r=>r!=null&&boxes.Any(b=>b.Intersects(r.bounds)))).Select(p=>p.Id).ToArray();
        }
        private ScopeState CaptureNativeScope(XElement xml,int[] writes,int[] boundaries,double margin)
        {
            var candidates=new HashSet<int>(boundaries.Concat(SpatialScopeCandidates(writes,margin)));var write=new HashSet<int>(writes);
            var native=new JArray();var verifiedTargeting=new List<int>();
            var all=Current().Aircraft.Aircraft.Assembly.Parts.ToArray();
            var boxes=all.ToDictionary(p=>p.Id,p=>ScopePartBounds(p));
            bool writeBoundsComplete=writes.All(id=>boxes[id].Count>0);
            foreach(var p in all){
                var targeting=p.GetModifier<PartTargetingData>();
                if(targeting==null||targeting.TargetMode!=PartTargetingMode.MultipleParts)continue;
                Bounds volume;
                if(!writeBoundsComplete||!TryNativeTargetingBounds(p,out volume))continue; // pure model conservatively guards all
                verifiedTargeting.Add(p.Id);volume.Expand((float)(margin*2));
                var relevant=new HashSet<int>(writes.Concat(candidates));
                var currentTargets=targeting.PartIDs??new List<int>();
                if(!relevant.Contains(p.Id)&&!currentTargets.Any(relevant.Contains)&&!relevant.Any(id=>boxes.ContainsKey(id)&&boxes[id].Any(b=>b.Intersects(volume))))continue;
                candidates.Add(p.Id);foreach(int id in currentTargets)candidates.Add(id);
                foreach(var pair in boxes)if(pair.Value.Any(b=>b.Intersects(volume)))candidates.Add(pair.Key);
                native.Add(new JObject{["kind"]="dynamic_targeting_native_volume",["partId"]=p.Id,["targetMode"]="MultipleParts",["currentTargetPartIds"]=new JArray(currentTargets),["boundsMin"]=new JArray(Vec(volume.min)),["boundsMax"]=new JArray(Vec(volume.max)),["meaning"]="Current handler target cache plus conservative native volume candidates; refreshed before and after each chunk, not a fixed custom whitelist."});
            }
            foreach(var p in Current().Aircraft.Aircraft.Assembly.Parts){var host=NativeHost(p);if(host.HasValue&&(write.Contains(p.Id)||write.Contains(host.Value))){candidates.Add(p.Id);candidates.Add(host.Value);native.Add(new JObject{["kind"]="native_derived_transform",["partId"]=p.Id,["hostPartId"]=host.Value});}}
            var state=ScopeState.Capture(xml,writes,candidates,verifiedTargeting);
            foreach(int id in candidates.Except(boundaries).Except(writes))state.Relations.Add(new JObject{["kind"]="conservative_native_or_spatial_guard",["partId"]=id,["contactProven"]=false});
            foreach(var row in native)state.Relations.Add(row);return state;
        }
        private List<Bounds> ScopePartBounds(PartData part)
        {
            var boxes=part.PartScript.GetComponentsInChildren<Renderer>(true).Where(r=>r!=null).Select(r=>r.bounds).ToList();
            boxes.AddRange(part.PartScript.GetComponentsInChildren<Collider>(true).Where(c=>c!=null).Select(c=>c.bounds));
            Bounds targeting;if(part.GetModifier<PartTargetingData>()!=null&&TryNativeTargetingBounds(part,out targeting))boxes.Add(targeting);
            return boxes.Where(b=>Finite(b.center)&&Finite(b.extents)&&b.extents.sqrMagnitude>1e-14f).ToList();
        }
        private static bool Finite(Vector3 value){return !float.IsNaN(value.x)&&!float.IsInfinity(value.x)&&!float.IsNaN(value.y)&&!float.IsInfinity(value.y)&&!float.IsNaN(value.z)&&!float.IsInfinity(value.z);}
        private bool TryNativeTargetingBounds(PartData part,out Bounds result)
        {
            result=default(Bounds);
            try{
                var handler=part.PartScript.GetModifier<PartTargetingScript>()?.Handler;
                if(handler==null)return false;
                var receiver=PrivateField(handler,"_intersectionReceiver");if(receiver==null)return false;
                var method=receiver.GetType().GetMethod("GetBox",BindingFlags.Instance|BindingFlags.Public);if(method==null)return false;
                var box=(ValueTuple<Vector3,Vector3,Quaternion>)method.Invoke(receiver,null);
                var q=box.Item3;var half=box.Item2;
                var x=q*Vector3.right;var y=q*Vector3.up;var z=q*Vector3.forward;
                var extents=new Vector3(Math.Abs(x.x*half.x)+Math.Abs(y.x*half.y)+Math.Abs(z.x*half.z),Math.Abs(x.y*half.x)+Math.Abs(y.y*half.y)+Math.Abs(z.y*half.z),Math.Abs(x.z*half.x)+Math.Abs(y.z*half.y)+Math.Abs(z.z*half.z));
                if(!Finite(box.Item1)||!Finite(extents)||extents.sqrMagnitude<1e-14f)return false;
                result=new Bounds(box.Item1,extents*2);return true;
            }catch(Exception){return false;}
        }
        private Dictionary<int,PartData> ScopeBindings(ScopeState state){return state.GuardIds.ToDictionary(id=>id,id=>Part(id));}
        private JObject ScopeView(ScopeLease lease)
        {
            return new JObject{["identity"]=JToken.FromObject(Identity()),["scopeId"]=lease.Id,["ownerId"]=lease.Owner,
                ["capturedRevision"]=lease.Revision,["writePartIds"]=new JArray(lease.State.WriteIds),["guardPartIds"]=new JArray(lease.State.GuardIds),
                ["boundaryPartIds"]=new JArray(lease.Boundaries),["relations"]=lease.State.Relations.DeepClone(),
                ["partFingerprints"]=JObject.FromObject(lease.State.PartHashes),["sharedStateFingerprint"]=lease.State.SharedHash,
                ["activeOperationId"]=lease.ActiveJob,["spatialMarginMetres"]=lease.Margin,
                ["meaning"]="A content guard, not an exclusive reservation. Numeric IDs bind captured native objects; known internal rebuilds rebind unchanged parts only. Any scoped content/dependency conflict stops the next chunk."};
        }
        private object ScopeRead(string command,JObject args)
        {
            Observe();
            if(command=="scope.capture"){
                Guard(args);var writes=PartIds(args["partIds"]);var boundaries=args["boundaryPartIds"]==null?new int[0]:PartIds(args["boundaryPartIds"]);
                double margin=args.Value<double?>("spatialMarginMetres")??.02;
                if(double.IsNaN(margin)||double.IsInfinity(margin)||margin<0||margin>10)throw new ApiError("invalid_input","spatialMarginMetres must be finite in 0..10.");
                if(scopeLeases.Count>=128)throw new ApiError("scope_capacity","Release unused scopes before capturing more.");
                var lease=new ScopeLease{Id=Guid.NewGuid().ToString("N"),Session=session,Owner=(string)args["ownerId"]??"anonymous",Revision=revision,Boundaries=boundaries,Margin=margin};
                lease.State=CaptureNativeScope(Current().Aircraft.Aircraft.GenerateXml(false),writes,boundaries,margin);lease.Bindings=ScopeBindings(lease.State);scopeLeases.Add(lease.Id,lease);return ScopeView(lease);
            }
            var id=Required(args,"scopeId");ScopeLease found;
            if(!scopeLeases.TryGetValue(id,out found)||found.Session!=session)throw new ApiError("scope_not_found","Scope is unavailable in this designer session.");
            if(args["craftSessionId"]!=null&&(string)args["craftSessionId"]!=session)throw new ApiError("session_conflict","The current open aircraft changed.");
            if(command=="scope.release"){
                if(found.ActiveJob!=null)throw new ApiError("scope_busy","Cancel and wait for the active job before releasing its scope.");
                scopeLeases.Remove(id);return new{scopeId=id,released=true,identity=Identity()};
            }
            var view=ScopeView(found);try{ValidateScopeLease(found,Current().Aircraft.Aircraft.GenerateXml(false));view["valid"]=true;}catch(ApiError e){view["valid"]=false;view["conflict"]=Json.Fail(e)["error"];}return view;
        }
        private void ValidateScopeLease(ScopeLease lease,XElement xml)
        {
            if(uncertain)throw new ApiError("state_uncertain","Inspect and recover the designer before continuing scoped edits.");
            if(lease.Session!=session)throw new ApiError("session_conflict","The current open aircraft changed.");
            lease.State.Validate(xml);
            var rebound=lease.Bindings.Where(pair=>Current().Aircraft.Aircraft.Assembly.GetPartById(pair.Key)!=pair.Value).Select(pair=>pair.Key).ToArray();
            if(rebound.Length>0)throw new ApiError("scope_object_conflict","Native object continuity changed outside a verified internal rebuild; recapture the scope.",new JObject{["partIds"]=new JArray(rebound)});
            var fresh=CaptureNativeScope(xml,lease.State.WriteIds,lease.Boundaries,lease.Margin);
            if(!fresh.GuardIds.SequenceEqual(lease.State.GuardIds))throw new ApiError("scope_dependency_conflict","Native or spatial dependency candidates changed; review and recapture the scope.",new JObject{["capturedGuardPartIds"]=new JArray(lease.State.GuardIds),["currentGuardPartIds"]=new JArray(fresh.GuardIds)});
        }
        private void ValidateScopedOperation(ScopeLease lease,JObject op)
        {
            var targets=ScopeState.OperationTargets(op);var write=new HashSet<int>(lease.State.WriteIds);var guards=new HashSet<int>(lease.State.GuardIds);
            if(targets.Any(id=>!write.Contains(id)))throw new ApiError("scope_violation","Operation targets a part outside writePartIds.");
            bool defaultSymmetry=new[]{"shape.update","properties.set"}.Contains((string)op["kind"]);
            bool symmetric=op.Value<bool?>("symmetric")??defaultSymmetry;
            foreach(int id in targets)if(SymmetricTargets(Part(id),symmetric).Any(p=>!write.Contains(p.Id)))throw new ApiError("scope_violation","Native symmetric propagation leaves writePartIds. Include peers or explicitly use symmetric:false.");
            foreach(string field in new[]{"targetPartId","sourcePartId","anchorPartId"})if(op[field]!=null&&(op[field].Type!=JTokenType.Integer||!guards.Contains((int)op[field])))throw new ApiError("scope_violation","Referenced alignment/anchor part must belong to the guarded scope.");
        }
        // Called only after a verified internal native rebuild. Other leases
        // keep their old content guards, and cannot accept changed target state.
        private void RebindUnchangedScopes(XElement before,XElement after)
        {
            var a=ScopeState.Parts(before);var b=ScopeState.Parts(after);
            foreach(var lease in scopeLeases.Values.Where(l=>l.Session==session))foreach(int id in lease.State.GuardIds){
                if(a.ContainsKey(id)&&b.ContainsKey(id)&&lease.State.PartHashes[id]==SnapshotState.Fingerprint(a[id])&&lease.State.PartHashes[id]==SnapshotState.Fingerprint(b[id]))lease.Bindings[id]=Part(id);
            }
        }
        private JObject ScopedReceipt(ScopedRun run,Job job,bool completed)
        {
            return new JObject{["identity"]=JToken.FromObject(Identity()),["operationId"]=job.Id,["scopeId"]=run.Lease.Id,["ownerId"]=run.Lease.Owner,
                ["completed"]=completed,["completedOperationCount"]=run.Cursor,["operationCount"]=run.Operations.Count,["chunks"]=run.Chunks.DeepClone(),
                ["actualChanges"]=new JArray(run.Chunks.SelectMany(c=>(JArray)c["result"]?["data"]?["actualChanges"]??new JArray())),
                ["rollbackPolicy"]="completed_chunks_preserved; current_chunk_only_atomic_recovery",["lastSliceMs"]=run.LastSliceMs,["maxSliceMs"]=run.MaxSliceMs,
                ["elapsedMs"]=run.Clock.Elapsed.TotalMilliseconds,["sliceTimingMeaning"]="Atomic chunk wall time includes awaited native settlement. It is not a continuous main-thread CPU stall or measured input latency.",
                ["frameDiagnostics"]=frameDiagnostics.View(),["verificationLevel"]="native_readback_and_scope_isolation; no_visual_or_user_aesthetic_acceptance"};
        }
        private async UniTask<JObject> ScopedBatchStep(JObject args,Job job)
        {
            Observe();ScopedRun run;
            if(!scopedRuns.TryGetValue(job.Id,out run)){
                if(string.IsNullOrEmpty(job.Key))throw new ApiError("request_id_required","Writes require an outer requestId for retry safety.");
                if(Required(args,"craftSessionId")!=session)throw new ApiError("session_conflict","The current open aircraft changed.");
                ScopeLease lease;if(!scopeLeases.TryGetValue(Required(args,"scopeId"),out lease))throw new ApiError("scope_not_found","Capture a fresh content scope first.");
                if(lease.ActiveJob!=null&&lease.ActiveJob!=job.Id)throw new ApiError("scope_busy","This scope already has a running job.");
                CheckBatch(args);ValidateScopeLease(lease,Current().Aircraft.Aircraft.GenerateXml(false));
                int chunk=args.Value<int?>("chunkSize")??1;if(chunk<1||chunk>4)throw new ApiError("invalid_input","chunkSize must be in 1..4.");
                foreach(JObject op in (JArray)args["operations"])ValidateScopedOperation(lease,op);
                run=new ScopedRun{Lease=lease,Operations=(JArray)args["operations"].DeepClone(),ChunkSize=chunk};scopedRuns.Add(job.Id,run);lease.ActiveJob=job.Id;
            }
            try {
                lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Cancelled between atomic chunks; completed chunks remain committed.");
                var before=Observe();ValidateScopeLease(run.Lease,before);
                var chunkOps=new JArray(run.Operations.Skip(run.Cursor).Take(run.ChunkSize).Select(x=>x.DeepClone()));foreach(JObject op in chunkOps)ValidateScopedOperation(run.Lease,op);
                var strict=new JObject{["craftSessionId"]=session,["expectedRevision"]=revision,["operations"]=chunkOps};
                int startFrame=Time.frameCount;var slice=Stopwatch.StartNew();
                var response=await Mutate("batch.apply",strict,job,after=>{
                    run.Lease.State.ValidateOutsideUnchanged(before,after);
                    var fresh=CaptureNativeScope(after,run.Lease.State.WriteIds,run.Lease.Boundaries,run.Lease.Margin);
                    if(fresh.GuardIds.Except(run.Lease.State.GuardIds).Any())throw new ApiError("scope_escape","The edit introduced a new dependency outside the captured scope; include its boundary and retry.",new JObject{["newGuardPartIds"]=new JArray(fresh.GuardIds.Except(run.Lease.State.GuardIds))});
                });
                run.LastSliceMs=slice.Elapsed.TotalMilliseconds;run.MaxSliceMs=Math.Max(run.MaxSliceMs,run.LastSliceMs);
                run.Chunks.Add(new JObject{["index"]=run.Chunks.Count,["startOperationIndex"]=run.Cursor,["operationCount"]=chunkOps.Count,["startFrame"]=startFrame,["endFrame"]=Time.frameCount,["elapsedMs"]=run.LastSliceMs,["result"]=response});
                if(!response.Value<bool>("success")){
                    response["scopedProgress"]=ScopedReceipt(run,job,false);FinishScoped(run,job);return response;
                }
                run.Cursor+=chunkOps.Count;
                var afterXml=Observe();
                // Keep pre-edit boundary dependencies as well as current ones.
                run.Lease.Boundaries=run.Lease.Boundaries.Concat(run.Lease.State.GuardIds.Except(run.Lease.State.WriteIds)).Distinct().OrderBy(x=>x).ToArray();
                run.Lease.State=CaptureNativeScope(afterXml,run.Lease.State.WriteIds,run.Lease.Boundaries,run.Lease.Margin);run.Lease.Bindings=ScopeBindings(run.Lease.State);run.Lease.Revision=revision;
                JobDiagnostics.Update(job.Id,new JObject{["mode"]="cooperative_scoped_chunks",["scopeId"]=run.Lease.Id,["ownerId"]=run.Lease.Owner,["completedOperationCount"]=run.Cursor,["operationCount"]=run.Operations.Count,["completedChunks"]=run.Chunks.Count,["lastSliceMs"]=run.LastSliceMs,["maxSliceMs"]=run.MaxSliceMs,["lastChunkEndFrame"]=Time.frameCount,
                    ["pluginInputGateOpenBetweenChunks"]=!Writing&&!AcceptanceInputBlocked&&(EventSystem.current==null||EventSystem.current.enabled),
                    ["nativeAllowKeyboardInputs"]=Assets.Scripts.Game.Instance.UserInterface.AllowKeyboardInputs,
                    ["nativeAnyDialogsOpen"]=Assets.Scripts.Game.Instance.UserInterface.AnyDialogsOpen,
                    ["nativeTextInputFocused"]=Assets.Scripts.Game.Instance.UserInterface.IsTextInputFocused,
                    ["inputDiagnosticMeaning"]="Plugin gate restoration and native UI permission are separate samples. Neither alone proves an actual user input event was processed.",
                    ["frameDiagnostics"]=frameDiagnostics.View()});
                if(run.Cursor==run.Operations.Count){var done=Json.Ok(ScopedReceipt(run,job,true));FinishScoped(run,job);return done;}
                inputWindowUntilFrame=Math.Max(inputWindowUntilFrame,Time.frameCount+1);return null;
            }catch(ScopedYieldSignal yielded){
                JobDiagnostics.Update(job.Id,new JObject{["waitingForUserInteraction"]=true,["pauseReason"]=yielded.Reason,
                    ["interactiveScheduling"]=InteractiveSchedulingView(),["yieldedBeforeAtomicEntry"]=true});
                return null;
            }catch(Exception e){var failure=Json.Fail(e);failure["scopedProgress"]=ScopedReceipt(run,job,false);FinishScoped(run,job);return failure;}
        }
        private void FinishScoped(ScopedRun run,Job job){run.Lease.ActiveJob=null;scopedRuns.Remove(job.Id);}
    }
}

