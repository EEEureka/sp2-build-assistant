using System;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Cysharp.Threading.Tasks;
using Assets.Scripts.Design;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private async UniTask<JObject> GeometryQuery(string command,JObject a,Job job)
        {
            VisualScope.Keys(a,"craftSessionId","expectedRevision","partIds","partIdsA","partIdsB","frame","plane","region","sampleSpacingMetres","limit","includeHidden","export","exportMeshes","source");
            bool exportMeshes=VisualScope.Boolean(a["exportMeshes"],"exportMeshes");
            if(exportMeshes&&!VisualScope.Boolean(a["export"],"export"))throw new ApiError("invalid_input","exportMeshes requires export:true; meshes are local artifacts, not inline response fields.");
            var clock=System.Diagnostics.Stopwatch.StartNew();var timings=new JObject();
            Observe();VisualGuard(a);var d=Current();var aircraft=d.Aircraft;await ReadSettled(d,null);Observe();VisualGuard(a);timings["observeAndSettleMs"]=clock.Elapsed.TotalMilliseconds;double stage=clock.Elapsed.TotalMilliseconds;
            bool section=command=="geometry.section";var first=PartIds(a[section?"partIds":"partIdsA"]);var second=section?new int[0]:PartIds(a["partIdsB"]);
            if(first.Intersect(second).Any())throw new ApiError("scope_overlap","Measurement scopes must be disjoint.");
            var f=TransformFrame(a["frame"]);var frameToWorld=Matrix4x4.TRS(f.position,f.rotation,Vector3.one);
            var groups=new JArray(new JObject{["index"]=0,["partIds"]=new JArray(first)});if(!section)groups.Add(new JObject{["index"]=1,["partIds"]=new JArray(second)});
            int limit=a["limit"]==null?64:VisualScope.Integer(a["limit"],"limit",1,1000);
            string source=a.Value<string>("source")??"renderMesh";if(source!="renderMesh"&&source!="collider")throw new ApiError("invalid_input","source is renderMesh or collider.");
            var snap=source=="collider"?CopyColliderSnapshot(groups,frameToWorld.inverse,VisualScope.Boolean(a["includeHidden"],"includeHidden"),job):CopyMeshSnapshot(groups,frameToWorld.inverse,VisualScope.Boolean(a["includeHidden"],"includeHidden"),job);
            var identity=JToken.FromObject(Identity());int capturedFrame=Time.frameCount;timings["copyMainThreadMs"]=clock.Elapsed.TotalMilliseconds-stage;stage=clock.Elapsed.TotalMilliseconds;
            var plane=a["plane"] as JObject;var region=a["region"] as JObject;
            VisualCore.V origin=new VisualCore.V(),normal=new VisualCore.V(0,1,0);VisualCore.V? min=null,max=null;
            if(command!="geometry.measure") {VisualScope.Keys(plane,"origin","normal");origin=VV(ReadPosition(plane["origin"]));normal=VV(ReadPosition(plane["normal"])).Unit();}
            else if(a["plane"]!=null||a["region"]!=null)throw new ApiError("invalid_input","geometry.measure queries complete surfaces; use section/seam for a plane/region.");
            if(region!=null){VisualScope.Keys(region,"min","max");min=VV(ReadPosition(region["min"]));max=VV(ReadPosition(region["max"]));if(min.Value.X>=max.Value.X||min.Value.Y>=max.Value.Y||min.Value.Z>=max.Value.Z)throw new ApiError("invalid_input","region.min must be below region.max on every axis.");}
            if(command=="geometry.seam"&&region==null)throw new ApiError("invalid_input","Seam requires an explicit region to avoid comparing unrelated surfaces.");
            if(command=="geometry.symmetry"&&region!=null)throw new ApiError("invalid_input","Symmetry uses complete scoped surfaces; region clipping is not supported.");
            double spacing=a["sampleSpacingMetres"]==null?.001:PropertyValues.Number(a["sampleSpacingMetres"],.00001,1,"sampleSpacingMetres");
            Action cancel=()=>{lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Measurement cancelled.");};
            var task=Task.Run(()=>{
                cancel();var ta=GeometryMeasure.Triangles(snap.Meshes.Where(m=>m.Group==0).ToArray());var tb=GeometryMeasure.Triangles(snap.Meshes.Where(m=>m.Group==1).ToArray());
                if(ta.Length==0||(!section&&tb.Length==0))return new JObject{["status"]="unavailable",["reason"]="No supported readable triangle surface for one or both scopes; inspect exclusions and choose renderMesh or a supported collider."};
                if(command=="geometry.measure")return GeometryMeasure.Report(GeometryMeasure.Distance(ta,tb,cancel));
                if(command=="geometry.symmetry")return GeometryMeasure.Symmetry(ta,tb,origin,normal,spacing,limit,cancel);
                var sa=SectionMeasure.Cut(ta,origin,normal,min,max);if(section)return SectionMeasure.Report(sa,limit);
                var sb=SectionMeasure.Cut(tb,origin,normal,min,max);var report=SectionMeasure.Seam(sa,sb,spacing,limit,cancel);report["sectionA"]=SectionMeasure.Report(sa,0);report["sectionB"]=SectionMeasure.Report(sb,0);return report;
            });
            await UniTask.WaitUntil(()=>task.IsCompleted);if(task.IsFaulted)throw task.Exception.InnerException;cancel();timings["backgroundQueryAndDeliveryMs"]=clock.Elapsed.TotalMilliseconds-stage;stage=clock.Elapsed.TotalMilliseconds;
            bool stale=Designer.Instance!=d||d.Aircraft!=aircraft;if(!stale){Observe();stale=fingerprint!=(string)identity["fingerprint"];}
            var result=new JObject{["identity"]=identity,["sampleId"]=job.Id,["capturedFrame"]=capturedFrame,["staleAtDelivery"]=stale,["source"]=source,["frame"]=a["frame"]?.DeepClone()??new JObject{["kind"]="world"},["frameToWorldRows"]=MatrixRows(frameToWorld),["units"]="metres",
                ["geometryStamp"]=VisualCore.GeometryHash(snap.Meshes),["triangleCount"]=snap.Triangles,["vertexCount"]=snap.Vertices,["complete"]=snap.Exclusions.Count==0,["exclusions"]=snap.Exclusions,["sources"]=snap.Sources,["measurement"]=task.Result,["stageTimings"]=timings,
                ["accuracy"]="Double precision computations on native float mesh samples, including captured transforms. No ideal parametric-surface accuracy claim; shader displacement, paint, decals and transparency require native screenshots.",
                ["cachePolicy"]="Immutable sample per request. No cross-frame Unity geometry cache; dynamic pose may change without an XML revision."};
            if(VisualScope.Boolean(a["export"],"export")){
                var artifact=new VisualCore.Result();artifact.Manifest=(JObject)result.DeepClone();
                artifact.Files["measurement.json"]=Encoding.UTF8.GetBytes(result.ToString());
                if(exportMeshes){
                    var meshData=new JObject{["format"]="indexed_triangles_v1",["sampleId"]=job.Id,["identity"]=identity.DeepClone(),["units"]="metres",["source"]=source,["frameToWorldRows"]=MatrixRows(frameToWorld),["geometryStamp"]=result["geometryStamp"].DeepClone(),["exclusions"]=snap.Exclusions.DeepClone(),
                        ["meshes"]=new JArray(snap.Meshes.Select(m=>new JObject{["partId"]=m.PartId,["groupIndex"]=m.Group,["vertices"]=new JArray(m.Vertices.Select(v=>new JArray(v.X,v.Y,v.Z))),["indices"]=new JArray(m.Indices)}))};
                    byte[] bytes=Encoding.UTF8.GetBytes(meshData.ToString(Newtonsoft.Json.Formatting.None));
                    if(bytes.Length>80*1024*1024)throw new ApiError("geometry_budget","Mesh export exceeds 80 MiB; reduce the selected scope.");
                    artifact.Files["meshes.json"]=bytes;artifact.Manifest["meshArtifact"]="meshes.json";
                }
                artifact.Files["manifest.json"]=Encoding.UTF8.GetBytes(artifact.Manifest.ToString());SaveVisual(job.Id,artifact);
                result["artifactType"]="geometry_measurement";result["artifactBase"]="v1/visual/"+job.Id+"/";result["captureId"]=job.Id;result["files"]=new JArray(artifact.Files.Select(x=>new JObject{["name"]=x.Key,["bytes"]=x.Value.Length,["sha256"]=VisualCore.Hash(x.Value)}));
            }
            return result;
        }
    }
}
