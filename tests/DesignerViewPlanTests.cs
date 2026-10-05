using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
namespace SP2BuildAssistant {internal sealed class ApiError:Exception{public string Code;public ApiError(string code,string message):base(message){Code=code;}}}
class DesignerViewPlanTests
{
    static int passed;
    static void Check(string name,bool test){if(!test)throw new Exception(name);Console.WriteLine("PASS "+name);passed++;}
    static void Reject(string name,Action test){try{test();}catch(ApiError){Check(name,true);return;}throw new Exception(name+" unexpectedly accepted");}
    static void Main(){
        var p=new DesignerViewPlan.Pose{Position=new VisualCore.V(0,0,20),Target=new VisualCore.V(0,0,0),Forward=new VisualCore.V(0,0,-1),Up=new VisualCore.V(0,1,0),FieldOfView=60,OrthographicSize=10,Near=.1,Far=1000};
        var b=new VisualCore.Box();b.Add(new VisualCore.V(-5,-1,-3));b.Add(new VisualCore.V(5,1,3));
        Func<string,DesignerViewPlan.View[]> plan=s=>DesignerViewPlan.Plan(JArray.Parse(s),p,b,1280,720);
        var current=plan("['current']")[0];Check("Current view preserves pose and projection",current.Camera.Position.Z==20&&!current.Camera.Orthographic&&!current.AutoDistance);
        var views=plan("[{view:'front',projection:'orthographic'},{view:'right'},{view:'top'},{view:'custom',azimuthDegrees:90,elevationDegrees:0}]");
        Check("Named front camera is on nose +Z",views[0].Camera.Position.Z>0&&views[0].Camera.Forward.Z==-1&&views[0].Camera.Orthographic);
        Check("Right and azimuth 90 agree",Math.Abs(views[1].Camera.Position.X-views[3].Camera.Position.X)<1e-8&&Math.Abs(views[3].Camera.Forward.Z)<1e-8);
        Check("Top camera uses +Z as up",views[2].Camera.Forward.Y==-1&&views[2].Camera.Up.Z==1);
        var ortho=plan("[{view:'current',projection:'orthographic'}]")[0];Check("Projection switch preserves scale at target",Math.Abs(ortho.Camera.OrthographicSize-20*Math.Tan(Math.PI/6))<1e-8);
        var exact=plan("[{view:'custom',azimuthDegrees:0,elevationDegrees:30,target:[1,2,3],distance:10,projection:'perspective',fieldOfViewDegrees:45}]")[0].Camera;
        Check("Explicit target and distance",Math.Abs(exact.Position.Y-7)<1e-8&&Math.Abs(exact.Position.Z-(3+Math.Sqrt(75)))<1e-8&&exact.FieldOfView==45);
        var portrait=DesignerViewPlan.Plan(new JArray("front"),p,b,256,1024)[0];
        Check("Portrait auto-fit grows camera distance",portrait.Camera.Position.Z>views[1].Camera.Position.X*2);
        var off=plan("[{view:'front',target:[30,0,0]}]")[0];Check("Off-centre auto fit contains focus bounds",off.Camera.Position.Z>60);
        Reject("Duplicate filenames",()=>plan("['front','front']"));
        Reject("Current pose overrides rejected",()=>plan("[{view:'current',distance:4}]"));
        Reject("Missing custom angle",()=>plan("[{view:'custom',azimuthDegrees:40}]"));
        Reject("Angles on named view rejected",()=>plan("[{view:'front',azimuthDegrees:40}]"));
        Reject("Parallel up at pole rejected",()=>plan("[{view:'custom',azimuthDegrees:40,elevationDegrees:90}]"));
        Reject("Wrong projection field",()=>plan("[{view:'front',projection:'perspective',orthographicSize:2}]"));
        Reject("Nonfinite target",()=>plan("[{view:'front',target:[NaN,0,0]}]"));
        Reject("Unknown option",()=>plan("[{view:'front',teleport:true}]"));
        Reject("Path traversal filename",()=>plan("[{view:'front',name:'../evil'}]"));
        Reject("Memory budget before rendering",()=>DesignerViewPlan.Plan(new JArray("front","right","top","back"),p,b,2048,2048));
        Console.WriteLine(passed+" designer view planning tests passed.");
    }
}
