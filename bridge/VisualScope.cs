using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    internal static class VisualScope
    {
        internal sealed class Edge {public int A,B;public string Key; public JObject Info;}
        internal static void Keys(JObject obj,params string[] keys){if(obj==null)throw new ApiError("invalid_input","Expected a JSON object.");foreach(var p in obj.Properties())if(!keys.Contains(p.Name))throw new ApiError("invalid_input","Unknown field: "+p.Name);}
        internal static int Integer(JToken token,string field,int min=int.MinValue,int max=int.MaxValue){if(token==null||token.Type!=JTokenType.Integer)throw new ApiError("invalid_input",field+" must be an integer.");long v=token.Value<long>();if(v<min||v>max)throw new ApiError("invalid_input",field+" out of range.");return (int)v;}
        internal static bool Boolean(JToken t,string key,bool fallback=false){if(t==null)return fallback;if(t.Type!=JTokenType.Boolean)throw new ApiError("invalid_input",key+" must be boolean.");return t.Value<bool>();}
        internal static string String(JToken t,string key,string fallback=null){if(t==null&&fallback!=null)return fallback;if(t==null||t.Type!=JTokenType.String||string.IsNullOrWhiteSpace((string)t))throw new ApiError("invalid_input",key+" must be a nonempty string.");return (string)t;}
        internal static int[] Resolve(JObject s,HashSet<int> all,Edge[] edges,int? selected,Func<int,int[]> assembly,int max)
        {
            string kind=String(s?["kind"],"selector.kind");HashSet<int> result;
            if(kind=="parts"){
                Keys(s,"kind","partIds");if(!(s["partIds"] is JArray ids)||ids.Count==0)throw new ApiError("invalid_input","partIds must be nonempty.");result=new HashSet<int>(ids.Select(x=>Integer(x,"partId")));
            }else if(kind=="selected"){Keys(s,"kind");if(!selected.HasValue)throw new ApiError("selection_empty","No selected part.");result=new HashSet<int>{selected.Value};
            }else if(kind=="craft"){Keys(s,"kind");result=new HashSet<int>(all);
            }else if(kind=="assembly"){Keys(s,"kind","rootPartId");int root=Integer(s["rootPartId"],"rootPartId");if(!all.Contains(root))throw new ApiError("part_not_found","Root part not found.");result=new HashSet<int>(assembly(root));
            }else if(kind=="branch"||kind=="neighborhood"){
                Keys(s,"kind","rootPartId",kind=="branch"?"stopConnectionKeys":"hops");int root=Integer(s["rootPartId"],"rootPartId");if(!all.Contains(root))throw new ApiError("part_not_found","Root part not found.");
                var cuts=new HashSet<string>();int hops=int.MaxValue;
                if(kind=="branch"){if(!(s["stopConnectionKeys"] is JArray keys)||keys.Count==0)throw new ApiError("invalid_input","branch requires stopConnectionKeys from visual.resolve connections.");foreach(var k in keys){string key=String(k,"connection key");if(!edges.Any(e=>e.Key==key))throw new ApiError("connection_not_found","Unknown stop connection: "+key);cuts.Add(key);}}
                else hops=Integer(s["hops"],"hops",0,10);
                result=new HashSet<int>{root};var queue=new Queue<Tuple<int,int>>();queue.Enqueue(Tuple.Create(root,0));
                while(queue.Count>0){var current=queue.Dequeue();if(current.Item2>=hops)continue;foreach(var e in edges){if(cuts.Contains(e.Key))continue;int next=e.A==current.Item1?e.B:e.B==current.Item1?e.A:int.MinValue;if(next==int.MinValue||!result.Add(next))continue;if(result.Count>max)throw new ApiError("scope_budget","Scope exceeds maxParts.");queue.Enqueue(Tuple.Create(next,current.Item2+1));}}
                if(kind=="branch")foreach(var e in edges.Where(e=>cuts.Contains(e.Key)))if(result.Contains(e.A)==result.Contains(e.B))throw new ApiError("scope_ambiguous","A stop edge does not separate the selected branch; cycle or unrelated boundary: "+e.Key);
            }else throw new ApiError("invalid_input","Unknown selector kind: "+kind);
            if(result.Count>max)throw new ApiError("scope_budget","Scope exceeds maxParts.");if(result.Any(id=>!all.Contains(id)))throw new ApiError("part_not_found","Scope contains missing part IDs.");return result.OrderBy(i=>i).ToArray();
        }
    }
}
