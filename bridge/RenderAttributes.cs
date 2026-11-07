using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant {
    public sealed partial class BuildRuntime {
        // Called on the Unity thread, after native CSG/modifier rebuilding settled.
        // Never calls RecalculateNormals or mutates the renderer/material/mesh.
        private JObject ReadRenderAttributes(Mesh source,Renderer renderer,Matrix4x4 matrix,VisualCore.MeshData clean,string[] requested) {
            var result=new JObject{["source"]="final_owned_render_surface",["renderer"]=renderer.name,["rendererId"]=renderer.GetInstanceID(),
                ["meshId"]=source.GetInstanceID(),["meshName"]=source.name,["rendererType"]=renderer.GetType().Name,
                ["requested"]=new JArray(requested),["meshToFrameRows"]=MatrixRows(matrix),
                ["normalTransform"]="inverse_transpose_normalized",["winding"]="native_indices_preserved",
                ["windingParity"]=matrix.determinant<0?-1:1,["shaderDisplacementIncluded"]=false};
            bool invertible=VisualCore.Finite(matrix.determinant)&&Math.Abs(matrix.determinant)>1e-12;
            var normalMatrix=matrix.inverse.transpose;
            Vector3[] normals=requested.Contains("normals")||requested.Contains("tangents")?source.normals:null;
            var ns=new JArray();bool normalValid=invertible&&normals!=null&&normals.Length==source.vertexCount;
            if(normalValid)foreach(int i in clean.SourceVertexIndices){
                var n=normalMatrix.MultiplyVector(normals[i]);
                if(!ValidDirection(n)){normalValid=false;break;}n.Normalize();ns.Add(new JArray(n.x,n.y,n.z));
            }
            if(requested.Contains("normals")){
                result["normalsStatus"]=normalValid?"available":"unavailable";
                result["normals"]=normalValid?(JToken)ns:JValue.CreateNull();
                if(!normalValid)result["normalsReason"]=!invertible?"singular_transform":"missing_mismatched_or_invalid_native_normals";
            }
            if(requested.Contains("tangents")){
                var tangents=source.tangents;bool valid=normalValid&&tangents.Length==source.vertexCount;var ts=new JArray();
                if(valid)foreach(int i in clean.SourceVertexIndices){
                    var t=tangents[i];var n=normalMatrix.MultiplyVector(normals[i]).normalized;
                    var direction=matrix.MultiplyVector(new Vector3(t.x,t.y,t.z));direction-=n*Vector3.Dot(n,direction);
                    if(!ValidDirection(direction)||!VisualCore.Finite(t.w)||Math.Abs(t.w)<1e-6){valid=false;break;}
                    direction.Normalize();ts.Add(new JArray(direction.x,direction.y,direction.z,t.w*(matrix.determinant<0?-1:1)));
                }
                result["tangentsStatus"]=valid?"available":"unavailable";result["tangents"]=valid?(JToken)ts:JValue.CreateNull();
                result["tangentTransform"]="linear_then_orthogonalize_to_normal; handedness *= transform determinant sign";
                if(!valid)result["tangentsReason"]="missing_mismatched_invalid_native_tangents_or_normals";
            }
            var remap=new Dictionary<int,int>();for(int i=0;i<clean.SourceVertexIndices.Length;i++)remap[clean.SourceVertexIndices[i]]=i;
            var submeshes=new JArray();
            for(int s=0;s<source.subMeshCount;s++){
                if(source.GetTopology(s)!=MeshTopology.Triangles)continue;
                var original=source.GetTriangles(s);var mapped=new List<int>();
                for(int i=0;i<original.Length;i+=3)if(remap.ContainsKey(original[i])&&remap.ContainsKey(original[i+1])&&remap.ContainsKey(original[i+2])){
                    mapped.Add(remap[original[i]]);mapped.Add(remap[original[i+1]]);mapped.Add(remap[original[i+2]]);
                }
                submeshes.Add(new JObject{["index"]=s,["materialSlot"]=s,["indices"]=new JArray(mapped)});
            }
            result["submeshes"]=submeshes;
            result["materials"]=new JArray(renderer.sharedMaterials.Select((m,i)=>new JObject{["slot"]=i,["name"]=m?.name,["shader"]=m?.shader?.name}));
            result["attributeStamp"]=VisualCore.Hash(System.Text.Encoding.UTF8.GetBytes(result.ToString(Newtonsoft.Json.Formatting.None)));
            return result;
        }
        private static bool ValidDirection(Vector3 value){return VisualCore.Finite(value.x)&&VisualCore.Finite(value.y)&&VisualCore.Finite(value.z)&&value.sqrMagnitude>1e-18f;}
    }
}
