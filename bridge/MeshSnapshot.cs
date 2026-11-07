using System;
using System.Collections.Generic;
using System.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Design;
using Newtonsoft.Json.Linq;
using UnityEngine;
namespace SP2BuildAssistant {
    public sealed partial class BuildRuntime {
        private sealed class MeshSnapshot {
            internal VisualCore.MeshData[] Meshes; internal JArray Parts,Exclusions,Sources;
            internal long Vertices,Triangles;
        }
        private MeshSnapshot CopyColliderSnapshot(JArray groups,Matrix4x4 worldToFrame,bool includeHidden,Job job) {
            var meshes=new List<VisualCore.MeshData>();var exclusions=new JArray();var sources=new JArray();long vertices=0,triangles=0;
            foreach(JObject group in groups)foreach(int id in group["partIds"].Values<int>()){
                var ps=Part(id).PartScript;int count=0;
                foreach(var c in ps.GetComponentsInChildren<Collider>(true)){
                    lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Collider snapshot cancelled.");
                    if(c.GetComponentInParent<PartScript>()!=ps||c.isTrigger||c.gameObject.layer==25)continue;
                    if((!c.enabled||!c.gameObject.activeInHierarchy)&&!includeHidden)continue;
                    Vector3[] points=null;int[] indices=null;
                    if(c is MeshCollider mc){if(mc.sharedMesh==null||!mc.sharedMesh.isReadable){exclusions.Add(new JObject{["partId"]=id,["renderer"]=c.name,["reason"]="collider_mesh_unreadable"});continue;}if(mc.convex){exclusions.Add(new JObject{["partId"]=id,["renderer"]=c.name,["reason"]="physx_convex_hull_not_exposed"});continue;}points=mc.sharedMesh.vertices;indices=mc.sharedMesh.triangles;}
                    else if(c is BoxCollider box){points=new Vector3[8];for(int i=0;i<8;i++)points[i]=box.center+Vector3.Scale(box.size,new Vector3((i&1)==0?-.5f:.5f,(i&2)==0?-.5f:.5f,(i&4)==0?-.5f:.5f));indices=new[]{0,2,1,1,2,3,4,5,6,5,7,6,0,1,4,1,5,4,2,6,3,3,6,7,0,4,2,2,4,6,1,3,5,3,7,5};}
                    else{exclusions.Add(new JObject{["partId"]=id,["renderer"]=c.name,["reason"]="analytic_collider_not_triangulated",["type"]=c.GetType().Name});continue;}
                    vertices+=points.Length;triangles+=indices.Length/3;if(vertices>1200000||triangles>500000)throw new ApiError("geometry_budget","Collider sample exceeds budget.");
                    var matrix=worldToFrame*c.transform.localToWorldMatrix;var clean=VisualCore.CleanMesh(new VisualCore.MeshData{PartId=id,Group=group.Value<int>("index"),Vertices=points.Select(v=>VV(matrix.MultiplyPoint3x4(v))).ToArray(),Indices=indices},out int removed);
                    if(removed>0)exclusions.Add(new JObject{["partId"]=id,["reason"]="nonfinite_triangles",["count"]=removed});
                    if(clean.Indices.Length==0)continue;meshes.Add(clean);count++;sources.Add(new JObject{["partId"]=id,["renderer"]=c.name,["capturedTriangles"]=clean.Indices.Length/3,["excludedNonfiniteTriangles"]=removed,["colliderType"]=c.GetType().Name});
                }
                if(count==0)exclusions.Add(new JObject{["partId"]=id,["reason"]="no_supported_collider_surface"});
            }
            return new MeshSnapshot{Meshes=meshes.ToArray(),Exclusions=exclusions,Sources=sources,Parts=new JArray(),Vertices=vertices,Triangles=triangles};
        }
        private MeshSnapshot CopyMeshSnapshot(JArray groups,Matrix4x4 worldToFrame,bool includeHidden,Job job,string[] vertexAttributes=null) {
            var meshes=new List<VisualCore.MeshData>();var parts=new JArray();var exclusions=new JArray();var sourceMeshes=new JArray();var claimed=new HashSet<int>();long vertices=0,triangles=0;
            foreach(JObject group in groups)foreach(int id in group["partIds"].Values<int>()){
                lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Cancelled during geometry capture.");var p=Part(id);var ps=p.PartScript;int count=0;var transform=worldToFrame*ps.transform.localToWorldMatrix;
                parts.Add(new JObject{["partId"]=id,["name"]=p.Name,["groupIndex"]=group["index"],["partToWorldRows"]=MatrixRows(ps.transform.localToWorldMatrix),["partToFrameRows"]=MatrixRows(transform),["visibleInDesigner"]=p.VisibleInDesigner});
                if(!p.VisibleInDesigner&&!includeHidden){exclusions.Add(new JObject{["partId"]=id,["reason"]="hidden_in_designer"});continue;}
                var registered=new HashSet<Renderer>(ps.PartMaterialScript.RendererMaps.Select(m=>(Renderer)m.Renderer).Where(r=>r!=null));
                foreach(var renderer in ps.GetComponentsInChildren<Renderer>(true)){
                    if(renderer.GetComponentInParent<PartScript>()!=ps)continue;
                    // Editor handles, trim previews and particle systems are not part mesh surfaces.
                    if(renderer.GetComponentInParent<HideScript>()?.HideDuringScreenshot==true)continue;
                    if(!registered.Contains(renderer)&&!(renderer is SkinnedMeshRenderer))continue;
                    if(!renderer.enabled||!renderer.gameObject.activeInHierarchy){if(!includeHidden||p.VisibleInDesigner)continue;}
                    if(!claimed.Add(renderer.GetInstanceID()))throw new ApiError("renderer_ownership","A renderer is shared by selected parts.");Mesh source=null,temp=null;
                    try{
                        if(renderer is MeshRenderer){source=renderer.GetComponent<MeshFilter>()?.sharedMesh;}
                        else if(renderer is SkinnedMeshRenderer skin){temp=new Mesh();skin.BakeMesh(temp);source=temp;}
                        else {exclusions.Add(new JObject{["partId"]=id,["renderer"]=renderer.name,["reason"]="unsupported_renderer",["type"]=renderer.GetType().Name});continue;}
                        if(source==null){exclusions.Add(new JObject{["partId"]=id,["renderer"]=renderer.name,["reason"]="missing_mesh"});continue;}
                        if(!source.isReadable){exclusions.Add(new JObject{["partId"]=id,["renderer"]=renderer.name,["reason"]="mesh_not_readable"});continue;}
                        if(vertices+source.vertexCount>(vertexAttributes==null?1200000:250000))throw new ApiError("geometry_budget","Vertex budget exceeded (250000 with attributes; 1200000 positions only). Reduce selected parts.");var raw=source.vertices;var indices=new List<int>();for(int sub=0;sub<source.subMeshCount;sub++){if(source.GetTopology(sub)!=MeshTopology.Triangles){exclusions.Add(new JObject{["partId"]=id,["renderer"]=renderer.name,["reason"]="non_triangle_submesh"});continue;}int[] idx=source.GetTriangles(sub);if(triangles+idx.Length/3>500000)throw new ApiError("geometry_budget","Triangle budget exceeded.");triangles+=idx.Length/3;indices.AddRange(idx);}
                        if(indices.Count==0)continue;vertices+=raw.Length;var matrix=worldToFrame*renderer.localToWorldMatrix;var copied=raw.Select(v=>VV(matrix.MultiplyPoint3x4(v))).ToArray();if(indices.Any(i=>i<0||i>=copied.Length)||indices.Count%3!=0)throw new ApiError("invalid_geometry","Invalid native triangle indices.");
                        var clean=VisualCore.CleanMesh(new VisualCore.MeshData{PartId=id,Group=group.Value<int>("index"),Vertices=copied,Indices=indices.ToArray()},out int removed);
                        if(removed>0){exclusions.Add(new JObject{["partId"]=id,["renderer"]=renderer.name,["reason"]="nonfinite_triangles",["count"]=removed});triangles-=removed;}
                        sourceMeshes.Add(new JObject{["partId"]=id,["renderer"]=renderer.name,["capturedTriangles"]=clean.Indices.Length/3,["excludedNonfiniteTriangles"]=removed});
                        if(clean.Indices.Length==0)continue;
                        if(vertexAttributes!=null)clean.Attributes=ReadRenderAttributes(source,renderer,matrix,clean,vertexAttributes);
                        meshes.Add(clean);count++;
                    }finally{if(temp!=null)UnityEngine.Object.Destroy(temp);}
                }
                if(count==0)exclusions.Add(new JObject{["partId"]=id,["reason"]="no_captured_mesh"});
            }
            return new MeshSnapshot {Meshes=meshes.ToArray(),Parts=parts,Exclusions=exclusions,Sources=sourceMeshes,Vertices=vertices,Triangles=triangles};
        }
    }
}
