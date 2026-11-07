using System;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private readonly RecoveryLeases recoveryLeases=new RecoveryLeases();
        internal void ReserveRecoveryLease(Job job)
        {
            var args=job.Input?["args"] as JObject;
            if((string)job.Input?["command"]=="craft.rollback"&&args?["checkpointId"]?.Type==JTokenType.String)recoveryLeases.Reserve(job.Id,(string)args["checkpointId"]);
        }
        private System.Collections.Generic.HashSet<string> QueuedCheckpointTargets()
        {
            return recoveryLeases.Snapshot();
        }
        private JObject CheckpointCapacity()
        {
            var protectedTargets=QueuedCheckpointTargets();
            return new JObject{["count"]=checkpoints.Count,["maximum"]=64,["automaticEviction"]="oldest_unpinned_automatic_or_named; pinned and active recovery targets retained",
                ["reclaimableIds"]=new JArray(checkpointInfo.Where(p=>!protectedTargets.Contains(p.Key)&&JObject.FromObject(p.Value).Value<bool?>("pinned")==false).OrderBy(p=>(string)JObject.FromObject(p.Value)["createdAt"]).Select(p=>p.Key)),
                ["queuedRecoveryTargetIds"]=new JArray(protectedTargets),["sessionBound"]=true,["persistentAcrossRestart"]=false};
        }
        private void MakeCheckpointRoom(string active=null)
        {
            lock(recoveryLeases.Gate)while(checkpoints.Count>=64){
                var queued=QueuedCheckpointTargets();
                var candidate=checkpointInfo.Where(p=>p.Key!=active&&!queued.Contains(p.Key)&&JObject.FromObject(p.Value).Value<bool?>("pinned")==false)
                    .OrderBy(p=>(string)JObject.FromObject(p.Value)["createdAt"]).FirstOrDefault();
                if(candidate.Key==null)throw new ApiError("checkpoint_capacity","All 64 recovery anchors are pinned or in use. Observe original recoveries or explicitly prune an eligible milestone.",CheckpointCapacity());
                checkpoints.Remove(candidate.Key);checkpointInfo.Remove(candidate.Key);
            }
        }
        private JObject AddCheckpoint(string id,string name,XElement xml,long sourceRevision,string sourceHash,string kind,bool pinned,string sourceOperation,string active=null)
        {
            MakeCheckpointRoom(active);
            checkpoints.Add(id,new XElement(xml));
            var info=new JObject{["id"]=id,["name"]=name,["craftSessionId"]=session,["revision"]=sourceRevision,["fingerprint"]=sourceHash,["createdAt"]=DateTime.UtcNow.ToString("o"),["kind"]=kind,["pinned"]=pinned,["sourceOperationId"]=sourceOperation,["recoverable"]=true,["partCount"]=xml.Element("Assembly")?.Element("Parts")?.Elements("Part").Count()??0};
            checkpointInfo[id]=info;
            return info;
        }
        private JObject CheckpointPrune(JObject args)
        {
            lock(recoveryLeases.Gate){
            Guard(args);
            var ids=args["ids"] as JArray;
            if(ids==null||ids.Count==0||ids.Any(x=>x.Type!=JTokenType.String)||ids.Values<string>().Distinct().Count()!=ids.Count)throw new ApiError("invalid_input","Explicit unique checkpoint ids required.");
            var queued=QueuedCheckpointTargets();
            foreach(string id in ids.Values<string>()){
                if(queued.Contains(id))throw new ApiError("checkpoint_in_use","A queued recovery uses this checkpoint; observe or cancel that original operation before pruning.");
                if(!checkpointInfo.ContainsKey(id))throw new ApiError("checkpoint_not_found",id);
                if(JObject.FromObject(checkpointInfo[id]).Value<bool?>("pinned")!=false&&args.Value<bool?>("includePinned")!=true)throw new ApiError("checkpoint_pinned","Deleting a pinned milestone requires explicit includePinned:true.");
            }
            if(ids.Count>=checkpoints.Count)throw new ApiError("recovery_anchor_required","Retain at least one recovery anchor.");
            foreach(string id in ids.Values<string>()){checkpoints.Remove(id);checkpointInfo.Remove(id);}
            return new JObject{["identity"]=JToken.FromObject(Identity()),["deletedIds"]=ids.DeepClone(),["capacity"]=CheckpointCapacity()};
            }
        }
        private static JObject RestorationReport(XElement target,XElement current)
        {
            if(target==null||current==null)return new JObject{["restorationStatus"]="unverified",["fingerprintIdentical"]=null};
            string expected=SnapshotState.Fingerprint(target),actual=SnapshotState.Fingerprint(current);
            bool same=expected==actual,equivalent=SnapshotState.EquivalentAfterNativeRestore(target,current);
            var fields=CraftDiff.Compare(target,current,1000);
            return new JObject{["restorationStatus"]=same?((int)fields["totalChanges"]==0?"exact":"declared_native_differences"):equivalent?"tolerance_equivalent":"different",
                ["fingerprintIdentical"]=same,["serializedFieldsIdentical"]=(int)fields["totalChanges"]==0,["targetFingerprint"]=expected,["currentFingerprint"]=actual,
                ["restoreEulerToleranceDegrees"]=SnapshotState.RestoreEulerToleranceDegrees,["remainingFields"]=fields,
                ["meaning"]="Fingerprint equality follows its declared cache normalization; strict serialized equality and tolerance-based recovery are reported separately. Project bindings are not implied."};
        }
    }
}
