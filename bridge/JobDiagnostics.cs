using System;
using System.Collections.Generic;
using System.Diagnostics;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    internal static class JobDiagnostics
    {
        private static readonly object gate=new object();
        private static readonly Dictionary<string,JObject> entries=new Dictionary<string,JObject>();
        internal static void Update(string id,JObject values)
        {
            lock(gate){JObject row;if(!entries.TryGetValue(id,out row)){if(entries.Count>=20000)return;entries[id]=row=new JObject();}foreach(var field in values.Properties())row[field.Name]=field.Value.DeepClone();}
        }
        internal static JObject View(Job job)
        {
            JObject view=job.View();lock(gate){JObject row;if(entries.TryGetValue(job.Id,out row))view["scheduling"]=row.DeepClone();}return view;
        }
    }
    internal sealed class FrameDiagnostics
    {
        private long previousTicks;
        internal long Samples;
        internal double LastFrameMs,MaxFrameMs;
        internal void Sample(long ticks)
        {
            if(previousTicks>0){LastFrameMs=(ticks-previousTicks)*1000d/Stopwatch.Frequency;MaxFrameMs=Math.Max(MaxFrameMs,LastFrameMs);Samples++;}previousTicks=ticks;
        }
        internal JObject View(){return new JObject{["samples"]=Samples,["lastFrameIntervalMs"]=LastFrameMs,["maxFrameIntervalMs"]=MaxFrameMs,["meaning"]="Observed BuildRuntime.Update intervals, including rendering/OS/other game work; not isolated input latency or proof of an FPS target."};}
    }
}
