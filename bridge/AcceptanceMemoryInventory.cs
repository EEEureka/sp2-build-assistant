using System.Diagnostics;
#if ACCEPTANCE_HOOKS
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Profiling;
#endif

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        [Conditional("ACCEPTANCE_HOOKS")]
        private void AcceptanceMemoryInventory()
        {
#if ACCEPTANCE_HOOKS
            string path=Path.Combine(BepInEx.Paths.ConfigPath,"sp2build.acceptance-inventory.json");
            if(!File.Exists(path))return;
            var d=Current();
            if(!d.Aircraft.Aircraft.Name.StartsWith("SP2Build 050 Precision Lab",StringComparison.Ordinal))
                throw new ApiError("test_fixture_required","Object inventory is restricted to named acceptance copies.");
            var request=JObject.Parse(File.ReadAllText(path));VisualScope.Keys(request,"label");
            string label=VisualScope.String(request["label"],"label");
            File.Delete(path);
            // Metadata only, no forced GC/UnloadUnusedAssets, setter, or mesh read.
            var rows=Resources.FindObjectsOfTypeAll<UnityEngine.Object>()
                .Where(o=>o!=null).Select(o=>new {type=o.GetType().FullName,name=o.name,bytes=Profiler.GetRuntimeMemorySizeLong(o)}).ToArray();
            var report=new JObject{["label"]=label,["capturedAt"]=DateTime.UtcNow.ToString("o"),["frame"]=Time.frameCount,
                ["nativeResourceCleanupLastScheduledSeconds"]=JToken.FromObject(typeof(Assets.Scripts.Design.DesignerScript).GetField("_lastResourceCollectionTime",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(d.DesignerScript)),
                ["realtimeSeconds"]=Time.realtimeSinceStartupAsDouble,
                ["totalObjects"]=rows.Length,["sumObjectBytes"]=rows.Sum(x=>x.bytes),
                ["types"]=JArray.FromObject(rows.GroupBy(x=>x.type).Select(g=>new {type=g.Key,count=g.Count(),bytes=g.Sum(x=>x.bytes)}).OrderByDescending(x=>x.bytes)),
                ["duplicates"]=JArray.FromObject(rows.GroupBy(x=>new{x.type,x.name}).Where(g=>g.Count()>1).Select(g=>new {g.Key.type,g.Key.name,count=g.Count(),bytes=g.Sum(x=>x.bytes)}).OrderByDescending(x=>x.bytes).Take(60)),
                ["meaning"]="Test-only global Unity object inventory, not only the current craft; overlapping runtime size estimates, no GC forced. Compiled out of shipping builds."};
            File.WriteAllText(Path.Combine(BepInEx.Paths.ConfigPath,"sp2build.acceptance-inventory.result.json"),report.ToString());
#endif
        }
    }
}
