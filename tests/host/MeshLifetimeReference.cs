using System;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using Assets.Scripts.Bindings.Manifold;
using Assets.Scripts.Craft.MeshGen;
using HarmonyLib;
using Newtonsoft.Json.Linq;
using Unity.Collections;
using Unity.Mathematics;

namespace SP2Acceptance
{
    internal static class MeshLifetimeReference
    {
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void Original(Manifold<Vertex> manifold, NativeMesh mesh, ulong submeshMask)
        { throw new InvalidOperationException("Native reverse patch was not installed."); }
        internal static JObject Run(Harmony harmony)
        {
            harmony.CreateReversePatcher(typeof(ManifoldUtils).GetMethod("ConvertManifoldToNativeMesh"),
                new HarmonyMethod(typeof(MeshLifetimeReference).GetMethod("Original",BindingFlags.Static|BindingFlags.NonPublic))).Patch();
            var assembly=AppDomain.CurrentDomain.GetAssemblies().Single(a=>a.GetName().Name=="SP2BuildAssistant");
            var repaired=assembly.GetType("SP2BuildAssistant.NativeMeshLifetime").GetMethod("Convert",BindingFlags.Static|BindingFlags.NonPublic);
            var checks=new JArray();var heaps=new JArray();
            foreach(int[] materials in new[]{new[]{0,1,30},new[]{0,1,30,31}})
            using(var source=new NativeMesh(96,48,Allocator.Temp)) {
                foreach(int material in materials) {
                    source.SetRunMaterial(material);
                    new Geometry.Box{center=new float3(material*3,0,0),extents=new float3(.5f),rotation=quaternion.identity}.draw(source);
                }
                using(var solid=source.ToManifold(Allocator.Temp,out var error)){
                    if(error!=Error.NO_ERROR || solid==null)throw new InvalidOperationException("Test solid creation failed: "+error);
                    foreach(ulong mask in new[]{0UL,1UL,2UL,3UL,1UL<<30,1UL<<31,ulong.MaxValue}){
                        using(var expected=new NativeMesh(0,0,Allocator.Temp))
                        using(var actual=new NativeMesh(0,0,Allocator.Temp)){
                            Original(solid,expected,mask);
                            repaired.Invoke(null,new object[]{solid,actual,mask});
                            bool same=Equal(expected,actual);
                            checks.Add(new JObject{["materials"]=new JArray(materials),["mask"]=mask.ToString(),["passed"]=same,["vertices"]=actual.Vertices.Length,
                                ["triangles"]=actual.Triangles.Length,["runs"]=actual.Runs.Length});
                            if(!same)throw new InvalidOperationException("Native conversion mismatch for mask "+mask);
                        }
                    }
                    if(materials.Length==3){
                        // Warm both paths first; the old path is intentionally
                        // exercised only on this small synthetic solid.
                        for(int pass=0;pass<2;pass++){
                            var before=Win32HeapProbe.ReadDefault();
                            for(int repeat=0;repeat<100;repeat++)
                            using(var output=new NativeMesh(0,0,Allocator.Temp)){
                                if(pass==0)Original(solid,output,ulong.MaxValue);
                                else repaired.Invoke(null,new object[]{solid,output,ulong.MaxValue});
                            }
                            var after=Win32HeapProbe.ReadDefault();
                            heaps.Add(new JObject{["path"]=pass==0?"original":"repaired",["conversions"]=100,
                                ["before"]=JObject.FromObject(before),["after"]=JObject.FromObject(after)});
                        }
                    }
                }
            }
            return new JObject{["checks"]=checks,["heapComparison"]=heaps,["passed"]=true,
                ["evidence"]="real native Burst conversion vs repaired managed entry; every vertex, normal, triangle and material run compared",
                ["scope"]="three and four disjoint boxes, material IDs 0/1/30/31 and seven masks; filtered/unfiltered paths; 114 original conversions intentionally exercise the original lifetime bug on small synthetic solids"};
        }
        private static bool Equal(NativeMesh a,NativeMesh b)
        {
            if(a.Vertices.Length!=b.Vertices.Length || a.Triangles.Length!=b.Triangles.Length || a.Runs.Length!=b.Runs.Length)return false;
            for(int i=0;i<a.Vertices.Length;i++)if(!a.Vertices[i].position.Equals(b.Vertices[i].position)||!a.Vertices[i].normal.Equals(b.Vertices[i].normal))return false;
            for(int i=0;i<a.Triangles.Length;i++)if(!a.Triangles[i].Equals(b.Triangles[i]))return false;
            for(int i=0;i<a.Runs.Length;i++)if(a.Runs[i].MaterialId!=b.Runs[i].MaterialId||a.Runs[i].StartTriangles!=b.Runs[i].StartTriangles)return false;
            return true;
        }
    }
}
