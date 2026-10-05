using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.Weapons;
using Assets.Scripts.Design;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private sealed class VisualSaved {public string Id;public DateTime Created;public VisualCore.Result Result;public long Bytes;}
        private readonly object visualGate=new object();
        private readonly Dictionary<string,VisualSaved> visualSaved=new Dictionary<string,VisualSaved>();
        private static VisualCore.V VV(Vector3 v){return new VisualCore.V(v.x,v.y,v.z);}
        private static JArray MatrixRows(Matrix4x4 m){return new JArray(Enumerable.Range(0,4).Select(r=>new JArray(Enumerable.Range(0,4).Select(c=>m[r,c]))));}
        private void VisualGuard(JObject args){if(VisualScope.String(args["craftSessionId"],"craftSessionId")!=session)throw new ApiError("session_conflict","Visual request belongs to another aircraft session.");if(args["expectedRevision"]!=null&&VisualScope.Integer(args["expectedRevision"],"expectedRevision",1)!=revision)throw new ApiError("revision_conflict","Aircraft changed; query a fresh snapshot.");EnsureDesignerSceneIntegrity(Current());}
        private int[] VisualAssembly(int id)
        {
            var root=Part(id);var parts=Current().Aircraft.Aircraft.Assembly.Parts;var ids=new HashSet<int>{id};
            if(root.GetModifier<ProceduralMissileData>()!=null){foreach(var p in parts)if(p.GetModifier<ProceduralMissileSubPartData>()?.Script?.GetConnectedMissile()?.PartScript.Part.Id==id)ids.Add(p.Id);}
            else if(root.GetModifier<JWingData>()!=null){foreach(var p in parts)if(p.GetModifier<ControlSurfacePartData>()?.GetFirstConnectedWing()?.Part.Id==id)ids.Add(p.Id);}
            else throw new ApiError("assembly_not_supported","Use explicit partIds or a bounded branch for this part type.");return ids.OrderBy(i=>i).ToArray();
        }
        private JObject VisualResolve(JObject args,bool capture=false)
        {
            if(!capture)VisualScope.Keys(args,"craftSessionId","expectedRevision","groups","maxParts");Observe();VisualGuard(args);var d=Current();var parts=d.Aircraft.Aircraft.Assembly.Parts;var all=new HashSet<int>(parts.Select(p=>p.Id));
            var edges=parts.SelectMany(p=>p.PartConnections).Distinct().Select(c=>{
                string first=c.PartA.Id+":"+string.Join(",",c.AttachPointsA.Select(p=>p.Id).OrderBy(i=>i)),second=c.PartB.Id+":"+string.Join(",",c.AttachPointsB.Select(p=>p.Id).OrderBy(i=>i));string canonical=String.CompareOrdinal(first,second)<0?first+"|"+second:second+"|"+first;
                string key="edge-"+Json.Hash(canonical).Substring(0,24);var info=new JObject{["key"]=key,["partA"]=c.PartA.Id,["partB"]=c.PartB.Id,["attachPointsA"]=new JArray(c.AttachPointsA.Select(p=>p.Id)),["attachPointsB"]=new JArray(c.AttachPointsB.Select(p=>p.Id))};return new VisualScope.Edge{A=c.PartA.Id,B=c.PartB.Id,Key=key,Info=info};}).ToArray();
            if(edges.Select(e=>e.Key).Distinct().Count()!=edges.Length)throw new ApiError("scope_ambiguous","Duplicate native connection identities.");
            int max=args["maxParts"]==null?2048:VisualScope.Integer(args["maxParts"],"maxParts",1,2048);var groups=args["groups"] as JArray??(args["groups"]==null?new JArray(new JObject{["name"]="selection",["selector"]=new JObject{["kind"]="selected"}}):null);
            if(groups==null||groups.Count<1||groups.Count>8)throw new ApiError("invalid_input","groups requires 1..8 entries.");var output=new JArray();var used=new HashSet<int>();var names=new HashSet<string>();
            foreach(var token in groups){var g=token as JObject;VisualScope.Keys(g,"name","selector");string name=VisualScope.String(g["name"],"name");if(name.Length>80||!names.Add(name))throw new ApiError("invalid_input","Group names must be unique, up to 80 characters.");
                var selector=g["selector"] as JObject;if(selector==null)throw new ApiError("invalid_input","selector must be an object.");int[] ids=VisualScope.Resolve(selector,all,edges,d.SelectedPart==null?(int?)null:d.SelectedPart.Part.Id,VisualAssembly,max);
                if(ids.Any(id=>!used.Add(id)))throw new ApiError("scope_overlap","Groups share parts; use disjoint explicit sets.");if(used.Count>max)throw new ApiError("scope_budget","Combined scope exceeds maxParts.");var set=new HashSet<int>(ids);
                output.Add(new JObject{["index"]=output.Count,["groupIndex"]=output.Count,["name"]=name,["selector"]=selector.DeepClone(),["partIds"]=new JArray(ids),["externalConnections"]=new JArray(edges.Where(e=>set.Contains(e.A)!=set.Contains(e.B)).Select(e=>e.Info.DeepClone()))});
            }
            return new JObject{["identity"]=JToken.FromObject(Identity()),["groups"]=output,["partIds"]=new JArray(used.OrderBy(i=>i)),["connections"]=new JArray(edges.Select(e=>e.Info)),["meaning"]="Explicit visual scope. Graph branches are not physical support or persistent component ownership."};
        }
        private static VisualCore.View[] VisualViews(JToken token)
        {
            var a=token as JArray??(token==null?new JArray("front","right","top","isometric"):null);if(a==null||a.Count<1||a.Count>8)throw new ApiError("invalid_input","views must contain 1..8 views.");var list=new List<VisualCore.View>();
            foreach(var item in a){VisualCore.View v;if(item.Type==JTokenType.String)v=VisualCore.NamedView((string)item);else{var obj=item as JObject;VisualScope.Keys(obj,"name","direction","up");string name=VisualScope.String(obj["name"],"view.name");VisualCore.ValidateViewName(name);v=new VisualCore.View(name,ReadV(obj["direction"]),ReadV(obj["up"]));}if(list.Any(x=>x.Name==v.Name))throw new ApiError("invalid_view","Duplicate view name.");list.Add(v);}return list.ToArray();
        }
        private static VisualCore.V ReadV(JToken t){if(!(t is JArray a)||a.Count!=3||a.Any(x=>x.Type!=JTokenType.Float&&x.Type!=JTokenType.Integer))throw new ApiError("invalid_view","Vectors need three numbers.");return new VisualCore.V(a[0].Value<double>(),a[1].Value<double>(),a[2].Value<double>());}
        private async UniTask<JObject> VisualCapture(JObject args,Job job,JObject centerOptions=null)
        {
            VisualScope.Keys(args,"craftSessionId","expectedRevision","groups","maxParts","views","resolution","frame","details","includeHidden","overlays");
            if(args["overlays"]!=null){var overlay=args["overlays"] as JObject;VisualScope.Keys(overlay,"centers");if(VisualScope.Boolean(overlay["centers"],"overlays.centers"))centerOptions=centerOptions??new JObject();}
            if(centerOptions!=null){centerOptions=(JObject)centerOptions.DeepClone();if(args["frame"]!=null)centerOptions["frame"]=args["frame"].DeepClone();}
            Observe();VisualGuard(args);var d=Current();var aircraft=d.Aircraft;await ReadSettled(d,null);VisualGuard(args);var resolved=VisualResolve(args,true);
            var views=VisualViews(args["views"]);var res=args["resolution"] as JObject??(args["resolution"]==null?new JObject():null);VisualScope.Keys(res,"width","height");int width=res["width"]==null?640:VisualScope.Integer(res["width"],"width",128,1024),height=res["height"]==null?640:VisualScope.Integer(res["height"],"height",128,1024);
            if(centerOptions!=null&&(width<384||height<384))throw new ApiError("invalid_input","Center annotations require width and height of at least 384 pixels.");
            string details=VisualScope.String(args["details"],"details","auto");if(details!="none"&&details!="perGroup"&&details!="auto")throw new ApiError("invalid_input","details must be auto, none or perGroup.");
            bool includeHidden=VisualScope.Boolean(args["includeHidden"],"includeHidden");var frame=args["frame"] as JObject??(args["frame"]==null?new JObject{["kind"]="world"}:null);VisualScope.Keys(frame,"kind","partId");string frameKind=VisualScope.String(frame["kind"],"frame.kind");var frameToWorld=Matrix4x4.identity;
            if(frameKind=="part"){var t=Part(VisualScope.Integer(frame["partId"],"frame.partId")).PartScript.transform;frameToWorld=Matrix4x4.TRS(t.position,t.rotation,Vector3.one);}else if(frameKind!="world"||frame["partId"]!=null)throw new ApiError("invalid_input","frame must be world or part with partId.");var worldToFrame=frameToWorld.inverse;
            var groups=(JArray)resolved["groups"];if(VisualCore.ImagePixelCount(width,height,views.Length,details=="perGroup"?groups.Count:0)>16000000)throw new ApiError("render_budget","Image budget is 16 million pixels including overview; reduce views or resolution.");
            var snapshot=CopyMeshSnapshot(groups,worldToFrame,includeHidden,job);
            var meshes=snapshot.Meshes;var parts=snapshot.Parts;var exclusions=snapshot.Exclusions;var sourceMeshes=snapshot.Sources;long vertices=snapshot.Vertices,triangles=snapshot.Triangles;
            var centersReport=centerOptions==null?null:CollectCenters(centerOptions);
            // Unity access ends here. No frame is yielded while copying centers/mesh/transform state.
            Observe();VisualGuard(args);var identity=JToken.FromObject(Identity());int[] partIds=resolved["partIds"].Values<int>().ToArray();string captureId=job.Id;
            var manifest=new JObject{["captureId"]=captureId,["identity"]=identity,["capturedAt"]=DateTime.UtcNow.ToString("o"),["capturedFrame"]=Time.frameCount,["backend"]="cpu_mesh_analysis",["style"]="opaque_two_sided_group_colors_flat_lighting",["nativeMaterials"]=false,["frame"]=frame.DeepClone(),["units"]="metres",["frameToWorldRows"]=MatrixRows(frameToWorld),["matrixOrder"]="rows; column vectors",["groups"]=groups.DeepClone(),["parts"]=parts,["exclusions"]=exclusions,["complete"]=exclusions.Count==0,["triangleCount"]=triangles,["vertexCount"]=vertices,["includeHidden"]=includeHidden,["warnings"]=new JArray("Analysis uses actual mesh triangles, opaque two-sided surfaces and group colors. Textures, alpha cutouts, shader deformation, native paint and decals are not reproduced.","Part labels are limited to 32 per view; use ID images or visual.pick for precise identification. No collision or physical-support conclusion is implied.")};
            manifest["sourceMeshes"]=sourceMeshes;manifest["rendererPolicy"]="Native PartMaterial renderer registry plus owned skinned meshes; editor HideDuringScreenshot helpers and non-surface effects excluded.";
            if(centersReport!=null){manifest["centersReport"]=centersReport;manifest["style"]="neutral_mesh_with_centers_overlay";manifest["warnings"]=new JArray("Actual triangle surfaces use neutral gray with green focus. Textures, native paint, transparency and shader deformation are not reproduced.","Whole-aircraft centers are overlaid irrespective of visual groups. Center markers are annotations, not surface hits; raw/ID images remain unmodified. No flight stability or physical-support conclusion is implied.");}
            var task=Task.Run(()=>VisualCore.Render(meshes.ToArray(),partIds,views,width,height,details,manifest,()=>{lock(job.Sync)return job.CancelRequested;}));
            await UniTask.WaitUntil(()=>task.IsCompleted);if(task.IsFaulted)throw task.Exception.InnerException;var result=task.Result;
            lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Capture cancelled before publication.");
            bool stale=Designer.Instance!=d||d.Aircraft!=aircraft;if(!stale){Observe();EnsureDesignerSceneIntegrity(d);stale=fingerprint!=(string)identity["fingerprint"];}
            result.Manifest["staleAtDelivery"]=stale;if(result.Manifest["centersReport"] is JObject cr)cr["staleAtDelivery"]=stale;result.Manifest["files"]=new JArray(result.Files.Select(f=>new JObject{["name"]=f.Key,["bytes"]=f.Value.Length,["sha256"]=VisualCore.Hash(f.Value),["mimeType"]="image/png"}));
            result.Files["manifest.json"]=Encoding.UTF8.GetBytes(result.Manifest.ToString());SaveVisual(captureId,result);
            var response=new JObject{["captureId"]=captureId,["identity"]=identity.DeepClone(),["geometryStamp"]=result.Manifest["geometryStamp"],["complete"]=manifest["complete"],["staleAtDelivery"]=stale,["artifactBase"]="v1/visual/"+captureId+"/",["files"]=new JArray(result.Files.Select(f=>new JObject{["name"]=f.Key,["bytes"]=f.Value.Length,["sha256"]=VisualCore.Hash(f.Value)})),["recommendedImages"]=result.Manifest["recommendedImages"].DeepClone(),["imageRecommendations"]=result.Manifest["imageRecommendations"].DeepClone(),["detailStatus"]=result.Manifest["detailStatus"].DeepClone(),["scalePolicy"]=result.Manifest["scalePolicy"],["comparisonGuidance"]=result.Manifest["comparisonGuidance"],["exclusions"]=exclusions.DeepClone(),["warnings"]=manifest["warnings"].DeepClone(),["retention"]="Up to 15 minutes, 3 captures or 192 MiB per game process; local downloads persist."};
            if(result.Manifest["centersReport"]!=null)response["centersReport"]=result.Manifest["centersReport"].DeepClone();return response;
        }
        private void TrimVisual(){foreach(string key in visualSaved.Where(p=>(DateTime.UtcNow-p.Value.Created).TotalMinutes>15).Select(p=>p.Key).ToArray())visualSaved.Remove(key);}
        private void SaveVisual(string id,VisualCore.Result result){long bytes=result.Files.Values.Sum(b=>(long)b.Length)+result.Views.Values.Sum(v=>(long)v.Ids.Length*4);if(bytes>192*1024*1024)throw new ApiError("render_budget","Capture exceeds retention memory budget.");lock(visualGate){TrimVisual();while(visualSaved.Count>=3||visualSaved.Values.Sum(v=>v.Bytes)+bytes>192*1024*1024)visualSaved.Remove(visualSaved.OrderBy(p=>p.Value.Created).First().Key);visualSaved[id]=new VisualSaved{Id=id,Created=DateTime.UtcNow,Result=result,Bytes=bytes};}}
        internal byte[] VisualArtifact(string id,string file){lock(visualGate){TrimVisual();if(!visualSaved.TryGetValue(id,out VisualSaved saved)||!saved.Result.Files.TryGetValue(file,out byte[] bytes))throw new ApiError("artifact_expired","Visual artifact unavailable; download results promptly.");return bytes;}}
        private JObject VisualPick(JObject a){VisualScope.Keys(a,"captureId","view","x","y");string id=VisualScope.String(a["captureId"],"captureId"),view=VisualScope.String(a["view"],"view");int x=VisualScope.Integer(a["x"],"x",0),y=VisualScope.Integer(a["y"],"y",0);lock(visualGate){TrimVisual();if(!visualSaved.TryGetValue(id,out VisualSaved s))throw new ApiError("artifact_expired","Capture is no longer retained.");if(!s.Result.Views.TryGetValue(view,out VisualCore.Image img))throw new ApiError("invalid_view","Pick a view name from manifest, not overview.");if(x>=img.Width||y>=img.Height)throw new ApiError("invalid_input","Pixel outside image.");int token=img.Ids[y*img.Width+x];var entry=((JArray)s.Result.Manifest["partIdPalette"]).FirstOrDefault(p=>p.Value<int>("index")==token);return new JObject{["captureId"]=id,["view"]=view,["x"]=x,["y"]=y,["partId"]=entry?["partId"],["capturedIdentity"]=s.Result.Manifest["identity"].DeepClone(),["meaning"]="Pixel identifies captured mesh surface, including behind text annotations. Re-query current identity before editing."};}}
    }
}
