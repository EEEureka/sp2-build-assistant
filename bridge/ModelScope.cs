using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // SDK batches may create parts, but native callbacks must not silently
    // modify existing objects or topology outside the declared write set.
    internal sealed class ModelScope
    {
        private readonly XElement before;
        private readonly HashSet<int> writable;
        private readonly Dictionary<int,XElement> parts;
        private readonly bool paletteAppend;
        private readonly HashSet<int> writableMaterials;
        private readonly XElement paletteBefore;
        private readonly HashSet<string> writableVariables;
        private System.Collections.Generic.List<string> variableOrder;
        internal const string Version = "sp2model.scope/1";
        internal ModelScope(XElement baseline,JObject scope,XElement nativePalette=null)
        {
            if(scope==null||scope["version"]?.Type!=JTokenType.String||(string)scope["version"]!=Version)throw new ApiError("invalid_model_scope","Expected sp2model.scope/1.");
            if(scope.Properties().Any(p=>p.Name!="version"&&p.Name!="writablePartIds"&&p.Name!="paletteAppend"&&p.Name!="variableNames"&&p.Name!="writableMaterialIds"))throw new ApiError("invalid_model_scope","Unknown model scope field.");
            if(scope["paletteAppend"]!=null&&scope["paletteAppend"].Type!=JTokenType.Boolean)throw new ApiError("invalid_model_scope","paletteAppend must be an explicit boolean.");
            paletteAppend=scope.Value<bool?>("paletteAppend")??false;
            paletteBefore=new XElement(nativePalette??baseline.Element("Theme")??new XElement("Theme"));
            var materialIds=scope["writableMaterialIds"] as JArray;
            int parsedMaterial;
            if(scope["writableMaterialIds"]!=null&&(materialIds==null||materialIds.Count>50||materialIds.Any(x=>!TryPartId(x,out parsedMaterial))))throw new ApiError("invalid_model_scope","writableMaterialIds must explicitly list existing nonnegative local palette IDs.");
            writableMaterials=new HashSet<int>(materialIds==null?Enumerable.Empty<int>():materialIds.Values<int>());
            var existingMaterialIds=NativeMaterialIds(paletteBefore.Elements("Material").ToArray());
            if(writableMaterials.Any(id=>!existingMaterialIds.Contains(id)))throw new ApiError("invalid_model_scope","A writable material no longer exists.");
            var ids=scope["writablePartIds"] as JArray;
            int parsed;
            if(ids==null||ids.Count>2048||ids.Any(x=>!TryPartId(x,out parsed)))throw new ApiError("invalid_model_scope","Explicit existing numeric writablePartIds are required; [] allows creation only.");
            before=new XElement(baseline);parts=ScopeState.Parts(before);writable=new HashSet<int>(ids.Values<int>());
            var variableNames=scope["variableNames"] as JArray;
            if(scope["variableNames"]!=null&&(variableNames==null||variableNames.Count>512||variableNames.Any(x=>x.Type!=JTokenType.String||string.IsNullOrWhiteSpace((string)x))))throw new ApiError("invalid_model_scope","variableNames must explicitly list reviewed native Setter names.");
            writableVariables=new HashSet<string>(variableNames==null?Enumerable.Empty<string>():variableNames.Values<string>(),StringComparer.Ordinal);
            variableOrder=(before.Element("Variables")?.Elements("Setter")??Enumerable.Empty<XElement>()).Select(e=>(string)e.Attribute("variable")).ToList();
            if(writable.Any(id=>!parts.ContainsKey(id)))throw new ApiError("invalid_model_scope","A writable part no longer exists.");
        }
        private static bool TryPartId(JToken token,out int id)
        {
            id=0;
            // JSON integers may be BigInteger values. Parsing into the native
            // range avoids overflow exceptions escaping the public API error.
            return token!=null&&token.Type==JTokenType.Integer
                &&int.TryParse(token.ToString(Newtonsoft.Json.Formatting.None),NumberStyles.Integer,CultureInfo.InvariantCulture,out id)&&id>=0;
        }
        private static int[] NativeMaterialIds(XElement[] materials)
        {
            // ThemeData assigns IDs to visible entries separately from hidden
            // reserved XML entries. Absolute XML indices are not palette IDs.
            int editable=0,reserved=-1;
            return materials.Select(m=>(bool?)m.Attribute("hidden")==true?reserved--:editable++).ToArray();
        }
        internal void ValidateOperations(JArray operations)
        {
            if(operations==null||operations.Count==0)throw new ApiError("invalid_model_scope","Model scope requires a nonempty explicit operations array.");
            variableOrder=(before.Element("Variables")?.Elements("Setter")??Enumerable.Empty<XElement>()).Select(e=>(string)e.Attribute("variable")).ToList();
            for(int index=0;index<operations.Count;index++)
            {
                var operation=operations[index] as JObject;
                if(operation==null)throw new ApiError("invalid_model_scope","Every model operation must be an object.",new JObject{["operationIndex"]=index});
                foreach(string field in new[]{"partId","partA","partB","sourcePartId","targetPartId","wingPartId","anchorPartId"})
                    if(operation[field]!=null)ValidateTarget(operation[field],index,field);
                foreach(string arrayField in new[]{"partIds","targetPartIds"})if(operation[arrayField]!=null)
                {
                    var targets=operation[arrayField] as JArray;
                    if(targets==null||targets.Count==0)throw new ApiError("invalid_model_scope","partIds must be a nonempty explicit reference array.",new JObject{["operationIndex"]=index,["field"]="partIds"});
                    foreach(var target in targets)ValidateTarget(target,index,"partIds");
                }
                ValidateOperationKindAndReferences(operation,index);
            }
        }
        private void ValidateOperationKindAndReferences(JObject operation,int index)
        {
            // Content comparison at the end cannot authorize a transient write:
            // changing a protected group or shared variable and changing it back
            // would leave equal XML. Keep this contract narrower than batch.apply.
            if(operation["groupId"]!=null)throw new ApiError("invalid_model_scope","Model scope requires explicit partIds, not an opaque group handle.",new JObject{["operationIndex"]=index,["field"]="groupId"});
            if(operation["kind"]?.Type!=JTokenType.String)throw new ApiError("invalid_model_scope","Model operations require a named supported kind.",new JObject{["operationIndex"]=index,["field"]="kind"});
            string kind=(string)operation["kind"];
            string[] required;
            switch(kind)
            {
                case "part.add": required=new string[0];break;
                case "craft.refresh":
                    if(parts.Keys.Any(id=>!writable.Contains(id)))throw new ApiError("model_scope_escape","Explicitly review every current part before whole-craft refresh.");
                    required=new string[0];break;
                case "part.clone": case "part.mirror": required=new[]{"partIds"};break;
                case "hole.create": required=new[]{"targetPartIds"};break;
                case "hole.update": required=new[]{"partId"};break;
                case "part.retype": case "native.state": case "mechanical.update": case "part.update": case "part.delete": case "shape.update": case "properties.set":
                case "decal.pose.set": case "fuselage.match": case "symmetry.create": case "symmetry.unlink": case "symmetry.enable":
                    required=new[]{"partId"};break;
                case "output.bind": case "output.update": case "output.unbind": required=new[]{"partId"};break;
                case "variable.add": case "variable.update": case "variable.delete": case "variable.reorder":
                    ValidateVariableOperation(operation,index);required=new string[0];break;
                case "transform.apply": case "symmetry.link": required=new[]{"partIds"};break;
                case "transform.align": required=new[]{"partIds","sourcePartId","targetPartId"};break;
                case "connection.connect": case "connection.disconnect": case "connection.auto": required=new[]{"partA","partB"};break;
                case "wing.control.add": required=new[]{"wingPartId"};break;
                case "appearance.set":
                    if((string)operation["mode"]=="shared"){
                        int materialId;
                        if(!TryPartId(operation["materialId"],out materialId)||!writableMaterials.Contains(materialId))throw new ApiError("model_operation_unsupported","Shared paint needs an explicit writableMaterialIds authorization.");
                        var users=parts.Where(p=>((string)p.Value.Attribute("materials")??"").Split(',').Any(s=>s.Trim()==materialId.ToString(CultureInfo.InvariantCulture))).Select(p=>p.Key).ToArray();
                        if(users.Any(id=>!writable.Contains(id)))throw new ApiError("model_scope_escape","Shared paint affects protected users; explicitly review all current users.",new JObject{["requiredWritableCandidates"]=new JArray(users)});
                        required=new string[0];break;
                    }
                    if(operation["mode"]?.Type!=JTokenType.String||((string)operation["mode"]!="assign"&&((string)operation["mode"]!="clone"||!paletteAppend)))
                        throw new ApiError("model_operation_unsupported","Model scope permits assignment of an existing material only; palette edits require separate explicit authorization.",new JObject{["operationIndex"]=index,["kind"]=kind});
                    required=new[]{"partIds"};break;
                default: throw new ApiError("model_operation_unsupported","This operation is outside the model-scope contract; craft/shared-state mutations are not supported.",new JObject{["operationIndex"]=index,["kind"]=kind});
            }
            foreach(string field in required)
                if(operation[field]==null)throw new ApiError("invalid_model_scope","Missing explicit model operation reference: "+field,new JObject{["operationIndex"]=index,["field"]=field});
            if((kind=="part.delete"||kind=="part.retype")&&operation["partId"]?.Type==JTokenType.Integer){
                int target=(int)operation["partId"];
                var related=(before.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>())
                    .Where(e=>(int?)e.Attribute("partA")==target||(int?)e.Attribute("partB")==target)
                    .SelectMany(e=>new[]{(int)e.Attribute("partA"),(int)e.Attribute("partB")}).Where(id=>parts.ContainsKey(id)&&!writable.Contains(id)).Distinct().OrderBy(id=>id).ToArray();
                if(related.Length>0)throw new ApiError("model_scope_escape","Deleting or retyping this existing object changes connections at protected endpoints. Review all endpoints before applying.",new JObject{
                    ["operationIndex"]=index,["partIds"]=new JArray(related),["requiredWritableCandidates"]=new JArray(related),["reason"]="statically_known_connection_endpoints",["writableExpanded"]=false});
            }
            if((kind=="wing.control.add"&&operation["wingPartId"]?.Type==JTokenType.Integer)||
               (kind=="shape.update"&&operation["partId"]?.Type==JTokenType.Integer)){
                int target=(int)(kind=="wing.control.add"?operation["wingPartId"]:operation["partId"]);
                if(parts.ContainsKey(target)){
                    var edges=(before.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>()).ToArray();
                    var hosts=parts[target].Element("JWing.State")!=null?new[]{target}:edges.Where(e=>(int?)e.Attribute("partA")==target||(int?)e.Attribute("partB")==target)
                        .SelectMany(e=>new[]{(int)e.Attribute("partA"),(int)e.Attribute("partB")}).Where(id=>parts.ContainsKey(id)&&parts[id].Element("JWing.State")!=null).Distinct().ToArray();
                    var candidates=edges.Where(e=>hosts.Contains((int)e.Attribute("partA"))||hosts.Contains((int)e.Attribute("partB")))
                        .SelectMany(e=>new[]{(int)e.Attribute("partA"),(int)e.Attribute("partB")})
                        .Where(id=>parts.ContainsKey(id)&&(parts[id].Element("ControlSurfacePart.State")!=null||hosts.Contains(id))).Concat(hosts).Distinct().OrderBy(id=>id).ToArray();
                    var protectedIds=candidates.Where(id=>!writable.Contains(id)).ToArray();
                    if(protectedIds.Length>0)throw new ApiError("model_scope_escape","Native wing rebuilds update attached control transforms. Review the host and all current native control dependents before this shape operation.",
                        new JObject{["operationIndex"]=index,["partIds"]=new JArray(protectedIds),["requiredWritableCandidates"]=new JArray(candidates),["reason"]="statically_known_native_wing_control_rebuild",["writableExpanded"]=false});
                }
            }
        }
        private void ValidateVariableOperation(JObject operation,int operationIndex)
        {
            if(writableVariables.Count==0)throw new ApiError("model_operation_unsupported","Setter edits require an explicit variableNames scope.");
            string kind=(string)operation["kind"];
            if(kind=="variable.reorder"){
                if(variableOrder.Any(name=>!writableVariables.Contains(name)))throw new ApiError("model_scope_escape","Reordering all Setters needs all affected names reviewed.");
                var order=operation["order"] as JArray;
                if(order==null||order.Count!=variableOrder.Count||order.Any(v=>v.Type!=JTokenType.Integer||(int)v<0||(int)v>=variableOrder.Count)||order.Values<int>().Distinct().Count()!=order.Count)throw new ApiError("invalid_order","Use every current Setter index exactly once.");
                variableOrder=order.Values<int>().Select(i=>variableOrder[i]).ToList();return;
            }
            int index=operation.Value<int?>("index")??-1;string original=null;
            if(kind!="variable.add"){
                if(index<0||index>=variableOrder.Count)throw new ApiError("setter_not_found","Setter index is unavailable at this operation boundary.");
                original=variableOrder[index];
            }
            string requested=(string)operation["variable"]??original;
            var required=new[]{original,requested}.Where(n=>n!=null&&!writableVariables.Contains(n)).Distinct().ToArray();
            if(required.Length>0)throw new ApiError("model_scope_escape","Setter operation targets names outside the reviewed variable scope.",new JObject{["operationIndex"]=operationIndex,["requiredVariableNames"]=new JArray(required)});
            if(kind=="variable.add")variableOrder.Add(requested);
            else if(kind=="variable.delete")variableOrder.RemoveAt(index);
            else variableOrder[index]=requested;
        }
        private string ProtectedShared(XElement xml)
        {
            var copy=new XElement(xml);var vars=copy.Element("Variables");
            if(vars!=null&&writableVariables.Count>0){
                vars.Elements("Setter").Where(e=>writableVariables.Contains((string)e.Attribute("variable"))).Remove();
                if(!vars.HasAttributes&&!vars.HasElements&&!vars.Nodes().Any())vars.Remove();
            }
            return ScopeState.Shared(copy);
        }
        private void ValidateTarget(JToken target,int operationIndex,string field)
        {
            // Only strings can refer to freshly created objects in this batch.
            // Their lifetime and binding are validated by BatchReferences.
            if(target.Type==JTokenType.String&&!string.IsNullOrEmpty((string)target))return;
            int id;
            if(!TryPartId(target,out id))throw new ApiError("invalid_model_scope","Targets must be native numeric IDs or nonempty temporary references.",new JObject{["operationIndex"]=operationIndex,["field"]=field});
            if(!writable.Contains(id))throw new ApiError("model_scope_escape","An operation targets an existing object outside the declared write set. New objects must use temporary references.",new JObject{["operationIndex"]=operationIndex,["field"]=field,["partIds"]=new JArray(id)});
        }
        private string ProtectedEdges(XElement xml)
        {
            var rows=(xml.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>())
                .Where(e=>new[]{(int?)e.Attribute("partA")??-1,(int?)e.Attribute("partB")??-1}.Any(id=>parts.ContainsKey(id)&&!writable.Contains(id)))
                .Select(SnapshotState.Fingerprint).OrderBy(x=>x,StringComparer.Ordinal);
            return string.Join("|",rows);
        }
        internal void Validate(XElement after)
        {
            var current=ScopeState.Parts(after);
            var changed=parts.Keys.Where(id=>!writable.Contains(id)&&(!current.ContainsKey(id)||SnapshotState.Fingerprint(parts[id])!=SnapshotState.Fingerprint(current[id]))).ToArray();
            bool edgesChanged=ProtectedEdges(before)!=ProtectedEdges(after);
            if(changed.Length>0||edgesChanged){
                var oldEdges=(before.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>()).ToArray();
                var newEdges=(after.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>()).ToArray();
                var oldGroups=oldEdges.ToLookup(SnapshotState.Fingerprint);var newGroups=newEdges.ToLookup(SnapshotState.Fingerprint);
                var differences=oldGroups.Select(g=>g.Key).Union(newGroups.Select(g=>g.Key)).SelectMany(key=>{
                    int delta=newGroups[key].Count()-oldGroups[key].Count();
                    var edge=delta>0?newGroups[key].First():oldGroups[key].First();
                    return Enumerable.Range(0,Math.Abs(delta)).Select(_=>new JObject{["change"]=delta>0?"added":"removed",["attributes"]=new JObject(edge.Attributes().Select(a=>new JProperty(a.Name.LocalName,a.Value)))});
                }).ToArray();
                var endpoints=differences.SelectMany(e=>new[]{e["attributes"]["partA"],e["attributes"]["partB"]}).Where(x=>x!=null).Select(x=>(int)x).Distinct().ToArray();
                throw new ApiError("model_scope_escape","Native author fields or protected topology changed. Review the complete observed dependencies; no write set was expanded.",new JObject{
                    ["partIds"]=new JArray(changed),["requiredWritableCandidates"]=new JArray(changed.Concat(endpoints).Distinct().OrderBy(x=>x)),
                    ["fieldChanges"]=new JArray(changed.Select(id=>new JObject{["partId"]=id,["deleted"]=!current.ContainsKey(id),["diff"]=CraftDiff.Compare(parts[id],current.ContainsKey(id)?current[id]:new XElement("Part"),100)})),
                    ["connectionChanges"]=new JArray(differences),["protectedEdgesChanged"]=edgesChanged,
                    ["dependencyCompleteness"]="observed_after_execution_only; unknown native callback chains require current evidence",
                    ["writablePartIds"]=new JArray(writable.OrderBy(x=>x))});
            }
            if(!paletteAppend&&writableMaterials.Count==0){if(ProtectedShared(before)!=ProtectedShared(after))throw new ApiError("model_scope_escape","Shared craft state outside the explicit palette/Setter authorization changed.");}
            else {
                var a=new XElement(before);var b=new XElement(after);a.Element("Theme")?.Remove();b.Element("Theme")?.Remove();a.Attribute("theme")?.Remove();b.Attribute("theme")?.Remove();
                if(ProtectedShared(a)!=ProtectedShared(b))throw new ApiError("model_scope_escape","Palette append changed unrelated shared craft state.");
                var palette=after.Element("Theme");if(palette==null||(string)after.Attribute("theme")!="Custom")throw new ApiError("model_scope_escape","Palette clone must remain local to a Custom craft theme.");
                var oldMaterials=paletteBefore.Elements("Material").ToArray();var newMaterials=palette.Elements("Material").ToArray();
                if(newMaterials.Length<oldMaterials.Length||(!paletteAppend&&newMaterials.Length!=oldMaterials.Length))throw new ApiError("model_scope_escape","Palette entries were removed or appended without authorization.");
                var oldMaterialIds=NativeMaterialIds(oldMaterials);var newMaterialIds=NativeMaterialIds(newMaterials);
                if(oldMaterials.Where((m,i)=>!writableMaterials.Contains(oldMaterialIds[i])&&SnapshotState.Fingerprint(m)!=SnapshotState.Fingerprint(newMaterials[i])).Any())throw new ApiError("model_scope_escape","Unreviewed palette entries changed or were reordered.");
                if(oldMaterialIds.Where((id,i)=>id!=newMaterialIds[i]).Any()||newMaterialIds.Skip(oldMaterialIds.Length).Any(id=>id<0))throw new ApiError("model_scope_escape","Reserved/visible palette identity cannot change through material authorization.");
                var oldMeta=new XElement(paletteBefore);var newMeta=new XElement(palette);oldMeta.Elements("Material").Remove();newMeta.Elements("Material").Remove();oldMeta.Attribute("name")?.Remove();newMeta.Attribute("name")?.Remove();
                if(SnapshotState.Fingerprint(oldMeta)!=SnapshotState.Fingerprint(newMeta))throw new ApiError("model_scope_escape","Palette metadata outside its local name changed.");
            }
        }
    }
}
