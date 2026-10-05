using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
namespace SP2BuildAssistant { internal class ApiError:Exception { public string Code;public ApiError(string code,string message):base(message){Code=code;} } }
class AssemblyScopeTests
{
    static int count;
    static AssemblyScope.Node N(int id,string role,int? owner=null,bool protect=false){return new AssemblyScope.Node{Id=id,Role=role,OwnerId=owner,Protected=protect};}
    static AssemblyScope.Edge E(int a,int b){return new AssemblyScope.Edge{A=a,B=b};}
    static void Check(string label,bool yes){if(!yes)throw new Exception(label);count++;Console.WriteLine("PASS "+label);}
    static void Reject(string label,string code,Action action){try{action();}catch(ApiError e){Check(label,e.Code==code);return;}throw new Exception(label+" was accepted");}
    static void Main(string[] args)
    {
        var nodes=new[]{N(1,"missile"),N(2,"missileChild",1),N(3,"other"),N(4,"wing")};
        var edges=new[]{E(1,2),E(1,3),E(3,4)};
        var plan=AssemblyScope.Resolve(nodes,edges,new[]{1});
        Check("Missile stops before pylon and wing",plan.Members.SequenceEqual(new[]{1,2}));
        Check("External root connection reported",plan.ExternalConnections.Length==1 && plan.ExternalConnections[0].B==3);
        Reject("Do not walk arbitrary connected branch","assembly_not_supported",()=>AssemblyScope.Resolve(nodes,edges,new[]{3}));
        Reject("Do not promote child to root","assembly_not_supported",()=>AssemblyScope.Resolve(nodes,edges,new[]{2}));
        Reject("Native child owner mismatch","assembly_ambiguous",()=>AssemblyScope.Resolve(new[]{N(1,"missile"),N(2,"missileChild",9)},new[]{E(1,2)},new[]{1}));
        Reject("Unknown native owner","assembly_ambiguous",()=>AssemblyScope.Resolve(new[]{N(1,"missile"),N(2,"missileChild")},new[]{E(1,2)},new[]{1}));
        Reject("Child shared outside assembly","assembly_ambiguous",()=>AssemblyScope.Resolve(nodes,edges.Concat(new[]{E(2,3)}),new[]{1}));
        Reject("Missing native connection","assembly_ambiguous",()=>AssemblyScope.Resolve(nodes,new[]{E(1,3)},new[]{1}));
        Reject("Main cockpit anywhere in scope","main_cockpit_delete",()=>AssemblyScope.Resolve(new[]{N(1,"missile"),N(2,"missileChild",1,true)},new[]{E(1,2)},new[]{1}));
        var wing=AssemblyScope.Resolve(new[]{N(1,"wing"),N(2,"wingControl",1),N(3,"other"),N(4,"missile")},new[]{E(1,2),E(1,3),E(3,4)},new[]{1});
        Check("Wing includes controls but excludes stores",wing.Members.SequenceEqual(new[]{1,2}));
        var symmetric=AssemblyScope.Resolve(nodes.Concat(new[]{N(5,"missile"),N(6,"missileChild",5)}),edges.Concat(new[]{E(5,6),E(5,3)}),new[]{1,5});
        Check("Explicit mirrored roots include their own children",symmetric.Members.SequenceEqual(new[]{1,2,5,6}));
        Check("Known root can have no children",AssemblyScope.Resolve(new[]{N(1,"missile")},new AssemblyScope.Edge[0],new[]{1}).Members.SequenceEqual(new[]{1}));
        Reject("Shared child between two selected roots rejected","assembly_ambiguous",()=>AssemblyScope.Resolve(new[]{N(1,"missile"),N(2,"missileChild",1),N(3,"missile")},new[]{E(1,2),E(2,3)},new[]{1,3}));
        if(args.Length>0) {
            var xml=XElement.Parse((string)JObject.Parse(File.ReadAllText(args[0]))["data"]["xml"]);
            var parts=xml.Element("Assembly").Element("Parts").Elements("Part").ToDictionary(p=>(int)p.Attribute("id"));
            var realEdges=xml.Element("Assembly").Element("Connections").Elements().Select(e=>E((int)e.Attribute("partA"),(int)e.Attribute("partB"))).ToArray();
            var realNodes=parts.Select(pair=>{
                var p=pair.Value;string role=p.Element("ProceduralMissile.State")!=null?"missile":p.Element("ProceduralMissileSubPart.State")!=null?"missileChild":"other";
                int? owner=null;
                if(role=="missileChild") {
                    var first=realEdges.FirstOrDefault(e=>e.A==pair.Key || e.B==pair.Key);
                    if(first!=null){int other=first.A==pair.Key?first.B:first.A;if(parts[other].Element("ProceduralMissile.State")!=null)owner=other;}
                }
                return N(pair.Key,role,owner);
            }).ToArray();
            var real=AssemblyScope.Resolve(realNodes,realEdges,new[]{229});
            Check("Captured Starfall body and five native components",real.Members.SequenceEqual(new[]{229,230,234,235,239,240}));
            Check("Captured pylon 103 is outside delete scope",real.ExternalConnections.Any(e=>e.A==103 || e.B==103) && !real.Members.Contains(103));
        }
        Console.WriteLine("Checks passed: "+count);
    }
}
