using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
namespace SP2BuildAssistant {internal sealed class ApiError:Exception {public string Code;public ApiError(string code,string message):base(message){Code=code;}}}
class VisualTests
{
    static int passed;
    static void Check(string name,bool value){if(!value)throw new Exception(name);passed++;Console.WriteLine("PASS "+name);}
    static void Reject(string name,string code,Action action){try{action();}catch(ApiError e){Check(name,e.Code==code);return;}throw new Exception(name+" unexpectedly passed");}
    static VisualCore.MeshData Cube(int id,int group,double x,double y,double z,double sx=1,double sy=1,double sz=1)
    {
        return new VisualCore.MeshData{PartId=id,Group=group,Vertices=new[]{new VisualCore.V(-1,-1,-1),new VisualCore.V(1,-1,-1),new VisualCore.V(1,1,-1),new VisualCore.V(-1,1,-1),new VisualCore.V(-1,-1,1),new VisualCore.V(1,-1,1),new VisualCore.V(1,1,1),new VisualCore.V(-1,1,1)}.Select(v=>new VisualCore.V(x+v.X*sx,y+v.Y*sy,z+v.Z*sz)).ToArray(),Indices=new[]{0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,2,3,7,2,7,6,1,2,6,1,6,5,3,0,4,3,4,7}};
    }
    static JObject Manifest(){return new JObject{["groups"]=new JArray(new JObject{["index"]=0,["name"]="A"},new JObject{["index"]=1,["name"]="B"})};}
    static int Pick(VisualCore.Image img,VisualCore.V point)
    {
        var rows=(JArray)img.Info["frameToPixelRows"];Func<int,int> f=r=>(int)Math.Floor(rows[r][0].Value<double>()*point.X+rows[r][1].Value<double>()*point.Y+rows[r][2].Value<double>()*point.Z+rows[r][3].Value<double>());return img.Ids[f(1)*img.Width+f(0)];
    }
    static void Main(string[] args)
    {
        Check("Odd overview includes blank tile in budget",VisualCore.ImagePixelCount(1000,1000,3,3)==16000000);
        Check("Even and single overview budget",VisualCore.ImagePixelCount(1000,1000,4,2)==16000000&&VisualCore.ImagePixelCount(128,128,1,0)==32768);
        Reject("Custom view cannot overwrite overview","invalid_view",()=>VisualCore.ValidateViewName("overview"));
        Reject("Custom view cannot target Windows device","invalid_view",()=>VisualCore.ValidateViewName("con"));
        var nodes=new HashSet<int>{1,2,3,4};var edges=new[]{new VisualScope.Edge{A=1,B=2,Key="a"},new VisualScope.Edge{A=2,B=3,Key="b"},new VisualScope.Edge{A=3,B=4,Key="c"}};
        Func<JObject,int[]> resolve=s=>VisualScope.Resolve(s,nodes,edges,2,id=>new[]{id,4},20);
        Check("Explicit ids deduplicate and sort",resolve(JObject.Parse("{kind:'parts',partIds:[3,1,3]}")).SequenceEqual(new[]{1,3}));
        Check("Selected resolves exact part",resolve(JObject.Parse("{kind:'selected'}")).SequenceEqual(new[]{2}));
        Check("Craft includes disconnected parts",resolve(JObject.Parse("{kind:'craft'}")).Length==4);
        Check("Native assembly membership adapter",resolve(JObject.Parse("{kind:'assembly',rootPartId:3}")).SequenceEqual(new[]{3,4}));
        Check("Bounded branch stops before aircraft",resolve(JObject.Parse("{kind:'branch',rootPartId:3,stopConnectionKeys:['b']}")).SequenceEqual(new[]{3,4}));
        Check("Neighborhood hop limit",resolve(JObject.Parse("{kind:'neighborhood',rootPartId:1,hops:1}")).SequenceEqual(new[]{1,2}));
        Reject("Unknown part rejected","part_not_found",()=>resolve(JObject.Parse("{kind:'parts',partIds:[99]}")));
        Reject("Missing selection rejected","selection_empty",()=>VisualScope.Resolve(JObject.Parse("{kind:'selected'}"),nodes,edges,null,null,20));
        Reject("Explicit branch boundary required","invalid_input",()=>resolve(JObject.Parse("{kind:'branch',rootPartId:3}")));
        Reject("Unknown edge rejected","connection_not_found",()=>resolve(JObject.Parse("{kind:'branch',rootPartId:3,stopConnectionKeys:['missing']}")));
        Reject("Cycle across cut rejected","scope_ambiguous",()=>VisualScope.Resolve(JObject.Parse("{kind:'branch',rootPartId:3,stopConnectionKeys:['b']}"),nodes,edges.Concat(new[]{new VisualScope.Edge{A=1,B=4,Key="d"}}).ToArray(),null,null,20));
        Reject("No silent truncation","scope_budget",()=>VisualScope.Resolve(JObject.Parse("{kind:'craft'}"),nodes,edges,null,null,2));
        Reject("Bad selector key","invalid_input",()=>resolve(JObject.Parse("{kind:'parts',partIds:[1],surprise:true}")));
        Reject("Boolean is not integer","invalid_input",()=>VisualScope.Integer(new JValue(true),"id"));
        Reject("Parallel camera vectors","invalid_view",()=>new VisualCore.View("x",new VisualCore.V(0,1,0),new VisualCore.V(0,2,0)));
        Reject("Nonfinite camera vector","invalid_view",()=>new VisualCore.View("x",new VisualCore.V(double.NaN,1,0),new VisualCore.V(0,2,0)));
        var mesh=new[]{Cube(101,0,-2,0,0,.5,.4,1),Cube(202,1,2,1,.5,.6,.2,1.5)};var views=new[]{"front","right","top","isometric"}.Select(VisualCore.NamedView).ToArray();
        string hash=VisualCore.GeometryHash(mesh);var result=VisualCore.Render(mesh,new[]{101,202},views,256,256,true,Manifest(),()=>false);
        Check("Four joint and eight detail views",result.Views.Count==12);
        Check("PNG artifact set includes raw color and IDs",result.Files.Count==37&&result.Files.ContainsKey("overview.png")&&result.Files.ContainsKey("front.raw.png"));
        Check("Joint views share scale",result.Views.Take(4).Select(p=>p.Value.Info.Value<double>("pixelsPerMetre")).Distinct().Count()==1);
        Check("Pick exact left physical group",Pick(result.Views["front"],new VisualCore.V(-2,0,0))==1);
        Check("Pick exact right physical group",Pick(result.Views["front"],new VisualCore.V(2,1,.5))==2);
        Check("Joint relation retains offset",result.Manifest["relations"][0]["deltaMetres"].Values<double>().SequenceEqual(new[]{4.0,1.0,.5}));
        Check("Detail scales explicitly distinct",result.Views["g1-front"].Info.Value<double>("pixelsPerMetre")>result.Views["front"].Info.Value<double>("pixelsPerMetre"));
        Check("Render never changes vertices",VisualCore.GeometryHash(mesh)==hash);
        var hidden=VisualCore.Render(new[]{Cube(1,0,0,0,0),Cube(2,1,0,0,3)},new[]{1,2},new[]{VisualCore.NamedView("front")},128,128,false,Manifest(),()=>false);
        Check("Z buffer picks nearer object",Pick(hidden.Views["front"],new VisualCore.V(0,0,3))==2);
        Check("Fully occluded part retained",hidden.Views["front"].Info["parts"].First(p=>p.Value<int>("partId")==1).Value<int>("visiblePixels")==0);
        var mirror=VisualCore.Render(new[]{Cube(1,0,0,0,0,-1,1,1)},new[]{1},new[]{VisualCore.NamedView("front")},128,128,false,Manifest(),()=>false);
        Check("Negative-scale winding remains visible",Pick(mirror.Views["front"],new VisualCore.V(0,0,0))==1);
        var missing=VisualCore.Render(new[]{Cube(1,0,0,0,0)},new[]{1,2},new[]{VisualCore.NamedView("front")},128,128,false,Manifest(),()=>false);
        Check("Missing mesh doesn't invent visible part",missing.Views["front"].Info["parts"].Count()==1);
        Reject("Cancellation stops renderer","cancelled",()=>VisualCore.Render(mesh,new[]{101,202},views,128,128,false,Manifest(),()=>true));
        Reject("Empty mesh fails clearly","no_geometry",()=>VisualCore.Render(new VisualCore.MeshData[0],new int[0],views,128,128,false,Manifest(),()=>false));
        mesh[0].Vertices[0]=new VisualCore.V(-5,-1,-1);Check("Geometry hash detects changed mesh",VisualCore.GeometryHash(mesh)!=hash);
        var dirty=Cube(1,0,0,0,0);dirty.Vertices[0]=new VisualCore.V(double.NaN,0,0);var clean=VisualCore.CleanMesh(dirty,out int removed);
        Check("Invalid native triangles explicitly counted",removed>0&&clean.Indices.Length==dirty.Indices.Length-removed*3);
        Check("Invalid vertices cannot poison finite bounds",clean.Vertices.All(v=>VisualCore.Finite(v.X))&&VisualCore.Finite(VisualCore.Bounds(new[]{clean}).Center.X));
        var small=new[]{Cube(1,0,-10,0,0,.2,.2,.2),Cube(2,1,10,0,0,.2,.2,.2)};
        var auto=VisualCore.Render(small,new[]{1,2},views,256,256,"auto",Manifest(),()=>false);
        Check("Auto detail recommends overview and both tiny groups",auto.Manifest["recommendedImages"].Count()==3&&auto.Views.Count==6);
        Check("Recommended files all exist",auto.Manifest["recommendedImages"].All(n=>auto.Files.ContainsKey((string)n)));
        Check("Cross-capture zoom policy explicit",(string)auto.Manifest["scalePolicy"]=="fit_scope_each_capture"&&((string)auto.Manifest["comparisonGuidance"]).Contains("pixelsPerMetre"));
        var none=VisualCore.Render(small,new[]{1,2},views,256,256,"none",Manifest(),()=>false);
        Check("None reports missing details without inventing files",none.Manifest["recommendedImages"].Count()==1&&none.Manifest["detailStatus"].All(s=>(string)s["status"]=="disabled"));
        var per=VisualCore.Render(small,new[]{1,2},views,256,256,"perGroup",Manifest(),()=>false);
        Check("Explicit perGroup preserves all views but recommends useful ones",per.Views.Count==12&&per.Manifest["recommendedImages"].Count()==3);
        var noNeed=VisualCore.Render(new[]{Cube(1,0,0,0,0)},new[]{1},views,384,384,"auto",Manifest(),()=>false);
        Check("Large readable group does not generate unnecessary detail",noNeed.Views.Count==4&&noNeed.Manifest["recommendedImages"].Count()==1);
        var occluded=VisualCore.Render(new[]{Cube(1,0,0,0,0),Cube(2,1,0,0,3)},new[]{1,2},new[]{VisualCore.NamedView("front")},256,256,"auto",Manifest(),()=>false);
        Check("Occluded group receives isolated detail",occluded.Manifest["imageRecommendations"].Any(x=>(string)x["reason"]=="occluded_in_joint_views"));
        var sevenViews=new[]{"front","right","top","isometric","back","left","bottom"}.Select(VisualCore.NamedView).ToArray();
        var budget=VisualCore.Render(small,new[]{1,2},sevenViews,1024,1024,"auto",Manifest(),()=>false);
        Check("Auto budget skip preserves overview and explains missing details",budget.Views.Count==7&&budget.Manifest["detailStatus"].All(s=>(string)s["status"]=="budget_exceeded")&&budget.Manifest["recommendedImages"].Count()==1);
        string autoPath=Path.Combine(args[0],"auto-small");Directory.CreateDirectory(autoPath);
        foreach(var file in auto.Files)File.WriteAllBytes(Path.Combine(autoPath,file.Key),file.Value);
        File.WriteAllText(Path.Combine(autoPath,"manifest.json"),auto.Manifest.ToString());
        Directory.CreateDirectory(args[0]);foreach(var file in result.Files)File.WriteAllBytes(Path.Combine(args[0],file.Key),file.Value);File.WriteAllText(Path.Combine(args[0],"manifest.json"),result.Manifest.ToString());
        Console.WriteLine("Visual checks: "+passed);
    }
}
