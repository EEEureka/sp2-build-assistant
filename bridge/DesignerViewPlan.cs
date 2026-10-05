using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using V = SP2BuildAssistant.VisualCore.V;

namespace SP2BuildAssistant
{
    // Pure view planning: no scene changes, suitable for validation before rendering.
    internal static class DesignerViewPlan
    {
        internal sealed class Pose
        {
            public V Position, Forward, Up, Target;
            public bool Orthographic;
            public double FieldOfView, OrthographicSize, Near, Far;
        }
        internal sealed class View
        {
            public string Name, Preset;
            public Pose Camera;
            public bool AutoDistance, AutoSize;
        }
        private static double Number(JObject a,string key,double fallback,double min,double max)
        {
            if(a[key]==null)return fallback;
            if(a[key].Type!=JTokenType.Integer&&a[key].Type!=JTokenType.Float)throw new ApiError("invalid_input",key+" requires a number.");
            double n=a[key].Value<double>();
            if(!VisualCore.Finite(n)||n<min||n>max)throw new ApiError("invalid_input",key+" is outside "+min+".."+max+".");
            return n;
        }
        private static V Vector(JToken token)
        {
            var a=token as JArray;
            if(a==null||a.Count!=3||a.Any(x=>x.Type!=JTokenType.Integer&&x.Type!=JTokenType.Float))throw new ApiError("invalid_input","target needs three world-space numbers.");
            var v=new V(a[0].Value<double>(),a[1].Value<double>(),a[2].Value<double>());
            if(!VisualCore.Finite(v.X)||!VisualCore.Finite(v.Y)||!VisualCore.Finite(v.Z)||Math.Max(Math.Max(Math.Abs(v.X),Math.Abs(v.Y)),Math.Abs(v.Z))>100000)throw new ApiError("invalid_input","target coordinates must be finite and within 100000 metres.");
            return v;
        }
        internal static View[] Plan(JArray specs,Pose current,VisualCore.Box bounds,int width,int height)
        {
            if(specs==null||specs.Count<1||specs.Count>8)throw new ApiError("invalid_input","views needs 1..8 entries.");
            // Include the duplicate first-image overview in the download/render budget.
            if((long)width*height*(specs.Count+1)>16000000)throw new ApiError("render_budget","Screenshot budget is 16 million pixels, including overview.");
            var output=specs.Select(token=>{
                JObject a=token.Type==JTokenType.String?new JObject{["view"]=token.DeepClone()}:token as JObject;
                VisualScope.Keys(a,"name","view","projection","target","azimuthDegrees","elevationDegrees","rollDegrees","distance","fieldOfViewDegrees","orthographicSize","position","direction","up","nearClipMetres","farClipMetres");
                string preset=VisualScope.String(a["view"],"view","current"),name=VisualScope.String(a["name"],"name",preset);
                VisualCore.ValidateViewName(name);
                string projection=VisualScope.String(a["projection"],"projection","current");
                if(!new[]{"current","perspective","orthographic"}.Contains(projection))throw new ApiError("invalid_input","projection must be current, perspective or orthographic.");
                bool ortho=projection=="current"?current.Orthographic:projection=="orthographic";
                if(a["orthographicSize"]!=null&&!ortho)throw new ApiError("invalid_input","orthographicSize requires orthographic projection.");
                double fov=Number(a,"fieldOfViewDegrees",current.FieldOfView,5,140);
                V target=current.Target,forward=current.Forward,up=current.Up,position=current.Position;
                bool autoDistance=false,autoSize=false;
                double size=Number(a,"orthographicSize",current.OrthographicSize,.01,10000);
                double near=current.Near,far=current.Far;
                if(preset=="fixed"){
                    if(projection=="current"||new[]{"position","direction","up","target","fieldOfViewDegrees","nearClipMetres","farClipMetres"}.Any(k=>a[k]==null)||(ortho&&a["orthographicSize"]==null))throw new ApiError("invalid_input","fixed requires explicit pose, projection, FOV and clipping; orthographic also requires size.");
                    if(new[]{"azimuthDegrees","elevationDegrees","rollDegrees","distance"}.Any(k=>a[k]!=null))throw new ApiError("invalid_input","fixed does not auto-fit or apply orbit angles.");
                    position=Vector(a["position"]);var basis=new VisualCore.View(name,Vector(a["direction"]),Vector(a["up"]));forward=basis.Forward;up=basis.Up;target=Vector(a["target"]);
                    near=Number(a,"nearClipMetres",.01,ortho?-100000:.001,10000);far=Number(a,"farClipMetres",1000,.01,100000);if(far<=near)throw new ApiError("invalid_input","farClipMetres must exceed nearClipMetres.");
                }else if(new[]{"position","direction","up","nearClipMetres","farClipMetres"}.Any(k=>a[k]!=null))throw new ApiError("invalid_input","Explicit camera vectors and clips require view=fixed.");
                else if(preset=="current"){
                    if(new[]{"target","azimuthDegrees","elevationDegrees","rollDegrees","distance"}.Any(k=>a[k]!=null))throw new ApiError("invalid_input","Use a named view or custom view to change camera pose.");
                    // Preserve apparent scale when switching the current camera's projection.
                    if(ortho&&!current.Orthographic&&a["orthographicSize"]==null)size=Math.Max(.01,Math.Sqrt((target-position).Dot(target-position))*Math.Tan(fov*Math.PI/360));
                    if(!ortho)near=Math.Max(.01,near);
                } else {
                    if(preset=="custom"){
                        if(a["azimuthDegrees"]==null||a["elevationDegrees"]==null)throw new ApiError("invalid_input","custom needs azimuthDegrees and elevationDegrees.");
                        double az=Number(a,"azimuthDegrees",0,-360,360)*Math.PI/180,el=Number(a,"elevationDegrees",0,-89.9,89.9)*Math.PI/180;
                        forward=new V(-Math.Sin(az)*Math.Cos(el),-Math.Sin(el),-Math.Cos(az)*Math.Cos(el));
                        var basis=new VisualCore.View(name,forward,new V(0,1,0));up=basis.Up;
                    } else {
                        if(a["azimuthDegrees"]!=null||a["elevationDegrees"]!=null)throw new ApiError("invalid_input","Angles require view=custom.");
                        var named=VisualCore.NamedView(preset);forward=named.Forward;up=named.Up;
                    }
                    double roll=Number(a,"rollDegrees",0,-180,180)*Math.PI/180;
                    up=up*Math.Cos(roll)+forward.Cross(up)*Math.Sin(roll);
                    target=a["target"]==null?bounds.Center:Vector(a["target"]);
                    // A sphere enclosing every focus AABB corner also covers an off-centre target.
                    double radius=0;
                    foreach(double x in new[]{bounds.Min.X,bounds.Max.X})foreach(double y in new[]{bounds.Min.Y,bounds.Max.Y})foreach(double z in new[]{bounds.Min.Z,bounds.Max.Z}){
                        var delta=new V(x,y,z)-target;radius=Math.Max(radius,Math.Sqrt(delta.Dot(delta)));
                    }
                    radius=Math.Max(.05,radius);
                    double aspect=(double)width/height,halfV=fov*Math.PI/360,halfH=Math.Atan(Math.Tan(halfV)*aspect);
                    double fitDistance=radius/Math.Sin(Math.Min(halfV,halfH))*1.1;
                    double distance=Number(a,"distance",fitDistance,.05,10000);autoDistance=a["distance"]==null;
                    if(distance+radius>100000)throw new ApiError("render_budget","Camera distance/scene bounds exceed screenshot range.");
                    position=target-forward*distance;
                    if(a["orthographicSize"]==null){size=radius*1.1/Math.Min(1,aspect);autoSize=ortho;}
                    near=.01;far=Math.Max(1000,distance+radius*2+10);
                }
                return new View{Name=name,Preset=preset,AutoDistance=autoDistance,AutoSize=autoSize,Camera=new Pose{Position=position,Forward=forward,Up=up,Target=target,Orthographic=ortho,FieldOfView=fov,OrthographicSize=size,Near=near,Far=far}};
            }).ToArray();
            if(output.Select(v=>v.Name).Distinct().Count()!=output.Length)throw new ApiError("invalid_input","View names must be unique; name custom views explicitly.");
            return output;
        }
    }
}
