using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using V=SP2BuildAssistant.VisualCore.V;

namespace SP2BuildAssistant
{
    // Double-precision triangle queries over immutable copied meshes. No Unity APIs.
    internal static class GeometryMeasure
    {
        internal sealed class Triangle
        {
            internal V A,B,C;internal int PartId,Index;
            internal V Min,Max;
            internal V Normal {get {var n=(B-A).Cross(C-A);double len=Math.Sqrt(n.Dot(n));return len>1e-15?n*(1/len):new V();}}
        }
        internal sealed class Witness {internal V A,B;internal Triangle TA,TB;internal double DistanceSquared=double.PositiveInfinity;}
        private sealed class Node {internal V Min,Max;internal Node L,R;internal Triangle[] Items;}
        private static double Get(V v,int axis){return axis==0?v.X:axis==1?v.Y:v.Z;}
        internal static double Length(V v){return Math.Sqrt(v.Dot(v));}
        internal static Triangle[] Triangles(VisualCore.MeshData[] meshes)
        {
            return meshes.SelectMany(m=>Enumerable.Range(0,m.Indices.Length/3).Select(i=>{
                var t=new Triangle{A=m.Vertices[m.Indices[3*i]],B=m.Vertices[m.Indices[3*i+1]],C=m.Vertices[m.Indices[3*i+2]],PartId=m.PartId,Index=i};
                t.Min=new V(Math.Min(t.A.X,Math.Min(t.B.X,t.C.X)),Math.Min(t.A.Y,Math.Min(t.B.Y,t.C.Y)),Math.Min(t.A.Z,Math.Min(t.B.Z,t.C.Z)));
                t.Max=new V(Math.Max(t.A.X,Math.Max(t.B.X,t.C.X)),Math.Max(t.A.Y,Math.Max(t.B.Y,t.C.Y)),Math.Max(t.A.Z,Math.Max(t.B.Z,t.C.Z)));return t;})).ToArray();
        }
        private static Node Build(Triangle[] items)
        {
            var n=new Node{Min=new V(items.Min(t=>t.Min.X),items.Min(t=>t.Min.Y),items.Min(t=>t.Min.Z)),Max=new V(items.Max(t=>t.Max.X),items.Max(t=>t.Max.Y),items.Max(t=>t.Max.Z))};
            if(items.Length<=8){n.Items=items;return n;}var d=n.Max-n.Min;int axis=d.X>=d.Y&&d.X>=d.Z?0:d.Y>=d.Z?1:2;
            Array.Sort(items,(a,b)=>Get(a.Min+a.Max,axis).CompareTo(Get(b.Min+b.Max,axis)));int half=items.Length/2;n.L=Build(items.Take(half).ToArray());n.R=Build(items.Skip(half).ToArray());return n;
        }
        private static double BoxDistance(Node a,Node b){double sum=0;for(int i=0;i<3;i++){double d=Math.Max(0,Math.Max(Get(a.Min,i)-Get(b.Max,i),Get(b.Min,i)-Get(a.Max,i)));sum+=d*d;}return sum;}
        private static double PointBox(V p,Node n){double sum=0;for(int i=0;i<3;i++){double d=Math.Max(0,Math.Max(Get(n.Min,i)-Get(p,i),Get(p,i)-Get(n.Max,i)));sum+=d*d;}return sum;}
        private static void Nearest(V p,Node node,Witness w){
            if(PointBox(p,node)>=w.DistanceSquared)return;
            if(node.Items!=null){foreach(var t in node.Items)Update(w,p,ClosestPoint(p,t),null,t);return;}
            var first=node.L;var second=node.R;if(PointBox(p,first)>PointBox(p,second)){first=node.R;second=node.L;}Nearest(p,first,w);Nearest(p,second,w);
        }
        private static bool Interior(V p,Triangle t){
            // Mesh edges (including triangulation edges) have no unique sampled
            // face normal. Keep their distance samples but omit angle statistics.
            var u=t.B-t.A;var v=t.C-t.A;var w=p-t.A;double uu=u.Dot(u),uv=u.Dot(v),vv=v.Dot(v),d=uu*vv-uv*uv;
            if(d<=1e-28)return false;double b=(vv*w.Dot(u)-uv*w.Dot(v))/d,c=(uu*w.Dot(v)-uv*w.Dot(u))/d;
            return b>1e-7&&c>1e-7&&b+c<1-1e-7;
        }
        internal static JObject Symmetry(Triangle[] a,Triangle[] b,V origin,V normal,double spacing,int limit,Action cancel=null){
            if(a.Length==0||b.Length==0)throw new ApiError("no_geometry","Both scopes need readable triangle surfaces.");
            normal=normal.Unit();long budget=0;
            Func<Triangle,int> divisions=t=>(int)Math.Max(1,Math.Ceiling(Math.Max(Length(t.B-t.A),Math.Max(Length(t.C-t.A),Length(t.C-t.B)))/spacing));
            foreach(var t in a.Concat(b)){long n=divisions(t);budget+=(n+1)*(n+2)/2;if(budget>100000)throw new ApiError("measurement_budget","Symmetry exceeds 100000 surface samples; increase sampleSpacingMetres or narrow the part scopes.");}
            var rows=new System.Collections.Generic.List<JObject>();double sum=0,max=0,angle=0;long count=0,normalCount=0;
            Action<Triangle[],Triangle[],string> direction=(source,target,label)=>{
                var tree=Build(target.ToArray());
                foreach(var t in source){int n=divisions(t);var mirroredNormal=t.Normal-normal*(2*t.Normal.Dot(normal));
                    for(int i=0;i<=n;i++)for(int j=0;j<=n-i;j++){
                        if((count&255)==0)cancel?.Invoke();var original=t.A+(t.B-t.A)*((double)i/n)+(t.C-t.A)*((double)j/n);var p=original-normal*(2*(original-origin).Dot(normal));var w=new Witness();Nearest(p,tree,w);
                        double distance=Math.Sqrt(w.DistanceSquared),degrees=Math.Acos(Math.Max(-1,Math.Min(1,Math.Abs(mirroredNormal.Dot(w.TB.Normal)))))*180/Math.PI;
                        bool normalAvailable=Interior(original,t)&&Interior(w.B,w.TB);
                        sum+=w.DistanceSquared;max=Math.Max(max,distance);if(normalAvailable){angle=Math.Max(angle,degrees);normalCount++;}count++;
                        if(limit>0&&(rows.Count<limit||distance>(double)rows[rows.Count-1]["distanceMetres"])){
                            rows.Add(new JObject{["direction"]=label,["sourcePartId"]=t.PartId,["targetPartId"]=w.TB.PartId,["sourcePoint"]=original.Json(),["reflectedPoint"]=p.Json(),["nearestPoint"]=w.B.Json(),["distanceMetres"]=distance,["unorientedNormalAngleDegrees"]=normalAvailable?(JToken)degrees:null,["normalStatus"]=normalAvailable?"triangle_interiors":"ambiguous_triangle_edge_or_degenerate"});
                            rows=rows.OrderByDescending(x=>(double)x["distanceMetres"]).Take(limit).ToList();
                        }
                    }
                }
            };
            direction(a,b,"A_reflected_to_B");direction(b,a,"B_reflected_to_A");
            return new JObject{["sampledMaxMetres"]=max,["rmsMetres"]=Math.Sqrt(sum/count),["sampleCount"]=count,["sampleSpacingMetres"]=spacing,["maxUnorientedNormalAngleDegrees"]=normalCount>0?(JToken)angle:null,["normalSampleCount"]=normalCount,["ambiguousNormalSampleCount"]=count-normalCount,["normalPolicy"]="Angles require both witnesses strictly inside nondegenerate triangles. Edge/vertex normals are ambiguous and excluded; distance samples remain included.",["worstSamples"]=new JArray(rows),["continuousUpperBound"]=null,["meaning"]="Bidirectional reflected triangle-surface sampling. RMS is sample weighted, not area weighted. Maximum is over sampled points only; duplicated vertices and tessellation affect weighting. Not a certified continuous Hausdorff bound."};
        }
        internal static V ClosestPoint(V p,Triangle t)
        {
            if(Length((t.B-t.A).Cross(t.C-t.A))<1e-14)return Edges(t).Select(e=>SegmentPoint(p,e[0],e[1])).OrderBy(x=>(x-p).Dot(x-p)).First();
            V ab=t.B-t.A,ac=t.C-t.A,ap=p-t.A;double d1=ab.Dot(ap),d2=ac.Dot(ap);if(d1<=0&&d2<=0)return t.A;
            V bp=p-t.B;double d3=ab.Dot(bp),d4=ac.Dot(bp);if(d3>=0&&d4<=d3)return t.B;
            double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return t.A+ab*(d1/(d1-d3));
            V cp=p-t.C;double d5=ab.Dot(cp),d6=ac.Dot(cp);if(d6>=0&&d5<=d6)return t.C;
            double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return t.A+ac*(d2/(d2-d6));
            double va=d3*d6-d5*d4;if(va<=0&&d4-d3>=0&&d5-d6>=0)return t.B+(t.C-t.B)*((d4-d3)/((d4-d3)+(d5-d6)));
            double denominator=va+vb+vc;if(Math.Abs(denominator)<1e-28){var edges=Edges(t);return edges.Select(e=>SegmentPoint(p,e[0],e[1])).OrderBy(x=>(x-p).Dot(x-p)).First();}
            return t.A+ab*(vb/denominator)+ac*(vc/denominator);
        }
        internal static V SegmentPoint(V p,V a,V b){var d=b-a;double len=d.Dot(d);return len<1e-28?a:a+d*Math.Max(0,Math.Min(1,(p-a).Dot(d)/len));}
        private static V[][] Edges(Triangle t){return new[]{new[]{t.A,t.B},new[]{t.B,t.C},new[]{t.C,t.A}};}
        private static void Segments(V p,V p2,V q,V q2,out V a,out V b)
        {
            var d1=p2-p;var d2=q2-q;var r=p-q;double x=d1.Dot(d1),e=d2.Dot(d2),f=d2.Dot(r),s,t;
            if(x<=1e-28&&e<=1e-28){a=p;b=q;return;}if(x<=1e-28){s=0;t=Math.Max(0,Math.Min(1,f/e));}
            else{double c=d1.Dot(r);if(e<=1e-28){t=0;s=Math.Max(0,Math.Min(1,-c/x));}
                else{double k=d1.Dot(d2),den=x*e-k*k;s=Math.Abs(den)>1e-28?Math.Max(0,Math.Min(1,(k*f-c*e)/den)):0;t=(k*s+f)/e;
                    if(t<0){t=0;s=Math.Max(0,Math.Min(1,-c/x));}else if(t>1){t=1;s=Math.Max(0,Math.Min(1,(k-c)/x));}}}
            a=p+d1*s;b=q+d2*t;
        }
        private static bool SegmentHit(V a,V b,Triangle t,out V hit)
        {
            var d=b-a;var e1=t.B-t.A;var e2=t.C-t.A;var h=d.Cross(e2);double det=e1.Dot(h);hit=new V();
            if(Math.Abs(det)<1e-14)return false;double inv=1/det;var s=a-t.A;double u=inv*s.Dot(h);if(u<0||u>1)return false;var q=s.Cross(e1);double v=inv*d.Dot(q);if(v<0||u+v>1)return false;double f=inv*e2.Dot(q);if(f<0||f>1)return false;hit=a+d*f;return true;
        }
        private static void Update(Witness w,V a,V b,Triangle ta,Triangle tb){double d=(a-b).Dot(a-b);if(d<w.DistanceSquared){w.DistanceSquared=d;w.A=a;w.B=b;w.TA=ta;w.TB=tb;}}
        private static void Pair(Triangle a,Triangle b,Witness w)
        {
            foreach(var e in Edges(a)){V hit;if(SegmentHit(e[0],e[1],b,out hit)){Update(w,hit,hit,a,b);return;}}
            foreach(var e in Edges(b)){V hit;if(SegmentHit(e[0],e[1],a,out hit)){Update(w,hit,hit,a,b);return;}}
            foreach(var p in new[]{a.A,a.B,a.C})Update(w,p,ClosestPoint(p,b),a,b);
            foreach(var p in new[]{b.A,b.B,b.C})Update(w,ClosestPoint(p,a),p,a,b);
            foreach(var ea in Edges(a))foreach(var eb in Edges(b)){V pa,pb;Segments(ea[0],ea[1],eb[0],eb[1],out pa,out pb);Update(w,pa,pb,a,b);}
        }
        internal static Witness Distance(Triangle[] a,Triangle[] b,Action cancel=null)
        {
            if(a.Length==0||b.Length==0)throw new ApiError("no_geometry","Both scopes need readable triangle surfaces.");var rootA=Build(a.ToArray());var rootB=Build(b.ToArray());var w=new Witness();long visits=0;
            Action<Node,Node> query=null;query=(x,y)=>{if((visits++&1023)==0)cancel?.Invoke();if(BoxDistance(x,y)>=w.DistanceSquared)return;
                if(x.Items!=null&&y.Items!=null){foreach(var ta in x.Items)foreach(var tb in y.Items)Pair(ta,tb,w);return;}
                bool splitX=y.Items!=null||(x.Items==null&&Length(x.Max-x.Min)>=Length(y.Max-y.Min));var first=splitX?x.L:y.L;var second=splitX?x.R:y.R;var other=splitX?y:x;
                if(BoxDistance(first,other)>BoxDistance(second,other)){var temp=first;first=second;second=temp;}
                if(splitX){query(first,y);query(second,y);}else{query(x,first);query(x,second);}};query(rootA,rootB);return w;
        }
        internal static JObject Report(Witness w){return new JObject{["distanceMetres"]=Math.Sqrt(w.DistanceSquared),["pointA"]=w.A.Json(),["pointB"]=w.B.Json(),["partA"]=w.TA.PartId,["partB"]=w.TB.PartId,["triangleA"]=w.TA.Index,["triangleB"]=w.TB.Index,["normalA"]=w.TA.Normal.Json(),["normalB"]=w.TB.Normal.Json(),["signedDistance"]=null,["penetrationDepth"]=null,["meaning"]="Unsigned surface distance of captured triangle meshes. Zero may mean contact or intersection; a positive value does not rule out containment. Normals belong to the reported witness triangles; edge/vertex witnesses or tied nearest faces do not define a unique surface normal."};}
    }
}
