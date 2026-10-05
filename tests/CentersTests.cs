using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
namespace SP2BuildAssistant { internal sealed class ApiError:Exception { public string Code; public ApiError(string code,string message):base(message){Code=code;} } }
class CentersTests
{
    static int count;
    static void Check(string name,bool ok){if(!ok)throw new Exception(name);count++;Console.WriteLine("PASS "+name);}
    static bool Near(double a,double b){return Math.Abs(a-b)<1e-8;}
    static JObject Metadata()
    {
        return JObject.Parse(@"{identity:{craftSessionId:'test-session',revision:1,fingerprint:'test',fingerprintAlgorithm:'sha256',gameVersion:'test',xmlVersion:25,stateUncertain:false},analysisId:'synthetic-test-only',capturedAt:'2026-10-02T00:00:00Z',capturedFrame:1,geometryStamp:'test',staleAtDelivery:false,
          basis:{mode:'native_designer',loadCondition:'current_editor_configuration',liftProjectionAxisWorld:[0,1,0],scopePolicy:'native',aircraftOrientationWorld:[0,0,0,1],massConversion:'native / 0.01',gameVersion:'test'},
          frame:{kind:'world',partId:null,referenceToken:null,orientationWorld:[0,0,0,1],frameToWorldRows:[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],axisLabels:['right','up','forward'],orientationBasis:'convention',meaning:'test'},
          scope:{assemblyPartCount:4,connectedPartCount:4,disconnectedPartCount:0,connectedPartIds:[1,2,3,4],meaning:'test'},focus:{status:'all',partIds:null,meaning:'test'},warnings:[]}");
    }
    static JObject Row(int id,string metric,double weight,double x,double y,double z)
    {return new JObject{["part"]=new JObject{["id"]=id,["type"]="test",["typeName"]="Synthetic",["name"]="Synthetic"},["sourceId"]=id+"/"+metric,["metric"]=metric,["nativeWeight"]=weight,["positionWorldMeters"]=new JArray(x,y,z),["positionFrameMeters"]=new JArray(x,y,z),["included"]=true,["reasonCodes"]=new JArray(),["weightMeaning"]="test",["activeInHierarchy"]=true,["connectedToMainCockpit"]=true};}
    static JArray Rows(){return new JArray(Row(1,"mass",1,10,0,0),Row(2,"mass",3,14,0,0),Row(3,"lift",2,13,.25,-.4),Row(4,"thrust",1000,13,-.12,-2));}
    static JObject Build(JArray rows=null,JObject opts=null,int[] focus=null){return CentersCore.Build(Metadata(),rows??Rows(),opts??new JObject(),focus);}
    static void Save(string directory,string name,JObject report){File.WriteAllText(Path.Combine(directory,name+".json"),new JObject{["success"]=true,["schemaVersion"]="1",["data"]=report}.ToString());}
    static void Main(string[] args)
    {
        string output=args[0];Directory.CreateDirectory(output);
        var report=Build();Save(output,"summary",report);
        Check("Weighted COM uses mass and true positions",Near(report["centers"]["com"]["positionFrameMeters"][0].Value<double>(),13));
        Check("CoL relative signed axes",Near(report["relations"]["colFromCom"]["deltaFrameMeters"][2].Value<double>(),-.4)&&(string)report["relations"]["colFromCom"]["axisRelation"][2]=="aft");
        Check("All three pairwise relations",Near(report["relations"]["cotFromCol"]["deltaFrameMeters"][1].Value<double>(),-.37));
        Check("Summary excludes contributor payload",report["contributors"]["items"].Count()==0&&report["contributors"].Value<int>("total")==4);
        Check("No fabricated stability assessment",(string)report["assessment"]["longitudinalStaticStability"]["status"]=="not_assessed"&&report["assessment"]["thrustMoment"]["momentNm"].Type==JTokenType.Null);
        var page=Build(null,JObject.Parse("{detail:'contributors',metric:'mass',limit:1}"));Save(output,"contributors",page);
        Check("Contributor paging total and next offset",page["contributors"].Value<int>("total")==2&&page["contributors"].Value<int>("returned")==1&&page["contributors"].Value<int>("nextOffset")==1);
        var focus=Build(null,JObject.Parse("{detail:'contributors'}"),new[]{1});
        Check("Focus preserves whole-aircraft denominator",Near(focus["contributors"]["items"][0].Value<double>("massFraction"),.25)&&Near(focus["centers"]["com"].Value<double>("massKg"),4));
        Check("Mass moment uses offset from COM",Near(focus["contributors"]["items"][0]["massMomentAboutComKgM"][0].Value<double>(),-3));
        var empty=Build(new JArray());Save(output,"empty",empty);
        Check("Unavailable centers are null not origin",empty["centers"]["com"]["positionFrameMeters"].Type==JTokenType.Null&&empty["relations"]["cotFromCom"].Type==JTokenType.Null);
        Check("No selection still retains whole aircraft centers",JToken.DeepEquals(Build(null,null,new int[0])["centers"],report["centers"]));
        var invalid=Rows();invalid.Add(Row(5,"mass",double.NaN,1,2,3));var partial=Build(invalid);Save(output,"partial",partial);
        Check("Nonfinite contribution excludes and marks partial",(string)partial["centers"]["com"]["status"]=="partial"&&Near(partial["centers"]["com"].Value<double>("massKg"),4));
        var negative=Build(new JArray(Row(1,"mass",-1,5,0,0)));
        Check("Negative-only mass unavailable",(string)negative["centers"]["com"]["status"]=="unavailable");
        var zero=Build(new JArray(Row(1,"lift",0,100,0,0)));
        Check("Zero wing weight unavailable",zero["centers"]["col"]["positionFrameMeters"].Type==JTokenType.Null);
        var badPosition=Rows();badPosition[0]["positionFrameMeters"]=new JArray(0,double.PositiveInfinity,0);var b=Build(badPosition);
        Check("Bad position cannot poison valid center",Near(b["centers"]["com"]["positionFrameMeters"][0].Value<double>(),14));
        var moved=Rows();foreach(JObject r in moved){r["positionFrameMeters"][0]=r["positionFrameMeters"][0].Value<double>()+20;r["positionWorldMeters"]=r["positionFrameMeters"].DeepClone();}
        var translated=Build(moved);var comparison=CentersCore.Compare(report,translated);translated["comparison"]=comparison;Save(output,"comparison",translated);
        Check("Common translation is not relation change",Near(comparison["relativeChanges"]["colFromCom"]["deltaMeters"][0].Value<double>(),0)&&Near(comparison["centerChanges"]["com"]["deltaMeters"][0].Value<double>(),20));
        var another=(JObject)report.DeepClone();another["identity"]["craftSessionId"]="different";
        Check("Cross-session compare rejected",(string)CentersCore.Compare(report,another)["status"]=="not_comparable");
        another=(JObject)report.DeepClone();another["frame"]["referenceToken"]="new-part-same-id";
        Check("Recycled frame reference rejected",(string)CentersCore.Compare(report,another)["status"]=="not_comparable");
        another=(JObject)report.DeepClone();another["basis"]["aircraftOrientationWorld"]=new JArray(0,1,0,0);
        Check("Aircraft rotation changes projection basis",(string)CentersCore.Compare(report,another)["status"]=="not_comparable");
        another=(JObject)report.DeepClone();another["calculationVersion"]="different";var rejected=CentersCore.Compare(another,report);another=(JObject)report.DeepClone();another["comparison"]=rejected;Save(output,"not-comparable",another);
        Check("Calculation version changed rejected",(string)rejected["status"]=="not_comparable");
        Check("Null relationships compare without exception",CentersCore.Compare(empty,empty)["relativeChanges"]["colFromCom"]["deltaMeters"].Type==JTokenType.Null);
        var vertices=new[]{new VisualCore.V(8,-.5,-4),new VisualCore.V(18,-.5,-4),new VisualCore.V(13,.5,4),new VisualCore.V(13,-.5,4)};
        var mesh=new VisualCore.MeshData{PartId=1,Group=0,Vertices=vertices,Indices=new[]{0,1,2,0,2,3}};
        var view=VisualCore.NamedView("right");long work=0;var img=VisualCore.Raster(new[]{mesh},new[]{1},new Dictionary<int,int>{{1,1}},view,new VisualCore.V(13,0,0),50,640,640,()=>{},ref work,report);
        var idCopy=(int[])img.Ids.Clone();var rawCopy=(byte[])img.RawPixels.Clone();VisualCore.DrawCenters(img,report,view,new VisualCore.V(13,0,0),50);
        Check("Centers do not alter surface pick IDs or raw image",idCopy.SequenceEqual(img.Ids)&&rawCopy.SequenceEqual(img.RawPixels));
        var com=img.Info["centersOverlay"]["markers"].First(m=>(string)m["center"]=="com");
        Check("Projected center pixel matches frame transform",Near(com["pixel"][0].Value<double>(),320)&&Near(com["pixel"][1].Value<double>(),320));
        var manifest=new JObject{["groups"]=new JArray(new JObject{["index"]=0,["name"]="Synthetic mesh"}),["centersReport"]=report.DeepClone()};
        var rendered=VisualCore.Render(new[]{mesh},new[]{1},new[]{VisualCore.NamedView("right"),VisualCore.NamedView("top"),VisualCore.NamedView("front")},640,640,"none",manifest,()=>false);
        foreach(var file in rendered.Files)File.WriteAllBytes(Path.Combine(output,file.Key),file.Value);File.WriteAllText(Path.Combine(output,"manifest.json"),rendered.Manifest.ToString());
        Check("Small center separation recommends three detail planes",rendered.Manifest["recommendedImages"].Count()==4);
        Check("Image report uses copied mesh geometry stamp",(string)rendered.Manifest["centersReport"]["geometryStamp"]==(string)rendered.Manifest["geometryStamp"]);
        var withImages=(JObject)rendered.Manifest["centersReport"].DeepClone();
        withImages["visual"]=new JObject{["identity"]=report["identity"].DeepClone(),["captureId"]="00000000000000000000000000000001",["geometryStamp"]=rendered.Manifest["geometryStamp"].DeepClone(),["complete"]=true,["staleAtDelivery"]=false,["artifactBase"]="v1/visual/00000000000000000000000000000001/",
            ["files"]=new JArray(rendered.Files.Select(f=>new JObject{["name"]=f.Key,["bytes"]=f.Value.Length,["sha256"]=VisualCore.Hash(f.Value)})),["recommendedImages"]=rendered.Manifest["recommendedImages"].DeepClone(),["imageRecommendations"]=rendered.Manifest["imageRecommendations"].DeepClone(),["detailStatus"]=rendered.Manifest["detailStatus"].DeepClone(),["scalePolicy"]=rendered.Manifest["scalePolicy"].DeepClone(),["comparisonGuidance"]=rendered.Manifest["comparisonGuidance"].DeepClone(),["exclusions"]=new JArray(),["warnings"]=new JArray(),["retention"]="test"};Save(output,"with-images",withImages);
        var far=(JObject)report.DeepClone();far["centers"]["cot"]["positionFrameMeters"]=new JArray(13,0,1000);
        var farManifest=new JObject{["groups"]=new JArray(new JObject{["index"]=0,["name"]="A"}),["centersReport"]=far};
        var distant=VisualCore.Render(new[]{mesh},new[]{1},new[]{VisualCore.NamedView("right")},384,384,"none",farManifest,()=>false);
        var cot=distant.Views["right"].Info["centersOverlay"]["markers"].First(m=>(string)m["center"]=="cot");
        Check("Center outside aircraft stays inside overview",cot["pixel"].Values<double>().All(v=>v>=0&&v<384));
        Check("Distant center adds readable aircraft context",distant.Manifest["recommendedImages"].Values<string>().Contains("centers-aircraft-context.png"));
        var unavailable=(JObject)report.DeepClone();unavailable["centers"]["cot"]["positionFrameMeters"]=null;unavailable["centers"]["cot"]["status"]="unavailable";
        work=0;img=VisualCore.Raster(new[]{mesh},new[]{1},new Dictionary<int,int>{{1,1}},view,new VisualCore.V(13,0,0),50,640,640,()=>{},ref work,unavailable);VisualCore.DrawCenters(img,unavailable,view,new VisualCore.V(13,0,0),50);
        Check("Unavailable center has no origin marker",img.Info["centersOverlay"]["markers"].Count()==2);
        Console.WriteLine("Centers tests passed: "+count);
    }
}
