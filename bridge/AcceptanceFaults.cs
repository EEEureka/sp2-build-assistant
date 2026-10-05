using System;
using System.IO;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        // The compiler removes calls and file access entirely in the shipping build.
        [System.Diagnostics.Conditional("ACCEPTANCE_HOOKS")]
        private void AcceptanceFault(string stage)
        {
#if ACCEPTANCE_HOOKS
            string path=Path.Combine(BepInEx.Paths.ConfigPath,"sp2build.acceptance-fault.json");
            if(!File.Exists(path))return;
            var fault=JObject.Parse(File.ReadAllText(path));
            if((string)fault["stage"]!=stage)return;
            if(!Current().Aircraft.Aircraft.Name.StartsWith("SP2Build 050 Precision Lab",StringComparison.Ordinal))throw new ApiError("test_fixture_required","Acceptance hooks are restricted to the named test copy.");
            File.Delete(path);
            Log.LogWarning("ACCEPTANCE injected stage="+stage);
            if(fault["pauseMilliseconds"]!=null){
                int delay=(int)fault["pauseMilliseconds"];
                if(delay<1||delay>5000)throw new ApiError("invalid_test_pause","Acceptance pause must be 1..5000 ms.");
                // Deliberately hold this render frame only in acceptance builds.
                // HTTP cancellation still comes through the real public endpoint.
                System.Threading.Thread.Sleep(delay);return;
            }
            throw new ApiError("acceptance_injected_failure","One-shot test-build fault at "+stage,new JObject{["stage"]=stage});
#endif
        }
    }
}
