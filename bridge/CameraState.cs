using System;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // State comparison is independent of Unity. Tolerances are absolute, never
    // proportional to camera distance; object identities and modes remain exact.
    internal static class CameraState
    {
        internal const double PositionTolerance = .0001;
        internal const double AngleToleranceDegrees = .001;
        internal const double ScalarTolerance = .000001;

        internal static double QuaternionAngle(JArray a, JArray b)
        {
            double na=Math.Sqrt(a.Sum(x=>Math.Pow((double)x,2))),nb=Math.Sqrt(b.Sum(x=>Math.Pow((double)x,2)));
            if(na==0||nb==0)return double.PositiveInfinity;
            double plus=0,minus=0;
            for(int i=0;i<4;i++){double x=(double)a[i]/na,y=(double)b[i]/nb;plus+=(x-y)*(x-y);minus+=(x+y)*(x+y);}
            return 4*Math.Asin(Math.Min(1,Math.Sqrt(Math.Min(plus,minus))/2))*180/Math.PI;
        }
        internal static JArray Compare(JObject before,JObject after)
        {
            var diffs=new JArray();
            foreach(string key in before.Properties().Select(p=>p.Name).Union(after.Properties().Select(p=>p.Name))){
                var a=before[key];var b=after[key];
                if(JToken.DeepEquals(a,b))continue;
                double tolerance=ScalarTolerance,error=double.PositiveInfinity;
                string metric="absolute";
                if(a!=null&&b!=null){
                    if(key.EndsWith("Quaternion")){error=QuaternionAngle((JArray)a,(JArray)b);tolerance=AngleToleranceDegrees;metric="degrees";}
                    else if(key.EndsWith("Position",StringComparison.OrdinalIgnoreCase)||key.EndsWith("PositionWorld",StringComparison.OrdinalIgnoreCase)||key=="targetWorld"){
                        error=Math.Sqrt(((JArray)a).Select((x,i)=>Math.Pow((double)x-(double)b[i],2)).Sum());tolerance=PositionTolerance;metric="metres";
                    }else if(a.Type==JTokenType.Float&&b.Type==JTokenType.Float){error=Math.Abs((double)a-(double)b);}
                    else if(a is JArray && b is JArray && ((JArray)a).Count==((JArray)b).Count){
                        var aa=((JContainer)a).Descendants().OfType<JValue>().ToArray();var bb=((JContainer)b).Descendants().OfType<JValue>().ToArray();
                        if(aa.Length==bb.Length&&aa.All(x=>x.Type==JTokenType.Float||x.Type==JTokenType.Integer)&&bb.All(x=>x.Type==JTokenType.Float||x.Type==JTokenType.Integer))
                            error=aa.Select((x,i)=>Math.Abs((double)x-(double)bb[i])).DefaultIfEmpty(0).Max();
                    }
                }
                bool strict=key.EndsWith("InstanceId")||key=="enabled"||key=="projection"||key=="cullingMask"||key=="clearFlags";
                if(strict){error=double.PositiveInfinity;tolerance=0;metric="exact";}
                diffs.Add(new JObject{["field"]=key,["before"]=a?.DeepClone(),["after"]=b?.DeepClone(),["metric"]=metric,
                    ["error"]=double.IsInfinity(error)?(JToken)null:error,["tolerance"]=tolerance,["withinTolerance"]=!double.IsNaN(error)&&error<=tolerance});
            }
            return diffs;
        }
        internal static bool Passed(JArray differences){return differences.All(x=>(bool)x["withinTolerance"]);}
    }
}
