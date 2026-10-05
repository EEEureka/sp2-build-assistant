using System;
using System.Linq;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private int rebuildCount;
        private static bool MergeableRaw(JObject op)
        {
            if((string)op["kind"]!="part.update"||op.Value<bool?>("symmetric")==true||!(op["changes"] is JArray changes)||changes.Count==0)return false;
            return changes.All(t=>t is JObject && ((string)t["path"]=="Part"||t["path"]==null||((string)t["path"]).StartsWith("InputController.State")));
        }
        private async UniTask ApplyOperationSequence(JArray ops,BatchReferences refs,JArray changed)
        {
            for(int i=0;i<ops.Count;){
                // A transform is a postcondition of that operation. Settle and
                // verify it BEFORE a later native setter may legitimately move
                // a dependent wheel/control. Do not silently discard it or
                // demand its pose still hold after a later operation.
                if(requiredPoses.Count>0){
                    await ReadSettled(Current(),null);
                    ValidateRequiredPoses();
                    requiredPoses.Clear();
                }
                var op=(JObject)ops[i];int end=i;
                if(MergeableRaw(op))while(end<ops.Count&&MergeableRaw((JObject)ops[end]))end++;
                if(end-i<2){refs.OperationIndex=i;changed.Add(Apply(op,refs));AcceptanceFault("after_operation_"+i);i++;continue;}
                var xml=Current().Aircraft.Aircraft.GenerateXml(false);var staged=new JArray();
                for(int j=i;j<end;j++){
                    var item=(JObject)ops[j];int id=refs.Resolve(item["partId"]);var p=Part(id);var element=XmlPart(xml,id);
                    ApplyRawChanges(p,element,(JArray)item["changes"]);
                    // A later explicit pose supersedes the postcondition from an
                    // earlier transform, also when this data segment is merged.
                    if(((JArray)item["changes"]).Any(c=>((string)c["path"]=="Part"||c["path"]==null)&&new[]{"position","rotation"}.Contains((string)c["attribute"])))requiredPoses.Remove(id);
                    staged.Add(new JObject{["kind"]="part.update",["partId"]=id,["editMode"]="adjacent_data_edits_one_rebuild",["segmentStartOperationIndex"]=i,["segmentEndOperationIndex"]=end-1});
                }
                Replace(xml);foreach(JObject row in staged)changed.Add(row);refs.OperationIndex=end-1;refs.Observe(ReferenceParts());AcceptanceFault("after_operation_"+(end-1));i=end;
            }
        }
        private object PreviewEditPlan(JObject a)
        {
            Guard(a);CheckBatch(a);var reports=new JArray();bool earlier=false;
            foreach(JObject op in (JArray)a["operations"]){string kind=(string)op["kind"];var checks=new JArray("operation_kind","allowed_fields");var pending=new JArray("native_setter_callbacks","geometry","collision_picking","final_affected_fields");
                if(kind=="properties.set"){
                    if(!(op["patch"] is JObject patch)||patch.Count<1||patch.Count>100)throw new ApiError("invalid_input","properties.set.patch needs 1..100 entries.");
                    if(op["partId"]?.Type==JTokenType.Integer){var p=Part(Int(op,"partId"));var entries=PropertyRegistry.Entries(p).ToDictionary(e=>e.Id);
                        foreach(var field in patch.Properties()){PropertyEntry e;if(!entries.TryGetValue(field.Name,out e))throw new ApiError("property_not_found",field.Name);var value=NativePropertyAdapter.Validate(e,field.Value);if(!earlier)NativePropertyAdapter.ValidateConditions(e,value);}
                        checks.Add("known_property_ids");checks.Add("typed_values_and_static_limits");checks.Add("resource_ids");if(!earlier)checks.Add("current_native_conditions");else pending.Add("conditions_after_prior_operations");
                    }else pending.Add("temporary_id_resolution");
                }
                if(kind=="part.update"&&op["partId"]?.Type==JTokenType.Integer&&!earlier){var p=Part(Int(op,"partId"));var candidate=p.GenerateXml();ApplyRawChanges(p,candidate,op["changes"] as JArray??throw new ApiError("invalid_input","changes needs an array."));checks.Add("native_metadata_and_current_path");checks.Add("expression_compile_if_applicable");}
                if(kind=="part.add"){FindTemplate(Required(op,"templateId"));checks.Add("template_exists");}
                JToken impacts=null;
                if(kind=="appearance.set"&&!earlier){impacts=AppearanceSet(op,true);checks.Add("material_slots_resources_values_and_current_users");}
                if(kind=="properties.set"&&op["partId"]?.Type==JTokenType.Integer&&!earlier){var p=Part(Int(op,"partId"));impacts=new JObject{["partIds"]=new JArray(new[]{p.Id}.Concat(SymmetricTargets(p,op.Value<bool?>("symmetric")??true).Select(x=>x.Id)).Distinct()),["scope"]="native_modifier_peers; target carvers may also affect referenced surface geometry"};}
                reports.Add(new JObject{["operationIndex"]=reports.Count,["kind"]=kind,["checked"]=checks,["predictedImpact"]=impacts,["pendingNativeValidation"]=pending,["mergeableDataEdit"]=MergeableRaw(op)});earlier=true;
            }
            return new {identity=Identity(),validationLevel="static_and_current_state_where_independent",validated="request_and_available_metadata",operationCount=reports.Count,operations=reports,
                sideEffects=false,reservesRevision=false,warnings=new[]{"Preview is not an isolated native geometry simulation. Subsequent-operation dynamic conditions and actual impacts are verified during apply; a legal preview can still fail atomically."}};
        }
    }
}
