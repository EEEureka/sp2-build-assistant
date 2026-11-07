using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // An opt-in content guard; the legacy revision guard remains unchanged.
    // This model has no Unity dependencies so conflict and recovery boundaries
    // can be tested without a player craft or a running designer.
    internal sealed class ScopeState
    {
        internal int[] WriteIds, GuardIds;
        internal string SharedHash, ConnectionHash;
        internal Dictionary<int,string> PartHashes;
        internal JArray Relations;

        internal static Dictionary<int,XElement> Parts(XElement xml)
        {
            var rows=xml.Element("Assembly")?.Element("Parts")?.Elements("Part");
            if(rows==null)throw new ApiError("scope_unavailable","Native part inventory is unavailable.");
            return rows.ToDictionary(p=>(int)p.Attribute("id"));
        }
        internal static ScopeState Capture(XElement xml,IEnumerable<int> writes,IEnumerable<int> boundaries,IEnumerable<int> spatiallyVerifiedTargeting=null)
        {
            var parts=Parts(xml);var write=new HashSet<int>(writes);var guards=new HashSet<int>(write.Concat(boundaries));
            if(write.Count<1||write.Count>2048||guards.Any(id=>!parts.ContainsKey(id)))throw new ApiError("invalid_scope","Scope needs existing explicit write parts and boundaries.");
            var relations=new JArray();var coupled=new HashSet<int>(write);var verified=new HashSet<int>(spatiallyVerifiedTargeting??Enumerable.Empty<int>());bool expanded;
            do {
                expanded=false;
                foreach(var pair in parts){
                    int id=pair.Key;string symmetry=(string)pair.Value.Attribute("symmetryId");
                    if(symmetry!=null&&symmetry!="0"&&coupled.Contains(id))
                        foreach(var peer in parts.Where(p=>(string)p.Value.Attribute("symmetryId")==symmetry))if(coupled.Add(peer.Key))expanded=true;
                    foreach(var target in pair.Value.Descendants("PartTargeting.State")){
                        string mode=(string)target.Attribute("targetMode");var values=ParseIds((string)target.Attribute(mode=="Custom"?"customPartIds":"partIds"));
                        // Native MultipleParts is a dynamic intersection receiver,
                        // not an authored whitelist. Its current cache can be used
                        // locally only with a same-state native volume check.
                        bool bounded=mode=="Custom"||mode=="SinglePart"||mode=="MultipleParts"&&verified.Contains(id);
                        if(!bounded){
                            foreach(int key in parts.Keys)if(coupled.Add(key))expanded=true;
                        }else if(coupled.Contains(id)||values.Any(coupled.Contains)){
                            if(coupled.Add(id))expanded=true;
                            foreach(int key in values){if(!parts.ContainsKey(key))throw new ApiError("scope_unavailable","Explicit target refers to an unavailable part.");if(coupled.Add(key))expanded=true;}
                        }
                    }
                }
            }while(expanded);
            guards.UnionWith(coupled);
            foreach(var edge in xml.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>()){
                int? a=(int?)edge.Attribute("partA"),b=(int?)edge.Attribute("partB");
                if(a.HasValue&&b.HasValue&&(coupled.Contains(a.Value)||coupled.Contains(b.Value))){
                    if(!parts.ContainsKey(a.Value)||!parts.ContainsKey(b.Value))throw new ApiError("scope_unavailable","Native connection has unavailable endpoint.");
                    guards.Add(a.Value);guards.Add(b.Value);relations.Add(new JObject{["kind"]="native_connection",["partA"]=a.Value,["partB"]=b.Value});
                }
            }
            foreach(int id in coupled.Except(write))relations.Add(new JObject{["kind"]="symmetry_or_target_dependency",["partId"]=id});
            var state=new ScopeState{WriteIds=write.OrderBy(x=>x).ToArray(),GuardIds=guards.OrderBy(x=>x).ToArray(),Relations=relations};
            state.PartHashes=state.GuardIds.ToDictionary(id=>id,id=>SnapshotState.Fingerprint(parts[id]));
            state.SharedHash=Shared(xml);state.ConnectionHash=Connections(xml,guards);return state;
        }
        internal static int[] ParseIds(string value)
        {
            if(string.IsNullOrEmpty(value))return new int[0];
            var rows=new List<int>();foreach(string item in value.Split(',')){int id;if(!int.TryParse(item,NumberStyles.Integer,CultureInfo.InvariantCulture,out id)||id<0)throw new ApiError("scope_unavailable","Target IDs cannot be interpreted safely.");rows.Add(id);}return rows.Distinct().ToArray();
        }
        internal static string Shared(XElement xml)
        {
            var copy=new XElement(xml);copy.Element("Assembly")?.Element("Parts")?.Remove();copy.Element("Assembly")?.Element("Connections")?.Remove();return SnapshotState.Fingerprint(copy);
        }
        private static string Connections(XElement xml,HashSet<int> ids)
        {
            var rows=(xml.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>())
                .Where(e=>ids.Contains((int?)e.Attribute("partA")??-1)||ids.Contains((int?)e.Attribute("partB")??-1))
                .Select(e=>SnapshotState.Fingerprint(e)).OrderBy(x=>x,StringComparer.Ordinal);
            return SnapshotState.Fingerprint(new XElement("ScopeConnections",rows.Select(x=>new XElement("Hash",x))));
        }
        internal int[] Conflicts(XElement current)
        {
            var parts=Parts(current);return GuardIds.Where(id=>!parts.ContainsKey(id)||SnapshotState.Fingerprint(parts[id])!=PartHashes[id]).ToArray();
        }
        internal void Validate(XElement current)
        {
            var conflicts=Conflicts(current);
            if(conflicts.Length>0)throw new ApiError("scope_conflict","A target, boundary, symmetry peer or targeting dependency changed.",new JObject{["partIds"]=new JArray(conflicts)});
            if(Shared(current)!=SharedHash)throw new ApiError("scope_conflict","Shared craft state changed; recapture and review the scope.");
            if(Connections(current,new HashSet<int>(GuardIds))!=ConnectionHash)throw new ApiError("scope_conflict","Scoped native connection state changed.");
        }
        internal void ValidateOutsideUnchanged(XElement before,XElement after)
        {
            var a=Parts(before);var b=Parts(after);var write=new HashSet<int>(WriteIds);
            if(!a.Keys.OrderBy(x=>x).SequenceEqual(b.Keys.OrderBy(x=>x)))throw new ApiError("scope_escape","Scoped in-place edits cannot create or retire parts.");
            var changed=a.Keys.Where(id=>!write.Contains(id)&&SnapshotState.Fingerprint(a[id])!=SnapshotState.Fingerprint(b[id])).ToArray();
            if(changed.Length>0)throw new ApiError("scope_escape","Native callbacks changed parts outside the declared write scope.",new JObject{["partIds"]=new JArray(changed)});
            if(Shared(before)!=Shared(after))throw new ApiError("scope_escape","Scoped in-place edit changed shared craft state.");
            var all=new HashSet<int>(a.Keys);
            if(Connections(before,all)!=Connections(after,all))throw new ApiError("scope_escape","Scoped in-place edit changed native topology.");
        }
        internal static int[] OperationTargets(JObject op)
        {
            string kind=(string)op["kind"];
            if(!new[]{"part.update","shape.update","properties.set","transform.apply","transform.align","decal.pose.set","appearance.set"}.Contains(kind))throw new ApiError("scoped_operation_unsupported","Scoped jobs support in-place part/shape/property/transform edits and material assignment only.");
            if(op["groupId"]!=null)throw new ApiError("invalid_scope","Scoped jobs use explicit numeric partIds, not revision-bound group handles.");
            if(kind=="appearance.set"&&(string)op["mode"]!="assign")throw new ApiError("scoped_operation_unsupported","Palette cloning/shared mutation requires a strict atomic batch.");
            JToken token=op["partIds"]??(op["partId"]==null?null:new JArray(op["partId"]));
            var values=token as JArray;if(values==null||values.Count<1||values.Any(v=>v.Type!=JTokenType.Integer||(long)v<0||(long)v>int.MaxValue))throw new ApiError("invalid_scope","Scoped operation requires explicit current numeric target IDs.");
            return values.Values<int>().Distinct().ToArray();
        }
    }
}
