using System;
using System.Reflection;
using System.Threading;
using Assets.Scripts.Bindings.Manifold;
using Assets.Scripts.Craft.MeshGen;
using BepInEx.Logging;
using HarmonyLib;
using Unity.Collections;

namespace SP2BuildAssistant
{
    // Game 0.7.8.103's ManifoldToNativeMeshJob omits MeshGL destruction on
    // both return paths. Temp frees the C++ object's storage, not its vectors.
    // Patch the synchronous entry, rather than a Burst job that can bypass IL
    // patches. Keep this compatibility repair restricted to the audited game
    // module and designer; never mutate the shipped Game.dll.
    internal static class NativeMeshLifetime
    {
        private const string AuditedModule = "9a77ca27-8013-4b89-8277-214a341b1af2";
        private static bool installed;
        private static long conversions, releases;
        internal static void Install(Harmony harmony, ManualLogSource log)
        {
            if (typeof(ManifoldUtils).Assembly.ManifestModule.ModuleVersionId.ToString() != AuditedModule) {
                log.LogWarning("Native mesh lifetime repair is unavailable for this unaudited game module.");
                return;
            }
            harmony.Patch(typeof(ManifoldUtils).GetMethod("ConvertManifoldToNativeMesh"),
                prefix:new HarmonyMethod(typeof(NativeMeshLifetime).GetMethod("Prefix",BindingFlags.Static|BindingFlags.NonPublic)));
            installed=true;
            log.LogInfo("Designer native mesh lifetime repair installed for Game 0.7.8.103.");
        }
        internal static object Describe() { return new { installed, auditedGameModule=AuditedModule,
            conversions=Interlocked.Read(ref conversions), releases=Interlocked.Read(ref releases),
            scope="designer Manifold-to-NativeMesh temporary C++ object lifetime" }; }
        private static bool Prefix(Manifold<Vertex> manifold, NativeMesh mesh, ulong submeshMask)
        {
            if(UnityEngine.SceneManagement.SceneManager.GetActiveScene().name!="Designer")return true;
            Convert(manifold,mesh,submeshMask);
            return false;
        }
        internal static void Convert(Manifold<Vertex> manifold, NativeMesh mesh, ulong submeshMask)
        {
            mesh.Clear();
            submeshMask &= 0x7FFFFFFFUL; // Preserve the native entry's material mask.
            var source=MeshGL<Vertex>.Create(Allocator.Temp,manifold,Vertex.OffsetOfNormal());
            Interlocked.Increment(ref conversions);
            try {
                // Preserve native array lengths/order, including its unused
                // vertex tail; callers may depend on these native semantics.
                mesh.Vertices.Length=checked((int)(ulong)source.VertPropertiesLength);
                source.GetVertices(mesh.Vertices.AsArray());
                var runs=new MeshGLBase.Run[source.GetRunDataLength()];
                if(source.GetRunData(runs)!=runs.Length)throw new InvalidOperationException("Invalid native material run table.");
                if(mesh.Runs.Capacity<runs.Length)mesh.Runs.Capacity=runs.Length;
                bool filtered=false;
                foreach(var run in runs)if((submeshMask & (1UL<<(int)run.OriginalID))==0){filtered=true;break;}
                int indexCount=checked((int)(ulong)source.IndexCount);
                if(!filtered){
                    mesh.Triangles.Length=indexCount/3;
                    source.GetIndices(mesh.Triangles.AsArray().Reinterpret<uint>(12));
                    foreach(var run in runs)mesh.Runs.AddNoResize(new NativeMesh.TriangleRun {
                        MaterialId=(int)run.OriginalID,StartTriangles=(int)run.StartIndex/3 });
                    return;
                }
                int kept=0;
                foreach(var run in runs)if((submeshMask & (1UL<<(int)run.OriginalID))!=0)
                    kept=checked(kept+(int)(run.EndIndex-run.StartIndex));
                using(var indices=new NativeArray<uint>(indexCount,Allocator.Temp)){
                    source.GetIndices(indices);
                    mesh.Triangles.Length=kept/3;
                    var dest=mesh.Triangles.AsArray().Reinterpret<uint>(12);
                    int offset=0;
                    foreach(var run in runs){
                        if((submeshMask & (1UL<<(int)run.OriginalID))==0)continue;
                        int length=(int)(run.EndIndex-run.StartIndex);
                        dest.GetSubArray(offset,length).CopyFrom(indices.GetSubArray((int)run.StartIndex,length));
                        mesh.Runs.AddNoResize(new NativeMesh.TriangleRun{MaterialId=(int)run.OriginalID,StartTriangles=offset/3});
                        offset+=length;
                    }
                }
            } finally {
                source.Dispose(); // Calls manifold_destruct_meshgl AND frees storage.
                Interlocked.Increment(ref releases);
            }
        }
    }
}
