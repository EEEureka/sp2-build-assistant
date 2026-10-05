using System;
using System.Collections.Generic;
using System.Linq;

namespace SP2BuildAssistant
{
    // Ownership is supplied by native modifiers, never inferred by walking a craft graph.
    internal static class AssemblyScope
    {
        internal sealed class Node
        {
            public int Id;
            public string Role;
            public int? OwnerId;
            public bool Protected;
        }
        internal sealed class Edge { public int A, B; }
        internal sealed class Plan
        {
            public int[] Roots, Children, Members;
            public Edge[] ExternalConnections;
        }
        internal static Plan Resolve(IEnumerable<Node> nodes, IEnumerable<Edge> connections, IEnumerable<int> rootIds)
        {
            var all=nodes.ToDictionary(n=>n.Id);var edges=connections.ToArray();var roots=rootIds.Distinct().OrderBy(x=>x).ToArray();
            var members=new HashSet<int>(roots);var children=new HashSet<int>();
            foreach(int id in roots) {
                if(!all.TryGetValue(id,out Node root))throw new ApiError("part_not_found","Assembly root no longer exists: "+id);
                string childRole=root.Role=="missile"?"missileChild":root.Role=="wing"?"wingControl":null;
                if(childRole==null)throw new ApiError("assembly_not_supported","assembly:true requires a procedural missile body or JWing root; arbitrary connected branches have no defined ownership.");
                foreach(int otherId in edges.Where(e=>e.A==id || e.B==id).Select(e=>e.A==id?e.B:e.A).Distinct()) {
                    var child=all[otherId];if(child.Role!=childRole)continue;
                    if(child.OwnerId!=id)throw new ApiError("assembly_ambiguous","Native owner of child "+otherId+" does not match root "+id+".");
                    children.Add(otherId);members.Add(otherId);
                }
                // A native-owned component without the corresponding connection is inconsistent.
                if(all.Values.Any(n=>n.Role==childRole && n.OwnerId==id && !members.Contains(n.Id)))
                    throw new ApiError("assembly_ambiguous","Native membership and connection data disagree.");
            }
            foreach(int child in children) {
                var outside=edges.Where(e=>e.A==child || e.B==child).Select(e=>e.A==child?e.B:e.A).Where(id=>!members.Contains(id));
                if(outside.Any())throw new ApiError("assembly_ambiguous","Child "+child+" also connects outside this assembly. Use explicit part IDs after inspection.");
            }
            if(members.Any(id=>all[id].Protected))throw new ApiError("main_cockpit_delete","Assembly includes the main cockpit; replace it in the game first.");
            return new Plan { Roots=roots,Children=children.OrderBy(x=>x).ToArray(),Members=members.OrderBy(x=>x).ToArray(),
                ExternalConnections=edges.Where(e=>members.Contains(e.A)!=members.Contains(e.B)).ToArray() };
        }
    }
}
