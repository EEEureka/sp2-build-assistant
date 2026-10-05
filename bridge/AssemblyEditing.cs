using System.Collections.Generic;
using System.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.Weapons;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private AssemblyScope.Plan AssemblyPlan(PartData root,bool symmetric)
        {
            var d=Current();var assembly=d.Aircraft.Aircraft.Assembly;var roots=new List<PartData>{root};
            if(symmetric)assembly.GetOtherSymmetricParts(root,roots);
            var nodes=assembly.Parts.Select(p=> {
                string role="other";int? owner=null;
                if(p.GetModifier<ProceduralMissileData>()!=null)role="missile";
                else if(p.GetModifier<JWingData>()!=null)role="wing";
                else if(p.PartScript.GetModifierWithInterface<IMissileSubPart>()!=null) {
                    role="missileChild";owner=p.GetModifier<ProceduralMissileSubPartData>()?.Script?.GetConnectedMissile()?.PartScript.Part.Id;
                }
                else if(p.GetModifier<ControlSurfacePartData>() is ControlSurfacePartData control) {
                    role="wingControl";owner=control.GetFirstConnectedWing()?.Part.Id;
                }
                return new AssemblyScope.Node{Id=p.Id,Role=role,OwnerId=owner,Protected=p.PartScript==d.Aircraft.MainCockpit};
            }).ToArray();
            var edges=assembly.Parts.SelectMany(p=>p.PartConnections).Distinct().Select(c=>new AssemblyScope.Edge{A=c.PartA.Id,B=c.PartB.Id});
            return AssemblyScope.Resolve(nodes,edges,roots.Select(p=>p.Id));
        }
        private JObject AssemblyInfo(PartData root,bool symmetric)
        {
            var plan=AssemblyPlan(root,symmetric);
            return new JObject{["rootPartId"]=root.Id,["symmetric"]=symmetric,["rootPartIds"]=new JArray(plan.Roots),
                ["memberPartIds"]=new JArray(plan.Members),["childPartIds"]=new JArray(plan.Children),
                ["parts"]=new JArray(plan.Members.Select(id=>PartInfo(Part(id),false))),
                ["externalConnections"]=new JArray(plan.ExternalConnections.Select(e=>new JObject{["partA"]=e.A,["partB"]=e.B})),
                ["membershipSource"]="native_missile_subparts_or_wing_control_surfaces",
                ["meaning"]="Bounded native component ownership, not all reachable parts or physical support. Only listed members are removed by assembly:true."};
        }
        private JObject DeleteAssembly(PartData root,bool symmetric)
        {
            var plan=AssemblyPlan(root,symmetric);var d=Current();
            var before=new HashSet<int>(d.Aircraft.Aircraft.Assembly.Parts.Select(p=>p.Id));
            // Resolve the entire scope before any deletion; remove dependent components first.
            foreach(int id in plan.Children.Concat(plan.Roots))d.DeletePart(Part(id).PartScript,false);
            var after=new HashSet<int>(d.Aircraft.Aircraft.Assembly.Parts.Select(p=>p.Id));before.ExceptWith(after);
            if(!before.SetEquals(plan.Members))throw new ApiError("assembly_delete_mismatch","Native deletion differed from the planned assembly scope; restoring the transaction.");
            return new JObject{["kind"]="part.delete",["partId"]=root.Id,["assembly"]=true,["symmetric"]=symmetric,
                ["rootPartIds"]=new JArray(plan.Roots),["deletedPartIds"]=new JArray(plan.Members)};
        }
    }
}
