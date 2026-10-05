using System;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
class CameraStateTests
{
    static int count;
    static void Check(bool ok,string name){if(!ok)throw new Exception(name);count++;}
    static JObject State(){return JObject.Parse("{positionWorld:[1,2,3],rotationQuaternion:[0,0,0,1],aspect:1.6,projection:'perspective',targetTextureInstanceId:0,enabled:true,projectionRows:[[1,0],[0,1]]}");}
    static void Main(){try{Run();}catch(Exception e){Console.WriteLine("FAIL: "+e.GetType().FullName+" "+e.Message);Environment.Exit(1);}}
    static void Run(){
        var a=State();var b=(JObject)a.DeepClone();Check(CameraState.Passed(CameraState.Compare(a,b)),"identity");
        b["rotationQuaternion"]=new JArray(0,0,0,-1);Check(CameraState.Passed(CameraState.Compare(a,b)),"quaternion double cover");
        b["positionWorld"][0]=1.00009;Check(CameraState.Passed(CameraState.Compare(a,b)),"sub tolerance position");
        b["positionWorld"][1]=2.00009;Check(!CameraState.Passed(CameraState.Compare(a,b)),"euclidean position not per axis");
        b=State();b["aspect"]=1.600002;Check(!CameraState.Passed(CameraState.Compare(a,b)),"aspect change detected");
        b=State();b["targetTextureInstanceId"]=1;Check(!CameraState.Passed(CameraState.Compare(a,b)),"reference strict");
        b=State();b["enabled"]=false;Check(!CameraState.Passed(CameraState.Compare(a,b)),"boolean strict");
        b=State();b["projectionRows"][0][0]=1.000002;Check(!CameraState.Passed(CameraState.Compare(a,b)),"matrix change");
        b=State();b.Remove("enabled");Check(!CameraState.Passed(CameraState.Compare(a,b)),"missing field");
        b=State();b["rotationQuaternion"]=new JArray(0,0,Math.Sin(.002*Math.PI/360),Math.Cos(.002*Math.PI/360));
        Check(!CameraState.Passed(CameraState.Compare(a,b)),"angular tolerance");
        Console.WriteLine("Camera state: "+count+" passed.");
    }
}
