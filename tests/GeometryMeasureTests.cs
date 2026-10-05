using System;
using System.Linq;
using SP2BuildAssistant;
using V=SP2BuildAssistant.VisualCore.V;
namespace SP2BuildAssistant {internal class ApiError:Exception {internal string Code;internal ApiError(string code,string message):base(message){Code=code;}}}
class GeometryMeasureTests
{
    static int count;
    static void Check(string name,bool value){if(!value)throw new Exception("FAIL "+name);count++;Console.WriteLine("PASS "+name);}
    static GeometryMeasure.Triangle[] Tri(params V[] p){return GeometryMeasure.Triangles(new[]{new VisualCore.MeshData{PartId=1,Vertices=p,Indices=Enumerable.Range(0,p.Length).ToArray()}});}
    static double Distance(GeometryMeasure.Triangle[] a,GeometryMeasure.Triangle[] b){return Math.Sqrt(GeometryMeasure.Distance(a,b).DistanceSquared);}
    static void Main(){
        var a=Tri(new V(0,0,0),new V(1,0,0),new V(0,1,0));
        var b=Tri(new V(0,0,.012),new V(1,0,.012),new V(0,1,.012));
        Check("12 mm parallel gap",Math.Abs(Distance(a,b)-.012)<1e-12);
        Check("witness points independent separation",Math.Abs(GeometryMeasure.Length(GeometryMeasure.Distance(a,b).A-GeometryMeasure.Distance(a,b).B)-.012)<1e-12);
        var intersect=Tri(new V(.2,.2,-1),new V(.2,.2,1),new V(.8,.2,1));
        Check("triangle edge pierces face",Distance(a,intersect)<1e-12);
        var coplanar=Tri(new V(.1,.1,0),new V(.2,.1,0),new V(.1,.2,0));
        Check("coplanar containment",Distance(a,coplanar)<1e-12);
        var outside=Tri(new V(.8,.8,0),new V(1,.8,0),new V(.8,1,0));
        Check("overlapping AABB does not mean touching mesh",Math.Abs(Distance(a,outside)-Math.Sqrt(.18))<1e-12);
        var degenerate=Tri(new V(0,0,1),new V(0,0,1),new V(0,0,1));
        Check("degenerate triangle finite point distance",Math.Abs(Distance(a,degenerate)-1)<1e-12);
        var edge=Tri(new V(.5,-.5,.012),new V(.5,1.5,.012),new V(.5,1.5,1));
        Check("edge-edge closest witness",Math.Abs(Distance(a,edge)-.012)<1e-12);
        Check("distance is symmetric",Math.Abs(Distance(edge,a)-Distance(a,edge))<1e-12);
        var section=SectionMeasure.Cut(a,new V(.25,0,0),new V(1,0,0));
        Check("analytic triangle plane segment",section.Segments.Count==1&&Math.Abs(GeometryMeasure.Length(section.Segments[0].A-section.Segments[0].B)-.75)<1e-12);
        var clipped=SectionMeasure.Cut(a,new V(.25,0,0),new V(1,0,0),new V(0,.2,-1),new V(1,.5,1));
        Check("region clips segment exactly",clipped.Segments.Count==1&&Math.Abs(GeometryMeasure.Length(clipped.Segments[0].A-clipped.Segments[0].B)-.3)<1e-12);
        Check("coplanar exclusion is explicit",SectionMeasure.Cut(a,new V(),new V(0,0,1)).CoplanarTriangles==1);
        var sa=new SectionMeasure.Result();sa.Segments.Add(new SectionMeasure.Segment{A=new V(),B=new V(1,0,0),Normal=new V(0,0,1)});
        var sb=new SectionMeasure.Result();sb.Segments.Add(new SectionMeasure.Segment{A=new V(),B=new V(.5,.01,0),Normal=new V(0,0,-1)});sb.Segments.Add(new SectionMeasure.Segment{A=new V(.5,.01,0),B=new V(1,0,0),Normal=new V(0,0,-1)});
        var seam=SectionMeasure.Seam(sa,sb,.001,8);
        Check("middle seam defect is detected",Math.Abs((double)seam["sampledMaxMetres"]-.01)<1e-12);
        Check("normal sign is not a false 180 degree seam",(double)seam["maxUnorientedNormalAngleDegrees"]<1e-10);
        Check("sampled result has no invented continuous bound",seam["continuousUpperBound"].Type==Newtonsoft.Json.Linq.JTokenType.Null);
        var large=a.Concat(Enumerable.Range(1,100).SelectMany(i=>Tri(new V(i*2,0,0),new V(i*2+1,0,0),new V(i*2,1,0)))).ToArray();
        Check("BVH retains global nearest",Math.Abs(Distance(large,b)-.012)<1e-12);
        var reflected=Tri(new V(0,0,-.012),new V(1,0,-.012),new V(0,1,-.012));
        var symmetric=GeometryMeasure.Symmetry(b,reflected,new V(),new V(0,0,1),.1,5);
        Check("mirror plane surface exact",(double)symmetric["sampledMaxMetres"]<1e-12);
        var asym=GeometryMeasure.Symmetry(b,a,new V(),new V(0,0,1),.1,5);
        Check("mirror defect distance",Math.Abs((double)asym["sampledMaxMetres"]-.012)<1e-12);
        Check("mirror samples are bidirectional",(long)asym["sampleCount"]>100);
        Check("mirror no invented continuous guarantee",asym["continuousUpperBound"].Type==Newtonsoft.Json.Linq.JTokenType.Null);
        Check("mirror edge normals excluded explicitly",(long)symmetric["ambiguousNormalSampleCount"]>0&&(long)symmetric["normalSampleCount"]>0);
        Check("mirror interior normals match",(double)symmetric["maxUnorientedNormalAngleDegrees"]<1e-6);
        var coarse=GeometryMeasure.Symmetry(b,reflected,new V(),new V(0,0,1),10,5);
        Check("no valid normal samples means unavailable angle",coarse["maxUnorientedNormalAngleDegrees"].Type==Newtonsoft.Json.Linq.JTokenType.Null);
        Console.WriteLine("Checks passed: "+count);
    }
}
