using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using V=SP2BuildAssistant.VisualCore.V;

namespace SP2BuildAssistant
{
    internal static class SectionMeasure
    {
        internal sealed class Segment {internal V A,B,Normal;internal int PartId;}
        internal sealed class Result {internal List<Segment> Segments=new List<Segment>();internal int CoplanarTriangles,DegenerateTriangles;}
        internal static Result Cut(GeometryMeasure.Triangle[] triangles,V origin,V normal,V? regionMin=null,V? regionMax=null)
        {
            normal=normal.Unit();var result=new Result();foreach(var t in triangles){var points=new[]{t.A,t.B,t.C};var d=points.Select(v=>(v-origin).Dot(normal)).ToArray();
                if(d.All(x=>Math.Abs(x)<1e-9)){result.CoplanarTriangles++;continue;}var intersections=new List<V>();
                for(int i=0;i<3;i++){int j=(i+1)%3;if(Math.Abs(d[i])<1e-9)intersections.Add(points[i]);if(d[i]*d[j]<0)intersections.Add(points[i]+(points[j]-points[i])*(d[i]/(d[i]-d[j])));}
                var unique=new List<V>();foreach(var p in intersections)if(unique.All(x=>GeometryMeasure.Length(p-x)>1e-9))unique.Add(p);
                if(unique.Count!=2){if(unique.Count>2)result.DegenerateTriangles++;continue;}V a=unique[0],b=unique[1];
                if(regionMin.HasValue&&!Clip(ref a,ref b,regionMin.Value,regionMax.Value))continue;
                if(GeometryMeasure.Length(a-b)>1e-9)result.Segments.Add(new Segment{A=a,B=b,Normal=t.Normal,PartId=t.PartId});}
            return result;
        }
        private static double Component(V v,int axis){return axis==0?v.X:axis==1?v.Y:v.Z;}
        private static bool Clip(ref V a,ref V b,V min,V max)
        {
            var delta=b-a;double low=0,high=1;for(int axis=0;axis<3;axis++){double p=Component(a,axis),d=Component(delta,axis),lo=Component(min,axis),hi=Component(max,axis);if(Math.Abs(d)<1e-15){if(p<lo||p>hi)return false;continue;}double x=(lo-p)/d,y=(hi-p)/d;if(x>y){double temp=x;x=y;y=temp;}low=Math.Max(low,x);high=Math.Min(high,y);if(low>high)return false;}b=a+delta*high;a=a+delta*low;return true;
        }
        internal static JObject Report(Result r,int limit){return new JObject{["segmentCount"]=r.Segments.Count,["totalLengthMetres"]=r.Segments.Sum(s=>GeometryMeasure.Length(s.B-s.A)),["coplanarTrianglesExcluded"]=r.CoplanarTriangles,["degenerateTrianglesExcluded"]=r.DegenerateTriangles,["truncated"]=r.Segments.Count>limit,["segments"]=new JArray(r.Segments.Take(limit).Select(s=>new JObject{["a"]=s.A.Json(),["b"]=s.B.Json(),["normal"]=s.Normal.Json(),["partId"]=s.PartId})),["interpretation"]="Unordered mesh-plane intersection segments; no closed-solid/interior inference. Coplanar faces are explicitly excluded."};}
        internal static JObject Seam(Result a,Result b,double step,int limit,Action cancel=null)
        {
            if(a.Segments.Count==0||b.Segments.Count==0)throw new ApiError("empty_section","Both groups must intersect the requested plane/region.");
            long projected=a.Segments.Concat(b.Segments).Sum(s=>(long)Math.Ceiling(GeometryMeasure.Length(s.B-s.A)/step)+1);
            if(projected>20000||projected*Math.Max(a.Segments.Count,b.Segments.Count)>20000000)throw new ApiError("measurement_budget","Reduce the seam region or increase sampleSpacingMetres.");
            double sum=0,max=-1,maxAngle=0;int samples=0;var witnesses=new List<JObject>();
            Action<Result,Result,string> sample=(source,target,label)=>{foreach(var s in source.Segments){cancel?.Invoke();int steps=Math.Max(1,(int)Math.Ceiling(GeometryMeasure.Length(s.B-s.A)/step));for(int i=0;i<=steps;i++){
                var p=s.A+(s.B-s.A)*((double)i/steps);double best=double.PositiveInfinity;V q=new V();Segment closest=null;
                foreach(var t in target.Segments){var candidate=GeometryMeasure.SegmentPoint(p,t.A,t.B);double distance=(candidate-p).Dot(candidate-p);if(distance<best){best=distance;q=candidate;closest=t;}}
                double d=Math.Sqrt(best);double angle=Math.Acos(Math.Max(-1,Math.Min(1,Math.Abs(s.Normal.Dot(closest.Normal)))))*180/Math.PI;maxAngle=Math.Max(maxAngle,angle);sum+=best;samples++;
                var witness=new JObject{["direction"]=label,["point"]=p.Json(),["nearest"]=q.Json(),["distanceMetres"]=d,["normalAngleDegrees"]=angle,["partId"]=s.PartId,["otherPartId"]=closest.PartId};
                if(d>max){max=d;witnesses.Insert(0,witness);}else if(witnesses.Count<limit)witnesses.Add(witness);if(witnesses.Count>limit)witnesses.RemoveAt(witnesses.Count-1);
            }}};sample(a,b,"A_to_B");sample(b,a,"B_to_A");
            return new JObject{["sampledMaxMetres"]=max,["rmsMetres"]=Math.Sqrt(sum/samples),["sampleCount"]=samples,["sampleSpacingMetres"]=step,["maxUnorientedNormalAngleDegrees"]=maxAngle,["witnesses"]=new JArray(witnesses),["continuousUpperBound"]=null,["meaning"]="Bidirectional sampled distances between clipped plane intersection segments. Max is sampled, not a proof for the continuous surface. Normal angles ignore winding sign."};
        }
    }
}
