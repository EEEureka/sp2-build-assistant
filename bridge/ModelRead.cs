using System;
using System.Linq;
using Assets.Scripts.Craft.Parts;
using Newtonsoft.Json.Linq;
using SP2Game = Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private JObject ModelStatus()
        {
            string nativeScene=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
            bool ready=DesignerReady(nativeScene);
            var xml=ready?Observe():null;
            return new JObject {
                ["pluginVersion"]="0.7.8", ["sdkVersion"]="0.7.8a1", ["releaseStatus"]="development",
                ["buildId"]=typeof(BuildRuntime).Assembly.ManifestModule.ModuleVersionId.ToString(),
                ["instancePid"]=System.Diagnostics.Process.GetCurrentProcess().Id,
                ["gameVersion"]=SP2Game.Version.ToString(), ["scene"]=nativeScene, ["designerReady"]=ready,
                ["name"]=ready?Current().Aircraft.Aircraft.Name:null,
                ["identity"]=ready?JToken.FromObject(Identity()):null,
                ["partCount"]=ready?Current().Aircraft.Aircraft.Assembly.Parts.Count:0,
                ["connectionCount"]=xml?.Element("Assembly")?.Element("Connections")?.Elements().Count()??0,
                ["modelingSdk"]=new JObject {["contract"]="sp2model/1",["scope"]=ModelScope.Version},
                ["detail"]="summary", ["meaning"]="Identity at sampling time; no parts or connection payload and no implicit permission to write."
            };
        }

        private JObject ModelQuery(JObject args)
        {
            if(args.Properties().Any(p=>!new[]{"partIds","name","type","offset","limit","fields","craftSessionId","expectedRevision"}.Contains(p.Name)))
                throw new ApiError("invalid_input","Unknown parts.query option.");
            if(args["craftSessionId"]!=null&&(string)args["craftSessionId"]!=session)throw new ApiError("session_conflict","Query belongs to another craft session.");
            if(args["expectedRevision"]!=null&&args.Value<long>("expectedRevision")!=revision)throw new ApiError("revision_conflict","Query pages must use the same identity.");
            int offset=args.Value<int?>("offset")??0, limit=args.Value<int?>("limit")??50;
            if(offset<0||limit<1||limit>200)throw new ApiError("invalid_input","parts.query offset >= 0 and limit 1..200.");
            var ids=args["partIds"] as JArray;
            if(args["partIds"]!=null&&(ids==null||ids.Count>2048||ids.Any(x=>x.Type!=JTokenType.Integer)))throw new ApiError("invalid_input","partIds must be an explicit array of native integer IDs.");
            foreach(string field in new[]{"name","type"})if(args[field]!=null&&args[field].Type!=JTokenType.String)throw new ApiError("invalid_input",field+" must be a string.");
            string[] allowed={"id","name","type","typeName","position","rotationQuaternion","rotationEulerDegrees","scale","symmetryId","materialIds","connectedPartIds","partFingerprint","contentFingerprint","contentFingerprintAlgorithm","lifetimeId","state","outputs","attachPoints","inputControllers"};
            var fields=args["fields"] as JArray;
            if(args["fields"]!=null&&(fields==null||fields.Count==0||fields.Any(x=>x.Type!=JTokenType.String||!allowed.Contains((string)x))))throw new ApiError("invalid_input","fields must select known part fields.",new JObject{["allowedFields"]=new JArray(allowed)});
            string[] selected=fields==null?new[]{"id","name","type","position","rotationQuaternion","scale","partFingerprint","contentFingerprint","lifetimeId"}:fields.Values<string>().Distinct().ToArray();
            var matches=Current().Aircraft.Aircraft.Assembly.Parts.Where(p=>(ids==null||ids.Values<int>().Contains(p.Id))&&(args["name"]==null||p.Name==(string)args["name"])&&(args["type"]==null||p.PartType.PartTypeId==(string)args["type"])).OrderBy(p=>p.Id).ToArray();
            bool details=selected.Any(x=>new[]{"state","outputs","attachPoints","inputControllers"}.Contains(x));
            var items=new JArray(matches.Skip(offset).Take(limit).Select(p=>{var full=PartInfo(p,details);return new JObject(selected.Concat(new[]{"id"}).Distinct().Select(k=>new JProperty(k,full[k]?.DeepClone())));}));
            return new JObject{["identity"]=JToken.FromObject(Identity()),["name"]=Current().Aircraft.Aircraft.Name,["items"]=items,["total"]=matches.Length,["returned"]=items.Count,["offset"]=offset,["limit"]=limit,["hasMore"]=offset+items.Count<matches.Length,["truncationReason"]=offset+items.Count<matches.Length?"page_limit":null,["allowedFields"]=new JArray(allowed)};
        }

        private JObject ModelDependencies(JObject args)
        {
            var requested=args["partIds"] as JArray;
            if(requested==null||requested.Count==0||requested.Count>2048||requested.Any(v=>v.Type!=JTokenType.Integer))throw new ApiError("invalid_input","Explicit native partIds required.");
            if((string)args["craftSessionId"]!=session||args.Value<long?>("expectedRevision")!=revision)throw new ApiError("revision_conflict","Dependencies must be sampled at the inspected identity.");
            int[] ids=requested.Values<int>().Distinct().ToArray();foreach(int id in ids)Part(id);
            var set=new System.Collections.Generic.HashSet<int>(ids);var xml=Current().Aircraft.Aircraft.GenerateXml(false);
            var edges=(xml.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<System.Xml.Linq.XElement>())
                .Where(e=>set.Contains((int)e.Attribute("partA"))||set.Contains((int)e.Attribute("partB"))).ToArray();
            var endpoints=edges.SelectMany(e=>new[]{(int)e.Attribute("partA"),(int)e.Attribute("partB")});
            var groups=GroupInfo(ids);
            var symmetryIds=ids.Select(id=>Part(id).SymmetryId).Where(id=>id!=0).ToArray();
            var peers=Current().Aircraft.Aircraft.Assembly.Parts.Where(p=>symmetryIds.Contains(p.SymmetryId)&&!set.Contains(p.Id)).Select(p=>p.Id).ToArray();
            return new JObject{["identity"]=JToken.FromObject(Identity()),["selectedPartIds"]=new JArray(ids),["connections"]=ReadModels.Connections(new System.Xml.Linq.XElement("Connections",edges)),
                ["nativeGroups"]=groups,["symmetryCandidates"]=new JArray(peers),["requiredWritableCandidates"]=new JArray(endpoints.Concat(peers).Distinct().OrderBy(id=>id)),
                ["completeness"]="static_native_connection_host_and_symmetry_relations_only",["unknownDynamicCallbacks"]=true,["writableExpanded"]=false,
                ["meaning"]="Review candidates explicitly; this is not physical parenthood, permission to edit, or proof that every runtime callback is known."};
        }
    }
}
