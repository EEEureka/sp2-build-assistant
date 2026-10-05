using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // No Unity access here. The worker only sees copied, immutable world-space meshes.
    internal static partial class VisualCore
    {
        // A two-column overview has one blank tile when the view count is odd (> 1).
        internal static long ImagePixelCount(int width,int height,int views,int detailGroups)
        {
            int columns=Math.Min(2,views),overviewTiles=columns*((views+columns-1)/columns);
            return (long)width*height*(views*(1+detailGroups)+overviewTiles);
        }
        internal static void ValidateViewName(string name)
        {
            if(!System.Text.RegularExpressions.Regex.IsMatch(name,"^(?!g)[a-z][a-z0-9-]{0,31}$")||
                System.Text.RegularExpressions.Regex.IsMatch(name,"^(overview|con|prn|aux|nul|com[0-9]|lpt[0-9])$"))
                throw new ApiError("invalid_view","Custom view names use lowercase letters/digits/hyphens; g-prefix, overview and Windows device names are reserved.");
        }
        internal struct V
        {
            public double X,Y,Z;
            public V(double x,double y,double z){X=x;Y=y;Z=z;}
            public static V operator +(V a,V b){return new V(a.X+b.X,a.Y+b.Y,a.Z+b.Z);}
            public static V operator -(V a,V b){return new V(a.X-b.X,a.Y-b.Y,a.Z-b.Z);}
            public static V operator *(V a,double b){return new V(a.X*b,a.Y*b,a.Z*b);}
            public double Dot(V b){return X*b.X+Y*b.Y+Z*b.Z;}
            public V Cross(V b){return new V(Y*b.Z-Z*b.Y,Z*b.X-X*b.Z,X*b.Y-Y*b.X);}
            public V Unit(){double n=Math.Sqrt(Dot(this));if(n<1e-10||!Finite(n))throw new ApiError("invalid_view","View axes must be finite and nonzero.");return this*(1/n);}
            public JArray Json(){return new JArray(X,Y,Z);}
        }
        internal sealed class MeshData { public int PartId,Group; public V[] Vertices; public int[] Indices; }
        internal sealed class View
        {
            public string Name; public V Forward,Up,Right;
            public View(string name,V forward,V up){Name=name;Forward=forward.Unit();Right=up.Cross(Forward).Unit();Up=Forward.Cross(Right).Unit();}
        }
        internal sealed class Box
        {
            public V Min=new V(double.PositiveInfinity,double.PositiveInfinity,double.PositiveInfinity),Max=new V(double.NegativeInfinity,double.NegativeInfinity,double.NegativeInfinity);
            public void Add(V v){if(!Finite(v.X)||!Finite(v.Y)||!Finite(v.Z))throw new ApiError("invalid_geometry","Mesh contains non-finite coordinates.");Min=new V(Math.Min(Min.X,v.X),Math.Min(Min.Y,v.Y),Math.Min(Min.Z,v.Z));Max=new V(Math.Max(Max.X,v.X),Math.Max(Max.Y,v.Y),Math.Max(Max.Z,v.Z));}
            public V Center {get{return (Min+Max)*.5;}}
            public JObject Json(){return new JObject{["min"]=Min.Json(),["max"]=Max.Json(),["center"]=Center.Json(),["size"]=(Max-Min).Json()};}
        }
        internal sealed class Image
        {
            public int Width,Height; public byte[] Pixels,RawPixels; public int[] Ids; public JObject Info;
        }
        internal sealed class Result
        {
            public readonly Dictionary<string,byte[]> Files=new Dictionary<string,byte[]>();
            public readonly Dictionary<string,Image> Views=new Dictionary<string,Image>();
            public JObject Manifest;
        }
        internal static bool Finite(double x){return !double.IsNaN(x)&&!double.IsInfinity(x);}
        internal static readonly int[][] Palette={new[]{72,167,241},new[]{246,158,58},new[]{98,203,132},new[]{208,126,231},new[]{244,112,127},new[]{91,209,210},new[]{221,205,89},new[]{184,190,207}};
        internal static View NamedView(string name)
        {
            switch(name){case "front":return new View(name,new V(0,0,-1),new V(0,1,0));case "back":return new View(name,new V(0,0,1),new V(0,1,0));
            case "right":return new View(name,new V(-1,0,0),new V(0,1,0));case "left":return new View(name,new V(1,0,0),new V(0,1,0));
            case "top":return new View(name,new V(0,-1,0),new V(0,0,1));case "bottom":return new View(name,new V(0,1,0),new V(0,0,-1));
            case "isometric":return new View(name,new V(-1,-.7,-1),new V(0,1,0));default:throw new ApiError("invalid_view","Unknown view: "+name);}
        }
        internal static Box Bounds(IEnumerable<MeshData> meshes){var b=new Box();foreach(var m in meshes)foreach(var i in m.Indices)b.Add(m.Vertices[i]);return b;}
        internal static double Fit(IEnumerable<MeshData> meshes,View[] views,V center,int width,int height)
        {
            double scale=double.PositiveInfinity;
            foreach(var view in views){double x=.0005,y=.0005;foreach(var mesh in meshes)foreach(int i in mesh.Indices){V p=mesh.Vertices[i]-center;x=Math.Max(x,Math.Abs(p.Dot(view.Right)));y=Math.Max(y,Math.Abs(p.Dot(view.Up)));}
                scale=Math.Min(scale,Math.Min((width-64)/(2*x),(height-96)/(2*y)));}
            return scale/1.08;
        }
        internal static string GeometryHash(IEnumerable<MeshData> meshes)
        {
            using(var sha=SHA256.Create())using(var stream=new CryptoStream(Stream.Null,sha,CryptoStreamMode.Write))using(var w=new BinaryWriter(stream)){
                foreach(var m in meshes){w.Write(m.PartId);w.Write(m.Group);w.Write(m.Vertices.Length);foreach(var v in m.Vertices){w.Write(v.X);w.Write(v.Y);w.Write(v.Z);}w.Write(m.Indices.Length);foreach(int i in m.Indices)w.Write(i);}w.Flush();stream.FlushFinalBlock();return Hex(sha.Hash);}
        }
        internal static string Hex(byte[] bytes){return BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant();}
        internal static string Hash(byte[] bytes){using(var s=SHA256.Create())return Hex(s.ComputeHash(bytes));}
        internal static MeshData CleanMesh(MeshData source,out int removedTriangles)
        {
            var vertices=new List<V>();var indices=new List<int>();var map=new Dictionary<int,int>();removedTriangles=0;
            for(int t=0;t<source.Indices.Length;t+=3){bool valid=true;for(int j=0;j<3;j++){int i=source.Indices[t+j];if(i<0||i>=source.Vertices.Length)throw new ApiError("invalid_geometry","Invalid triangle index.");V v=source.Vertices[i];if(!Finite(v.X)||!Finite(v.Y)||!Finite(v.Z))valid=false;}
                if(!valid){removedTriangles++;continue;}for(int j=0;j<3;j++){int old=source.Indices[t+j];if(!map.TryGetValue(old,out int index)){index=vertices.Count;vertices.Add(source.Vertices[old]);map.Add(old,index);}indices.Add(index);}}
            return new MeshData{PartId=source.PartId,Group=source.Group,Vertices=vertices.ToArray(),Indices=indices.ToArray()};
        }

        internal static Result Render(MeshData[] meshes,int[] partIds,View[] views,int width,int height,bool details,JObject manifest,Func<bool> cancelled)
        { return Render(meshes,partIds,views,width,height,details ? "perGroup" : "none",manifest,cancelled); }
        internal static Result Render(MeshData[] meshes,int[] partIds,View[] views,int width,int height,string details,JObject manifest,Func<bool> cancelled)
        {
            if(ImagePixelCount(width,height,views.Length,0)>16000000)throw new ApiError("render_budget","Image budget is 16 million pixels including overview.");
            var timer=Stopwatch.StartNew();Action check=()=>{if(cancelled())throw new ApiError("cancelled","Visual capture cancelled.");if(timer.Elapsed.TotalSeconds>45)throw new ApiError("render_timeout","Visual render exceeded 45 seconds; reduce resolution or scope.");};
            if(meshes.Length==0)throw new ApiError("no_geometry","Selected scope has no readable visible triangle meshes.");
            var result=new Result{Manifest=manifest};var bounds=Bounds(meshes);var centerReport=manifest["centersReport"] as JObject;
            var fitMeshes=CenterFitMeshes(meshes,centerReport);var center=Bounds(fitMeshes).Center;double scale=Fit(fitMeshes,views,center,width,height);long work=0;
            var tokens=partIds.Select((id,i)=>new{id,token=i+1}).ToDictionary(p=>p.id,p=>p.token);
            manifest["geometryStamp"]=GeometryHash(meshes);manifest["bounds"]=bounds.Json();manifest["views"]=new JArray();
            if(centerReport!=null){centerReport["geometryStamp"]=manifest["geometryStamp"].DeepClone();manifest["framingBounds"]=Bounds(fitMeshes).Json();}
            manifest["scalePolicy"]=centerReport==null?"fit_scope_each_capture":"fit_scope_and_centers_each_capture";
            manifest["recommendationPolicy"]=new JObject{["basis"]="best visible joint tile, before harness downscaling",["minimumExtentPixels"]=96,["minimumRelativeExtent"]=.15,["minimumVisiblePixels"]=1024};
            manifest["comparisonGuidance"]="A frame fixes coordinate axes, not zoom. Even with the same frame/resolution, changed geometry changes pixelsPerMetre. Compare metres using each view's pixelsPerMetre/frameToPixelRows; do not compare raw pixel lengths across captures or detail views.";
            manifest["partIdPalette"]=new JArray(tokens.Select(t=>new JObject{["partId"]=t.Key,["index"]=t.Value,["rgb"]=new JArray(t.Value&255,(t.Value>>8)&255,(t.Value>>16)&255)}));
            var overview=new List<Image>();
            int[] renderedIds=meshes.Select(m=>m.PartId).Distinct().OrderBy(i=>i).ToArray();
            foreach(var v in views){check();var img=Raster(meshes,renderedIds,tokens,v,center,scale,width,height,check,ref work,centerReport);if(centerReport!=null)DrawCenters(img,centerReport,v,center,scale);AddImage(result,v.Name,img);overview.Add(img);}
            int cols=Math.Min(2,overview.Count),rows=(overview.Count+cols-1)/cols;
            var sheet=Blank(width*cols,height*rows);
            for(int k=0;k<overview.Count;k++)for(int y=0;y<height;y++)Buffer.BlockCopy(overview[k].Pixels,y*width*4,sheet.Pixels,((k/cols*height+y)*sheet.Width+(k%cols)*width)*4,width*4);
            result.Files["overview.png"]=Png(sheet.Width,sheet.Height,sheet.Pixels);
            foreach(var img in overview){img.Pixels=null;img.RawPixels=null;}
            manifest["recommendedImages"]=new JArray("overview.png");
            manifest["imageRecommendations"]=new JArray(new JObject{["file"]="overview.png",["reason"]="joint_spatial_context"});
            var detailStatus=new JArray();manifest["detailStatus"]=detailStatus;
            long pixels=ImagePixelCount(width,height,views.Length,0);
            foreach(JObject groupInfo in (JArray)manifest["groups"]){
                int group=groupInfo.Value<int>("index");var local=meshes.Where(m=>m.Group==group).ToArray();
                var status=new JObject{["groupIndex"]=group,["status"]="no_geometry"};detailStatus.Add(status);if(local.Length==0)continue;
                var ids=local.Select(m=>m.PartId).Distinct().OrderBy(i=>i).ToArray();
                var metrics=overview.Select(img=>GroupProjection(img,ids)).ToArray();
                var best=metrics.OrderByDescending(m=>m.Value<double>("readability")).First();
                bool need=!metrics.Any(m=>m.Value<bool>("readable"));
                status["jointBestView"]=best["view"];status["jointViews"]=new JArray(metrics);status["detailNeeded"]=need;
                if(details=="none"){status["status"]=need?"disabled":"not_needed";continue;}
                if(details=="auto"&&!need){status["status"]="not_needed";continue;}
                var detailViews=details=="perGroup"?views:new[]{views.FirstOrDefault(v=>v.Name=="isometric")??views.First(v=>v.Name==(string)best["view"])};
                long extra=(long)width*height*detailViews.Length;
                if(pixels+extra>16000000){if(details=="perGroup")throw new ApiError("render_budget","Image budget is 16 million pixels.");status["status"]="budget_exceeded";continue;}
                pixels+=extra;var mid=Bounds(local).Center;double zoom=Fit(local,detailViews,mid,width,height);
                var candidates=new List<Image>();
                foreach(var v in detailViews){check();string name="g"+(group+1)+"-"+v.Name;var img=Raster(local,ids,tokens,v,mid,zoom,width,height,check,ref work,centerReport);img.Info["groupIndex"]=group;img.Info["detail"]=true;AddImage(result,name,img);candidates.Add(img);img.Pixels=null;img.RawPixels=null;}
                status["status"]="generated";
                if(need){
                    var chosen=candidates.OrderByDescending(img=>GroupProjection(img,ids).Value<double>("readability")*(img.Info.Value<string>("name").EndsWith("isometric")?1.15:1)).First();
                    bool dense=((JArray)chosen.Info["parts"]).Count(p=>p.Value<int>("visiblePixels")>0)>8;
                    string file=chosen.Info.Value<string>(dense?"rawFile":"annotatedFile");
                    ((JArray)manifest["recommendedImages"]).Add(file);
                    ((JArray)manifest["imageRecommendations"]).Add(new JObject{["file"]=file,["groupIndex"]=group,["view"]=chosen.Info["name"],
                        ["reason"]=best.Value<int>("visiblePixels")==0?"occluded_in_joint_views":"small_or_thin_in_joint_views",["pixelsPerMetre"]=chosen.Info["pixelsPerMetre"],
                        ["meaning"]="Isolated group detail at its own zoom. Use overview for relative position and surrounding context."});
                }
            }
            if(centerReport!=null)RenderCentersDetails(result,meshes,renderedIds,tokens,centerReport,scale,width,height,check,ref work,ref pixels);
            var groups=(JArray)manifest["groups"];
            foreach(JObject g in groups){int index=g.Value<int>("index");var own=meshes.Where(m=>m.Group==index).ToArray();g["bounds"]=own.Length==0?null:Bounds(own).Json();g["analysisColor"]=new JArray(centerReport==null?Palette[index%Palette.Length]:new[]{192,200,215});if(centerReport!=null)g["focusColor"]=new JArray(112,224,177);}
            var relations=new JArray();for(int i=0;i<groups.Count;i++)for(int j=i+1;j<groups.Count;j++){var a=meshes.Where(m=>m.Group==i).ToArray();var b=meshes.Where(m=>m.Group==j).ToArray();if(a.Length>0&&b.Length>0)relations.Add(new JObject{["fromGroup"]=i,["toGroup"]=j,["basis"]="captured_geometry_bounds_centers",["deltaMetres"]=(Bounds(b).Center-Bounds(a).Center).Json()});}
            manifest["relations"]=relations;manifest["renderSeconds"]=timer.Elapsed.TotalSeconds;
            return result;
        }
        private static JObject GroupProjection(Image img,int[] ids)
        {
            var set=new HashSet<int>(ids);var parts=((JArray)img.Info["parts"]).Where(p=>set.Contains(p.Value<int>("partId"))).ToArray();
            int count=parts.Sum(p=>p.Value<int>("visiblePixels"));
            var boxes=parts.Where(p=>p.Value<int>("visiblePixels")>0).Select(p=>(JArray)p["visibleBoundsPixels"]).ToArray();
            double w=boxes.Length==0?0:boxes.Max(b=>b[2].Value<double>())-boxes.Min(b=>b[0].Value<double>())+1;
            double h=boxes.Length==0?0:boxes.Max(b=>b[3].Value<double>())-boxes.Min(b=>b[1].Value<double>())+1;
            double relative=Math.Max(w/img.Width,h/img.Height),extent=Math.Max(w,h);
            return new JObject{["view"]=img.Info["name"],["widthPixels"]=w,["heightPixels"]=h,["visiblePixels"]=count,["relativeExtent"]=relative,
                ["readable"]=extent>=96&&relative>=.15&&count>=1024,
                ["readability"]=Math.Min(extent/96,Math.Min(relative/.15,count/1024.0))};
        }
        private static void AddImage(Result result,string name,Image img)
        {
            result.Files[name+".png"]=Png(img.Width,img.Height,img.Pixels);
            result.Files[name+".raw.png"]=Png(img.Width,img.Height,img.RawPixels);
            byte[] ids=new byte[img.Width*img.Height*4];for(int i=0;i<img.Ids.Length;i++){int t=img.Ids[i];ids[i*4]=(byte)t;ids[i*4+1]=(byte)(t>>8);ids[i*4+2]=(byte)(t>>16);ids[i*4+3]=255;}
            result.Files[name+".ids.png"]=Png(img.Width,img.Height,ids);
            img.Info["name"]=name;img.Info["annotatedFile"]=name+".png";img.Info["rawFile"]=name+".raw.png";img.Info["partIdFile"]=name+".ids.png";
            ((JArray)result.Manifest["views"]).Add(img.Info);result.Views.Add(name,img);
        }
        internal static Image Blank(int width,int height){var img=new Image{Width=width,Height=height,Pixels=new byte[width*height*4]};for(int i=0;i<img.Pixels.Length;i+=4){img.Pixels[i]=24;img.Pixels[i+1]=29;img.Pixels[i+2]=38;img.Pixels[i+3]=255;}return img;}
        internal static Image Raster(MeshData[] meshes,int[] ids,Dictionary<int,int> tokens,View view,V center,double scale,int width,int height,Action check,ref long work,JObject centers=null)
        {
            var img=Blank(width,height);img.Ids=new int[width*height];var depth=Enumerable.Repeat(double.PositiveInfinity,width*height).ToArray();var projected=new Dictionary<int,double[]>();var pixels=new Dictionary<int,int>();
            foreach(int id in ids){projected[id]=new[]{double.PositiveInfinity,double.PositiveInfinity,double.NegativeInfinity,double.NegativeInfinity};pixels[id]=0;}
            var reverse=tokens.ToDictionary(p=>p.Value,p=>p.Key);double minDepth=double.PositiveInfinity,maxDepth=double.NegativeInfinity;
            foreach(var mesh in meshes){check();var vtx=new V[mesh.Vertices.Length];for(int i=0;i<vtx.Length;i++){V d=mesh.Vertices[i]-center;vtx[i]=new V(width*.5+d.Dot(view.Right)*scale,height*.5-d.Dot(view.Up)*scale,d.Dot(view.Forward));}
                int token=tokens[mesh.PartId];int[] baseColor=centers==null?Palette[mesh.Group%Palette.Length]:(centers["focus"]?["partIds"] is JArray focused&&focused.Values<int>().Contains(mesh.PartId)?new[]{112,224,177}:new[]{192,200,215});var pb=projected[mesh.PartId];
                for(int t=0;t<mesh.Indices.Length;t+=3){if((t&1023)==0)check();V a=vtx[mesh.Indices[t]],b=vtx[mesh.Indices[t+1]],c=vtx[mesh.Indices[t+2]];
                    foreach(V q in new[]{a,b,c}){pb[0]=Math.Min(pb[0],q.X);pb[1]=Math.Min(pb[1],q.Y);pb[2]=Math.Max(pb[2],q.X);pb[3]=Math.Max(pb[3],q.Y);minDepth=Math.Min(minDepth,q.Z);maxDepth=Math.Max(maxDepth,q.Z);}
                    double area=(b.X-a.X)*(c.Y-a.Y)-(b.Y-a.Y)*(c.X-a.X);if(Math.Abs(area)<1e-10)continue;
                    int x0=Math.Max(0,(int)Math.Floor(Math.Min(a.X,Math.Min(b.X,c.X)))),x1=Math.Min(width-1,(int)Math.Ceiling(Math.Max(a.X,Math.Max(b.X,c.X))));
                    int y0=Math.Max(0,(int)Math.Floor(Math.Min(a.Y,Math.Min(b.Y,c.Y)))),y1=Math.Min(height-1,(int)Math.Ceiling(Math.Max(a.Y,Math.Max(b.Y,c.Y))));
                    work+=(long)Math.Max(0,x1-x0+1)*Math.Max(0,y1-y0+1);if(work>350000000L)throw new ApiError("render_budget","Pixel work budget exceeded; reduce resolution, views or scope.");
                    // View-space lighting and two-sided surfaces keep reflected meshes visible.
                    V n=(mesh.Vertices[mesh.Indices[t+1]]-mesh.Vertices[mesh.Indices[t]]).Cross(mesh.Vertices[mesh.Indices[t+2]]-mesh.Vertices[mesh.Indices[t]]);
                    V normal=new V(n.Dot(view.Right),n.Dot(view.Up),n.Dot(view.Forward));double length=Math.Sqrt(normal.Dot(normal));double light=.3+.7*(length<1e-15?0:Math.Abs(normal.Dot(new V(-.35,.5,-.79)))/length);
                    byte r=(byte)Math.Min(255,baseColor[0]*light),g=(byte)Math.Min(255,baseColor[1]*light),bl=(byte)Math.Min(255,baseColor[2]*light);
                    for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){double px=x+.5,py=y+.5;
                        double u=((b.X-px)*(c.Y-py)-(b.Y-py)*(c.X-px))/area,v=((c.X-px)*(a.Y-py)-(c.Y-py)*(a.X-px))/area,w=1-u-v;
                        if(u< -1e-9||v< -1e-9||w< -1e-9)continue;double z=u*a.Z+v*b.Z+w*c.Z;int pos=y*width+x;
                        if(z>=depth[pos]-1e-10)continue;depth[pos]=z;img.Ids[pos]=token;int k=pos*4;img.Pixels[k]=r;img.Pixels[k+1]=g;img.Pixels[k+2]=bl;
                    }
                }
            }
            var visible=new Dictionary<int,int[]>();for(int y=0;y<height;y++)for(int x=0;x<width;x++){int tok=img.Ids[y*width+x];if(tok==0)continue;int id=reverse[tok];pixels[id]++;if(!visible.TryGetValue(id,out int[] box))visible[id]=box=new[]{x,y,x,y};box[0]=Math.Min(x,box[0]);box[1]=Math.Min(y,box[1]);box[2]=Math.Max(x,box[2]);box[3]=Math.Max(y,box[3]);}
            img.RawPixels=(byte[])img.Pixels.Clone();var entries=new JArray();int labels=0;var occupied=new List<int[]>();
            foreach(int id in ids){bool seen=visible.TryGetValue(id,out int[] b);string label="G"+(meshes.First(m=>m.PartId==id).Group+1)+" P"+id;bool labelled=false;
                if(centers==null&&seen&&labels<32){int lx=Math.Max(2,Math.Min(width-label.Length*6-2,b[0])),ly=Math.Max(28,Math.Min(height-28,b[1]));for(int tries=0;tries<5;tries++,ly+=10){if(ly>height-28)break;if(occupied.Any(o=>lx<o[2]&&lx+label.Length*6>o[0]&&ly<o[3]&&ly+8>o[1]))continue;Text(img,lx,ly,label,255,255,255,true);occupied.Add(new[]{lx,ly,lx+label.Length*6,ly+8});labelled=true;labels++;break;}}
                entries.Add(new JObject{["partId"]=id,["index"]=tokens[id],["projectedBoundsPixels"]=Finite(projected[id][0])?new JArray(projected[id]):null,["visibleBoundsPixels"]=seen?new JArray(b):null,["visiblePixels"]=pixels[id],["visibility"]=seen?"visible":"occluded_or_subpixel",["labelDrawn"]=labelled});}
            Text(img,8,8,view.Name.ToUpperInvariant()+"  ANALYSIS",230,235,245,true);
            var axes=new[]{new V(1,0,0),new V(0,1,0),new V(0,0,1)};var axisColors=new[]{new byte[]{245,99,99},new byte[]{103,219,133},new byte[]{104,172,255}};
            for(int axis=0;axis<3;axis++){int ax=width-35,ay=40,ex=ax+(int)(axes[axis].Dot(view.Right)*22),ey=ay-(int)(axes[axis].Dot(view.Up)*22);var color=axisColors[axis];DrawLine(img,ax,ay,ex,ey,color[0],color[1],color[2]);Text(img,ex+2,ey-3,"XYZ"[axis].ToString(),color[0],color[1],color[2],false);}
            double bar=NiceLength(100/scale);int barPixels=(int)Math.Round(bar*scale);Line(img,12,height-20,12+barPixels,height-20,240,240,240);
            Text(img,12,height-12,bar.ToString("0.###",System.Globalization.CultureInfo.InvariantCulture)+" M",230,235,245,true);
            img.Info=new JObject{["width"]=width,["height"]=height,["pixelsPerMetre"]=scale,["targetCenter"]=center.Json(),["forward"]=view.Forward.Json(),["screenRight"]=view.Right.Json(),["screenUp"]=view.Up.Json(),["depthRange"]=new JArray(minDepth,maxDepth),["projection"]="orthographic",["pixelOrigin"]="top_left",["pixelSample"]="integer index plus 0.5",["parts"]=entries,
                ["frameToPixelRows"]=new JArray(new JArray(view.Right.X*scale,view.Right.Y*scale,view.Right.Z*scale,width*.5-center.Dot(view.Right)*scale),new JArray(-view.Up.X*scale,-view.Up.Y*scale,-view.Up.Z*scale,height*.5+center.Dot(view.Up)*scale),new JArray(view.Forward.X,view.Forward.Y,view.Forward.Z,-center.Dot(view.Forward)),new JArray(0,0,0,1))};return img;
        }
        private static double NiceLength(double x){double p=Math.Pow(10,Math.Floor(Math.Log10(x)));double n=x/p;return (n>=5?5:n>=2?2:1)*p;}
        private static void Pixel(Image i,int x,int y,byte r,byte g,byte b){if(x<0||y<0||x>=i.Width||y>=i.Height)return;int p=(y*i.Width+x)*4;i.Pixels[p]=r;i.Pixels[p+1]=g;i.Pixels[p+2]=b;}
        private static void Line(Image i,int x,int y,int end,int unused,byte r,byte g,byte b){for(;x<=end;x++)Pixel(i,x,y,r,g,b);}
        private static void DrawLine(Image img,int x,int y,int ex,int ey,byte r,byte g,byte b){int dx=Math.Abs(ex-x),sx=x<ex?1:-1,dy=-Math.Abs(ey-y),sy=y<ey?1:-1,err=dx+dy;while(true){Pixel(img,x,y,r,g,b);if(x==ex&&y==ey)break;int twice=2*err;if(twice>=dy){err+=dy;x+=sx;}if(twice<=dx){err+=dx;y+=sy;}}}
        private static readonly Dictionary<char,string> Font=new Dictionary<char,string>{
            {'0',"01110100011001110101110011000101110"},{'1',"00100011000010000100001000010001110"},{'2',"01110100010000100010001000100011111"},{'3',"11110000010000101110000010000111110"},{'4',"00010001100101010010111110001000010"},{'5',"11111100001111000001000011000101110"},{'6',"00110010001000011110100011000101110"},{'7',"11111000010001000100010000100001000"},{'8',"01110100011000101110100011000101110"},{'9',"01110100011000101111000010001001100"},
            {'A',"01110100011000111111100011000110001"},{'B',"11110100011000111110100011000111110"},{'C',"01111100001000010000100001000001111"},{'D',"11110100011000110001100011000111110"},{'E',"11111100001000011110100001000011111"},{'F',"11111100001000011110100001000010000"},{'G',"01111100001000010111100011000101111"},{'H',"10001100011000111111100011000110001"},{'I',"01110001000010000100001000010001110"},{'J',"00001000010000100001100011000101110"},{'K',"10001100101010011000101001001010001"},{'L',"10000100001000010000100001000011111"},{'M',"10001110111010110101100011000110001"},{'N',"10001110011010110011100011000110001"},{'O',"01110100011000110001100011000101110"},{'P',"11110100011000111110100001000010000"},{'Q',"01110100011000110001101011001001101"},{'R',"11110100011000111110101001001010001"},{'S',"01111100001000001110000010000111110"},{'T',"11111001000010000100001000010000100"},{'U',"10001100011000110001100011000101110"},{'V',"10001100011000110001100010101000100"},{'W',"10001100011000110101101011101110001"},{'X',"10001100010101000100010101000110001"},{'Y',"10001100010101000100001000010000100"},{'Z',"11111000010001000100010001000011111"},{'.',"00000000000000000000000000011000110"},{'-',"00000000000000011111000000000000000"}};
        internal static void Text(Image img,int x,int y,string text,byte r,byte g,byte b,bool background)
        {foreach(char c in text){if(background)for(int yy=-1;yy<8;yy++)for(int xx=-1;xx<6;xx++)Pixel(img,x+xx,y+yy,18,22,29);if(Font.TryGetValue(c,out string bits))for(int j=0;j<35;j++)if(bits[j]=='1')Pixel(img,x+j%5,y+j/5,r,g,b);x+=6;}}
        internal static byte[] Png(int width,int height,byte[] rgba)
        {
            using(var output=new MemoryStream())using(var w=new BinaryWriter(output)){w.Write(new byte[]{137,80,78,71,13,10,26,10});byte[] head=new byte[13];BE(head,0,(uint)width);BE(head,4,(uint)height);head[8]=8;head[9]=6;Chunk(w,"IHDR",head);
                byte[] raw=new byte[(width*4+1)*height];for(int y=0;y<height;y++)Buffer.BlockCopy(rgba,y*width*4,raw,y*(width*4+1)+1,width*4);
                using(var compressed=new MemoryStream()){compressed.WriteByte(0x78);compressed.WriteByte(0x9c);using(var def=new DeflateStream(compressed,CompressionMode.Compress,true))def.Write(raw,0,raw.Length);uint a=1,b=0;foreach(byte v in raw){a=(a+v)%65521;b=(b+a)%65521;}byte[] sum=new byte[4];BE(sum,0,(b<<16)|a);compressed.Write(sum,0,4);Chunk(w,"IDAT",compressed.ToArray());}Chunk(w,"IEND",new byte[0]);return output.ToArray();}
        }
        private static void BE(byte[] b,int offset,uint x){b[offset]=(byte)(x>>24);b[offset+1]=(byte)(x>>16);b[offset+2]=(byte)(x>>8);b[offset+3]=(byte)x;}
        private static void Chunk(BinaryWriter w,string name,byte[] data){byte[] len=new byte[4];BE(len,0,(uint)data.Length);w.Write(len);byte[] n=System.Text.Encoding.ASCII.GetBytes(name);w.Write(n);w.Write(data);uint crc=0xffffffff;foreach(byte v in n.Concat(data)){crc^=v;for(int k=0;k<8;k++)crc=(crc&1)!=0?0xedb88320^(crc>>1):crc>>1;}BE(len,0,~crc);w.Write(len);}
    }
}
