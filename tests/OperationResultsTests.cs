using System;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;

class OperationResultsTests
{
    static int checks;
    static void Check(string name, bool passed) { if (!passed) throw new Exception(name); checks++; Console.WriteLine("PASS " + name); }
    static JObject Result(string value) { return new JObject { ["success"] = true, ["schemaVersion"] = "1", ["data"] = new JObject { ["value"] = value } }; }
    static void Main()
    {
        DateTime now = new DateTime(2026, 10, 4, 0, 0, 0, DateTimeKind.Utc);
        var cache = new OperationResults(65536, TimeSpan.FromMinutes(15), () => now);
        var source = Result("飞机\"\\\n2026-10-04T00:00:00.000Z");
        source["data"]["decimal"] = 0.1234567890123456789012345678m;
        source["data"]["integer"] = long.MaxValue;
        string exact = source.ToString(Formatting.None);
        Check("store accepts normal result", cache.Save("one", source));
        source["data"]["value"] = "changed";
        Check("frozen JSON preserves unicode decimals timestamps and int64", cache.Read("one") == exact);
        var job = new Job { Id="job", Key="request", Signature="signature", Results=cache, Input=new JObject { ["xml"] = new string('x',10000) } };
        Check("queued job has no result", (string)job.View()["state"] == "queued" && job.View()["result"].Type == JTokenType.Null);
        job.State = "running";
        job.Complete(Result(new string('z',10000)));
        Check("completed input is released", job.Input == null);
        var view = JObject.Parse(job.View().ToString(Formatting.None));
        Check("wire result remains an object not quoted JSON", view["result"].Type == JTokenType.Object && (bool)view["result"]["success"]);
        Check("completed outcome reported", (string)view["completionState"] == "succeeded" && (string)view["state"] == "succeeded");
        long packed = (long)cache.Describe()["compressedBytes"];
        Check("compression retains fewer bytes for XML like payload", packed < 1000 && (long)cache.Describe()["uncompressedJsonBytes"] > 10000);
        now = now.AddMinutes(14.9);
        Check("read survives before deadline", cache.Read("job") != null);
        now = now.AddMinutes(.1);
        view = job.View();
        Check("age expiration works on read without a new POST", (string)view["state"] == "result_expired" && (string)view["completionState"] == "succeeded");
        Check("expiration leaves dedup identity intact", job.Key == "request" && job.Signature == "signature" && job.Id == "job");
        Check("expired payload accounting is zero", (long)cache.Describe()["compressedBytes"] == 0 && (int)cache.Describe()["retainedResults"] == 0);
        var small = new OperationResults(500);
        var oldest = new Job { Id="old", Results=small, Input=new JObject() }; oldest.Complete(Result(new string('a',500)));
        for (int i=0;i<30;i++) small.Save("n"+i,Result(new string((char)('b'+i%20),500)));
        Check("capacity never exceeds byte budget", (long)small.Describe()["compressedBytes"] <= 500 && (long)small.Describe()["expiredByCapacity"] > 0);
        Check("oldest expires and newest remains", (string)oldest.View()["state"] == "result_expired" && small.Read("n29") != null);
        var tiny = new OperationResults(1);
        var tooBig = new Job { Id="big", Results=tiny, Input=new JObject() }; tooBig.Complete(Result("done"));
        Check("oversized response preserves execution outcome and frees input", (string)tooBig.View()["state"] == "result_expired" && (string)tooBig.View()["completionState"] == "succeeded" && (string)tooBig.View()["resultRetention"] == "single_result_exceeds_capacity" && tooBig.Input == null);
        var cancel = new Job { Id="cancel", Results=cache, Input=new JObject() };
        cancel.Complete(new JObject { ["success"]=false,["error"]=new JObject { ["code"]="cancelled" } });
        Check("cancelled job releases input and retains cancellation", cancel.Input == null && (string)cancel.View()["state"] == "cancelled");
        var failed = new Job { Id="failed", Results=cache, Input=new JObject() };
        failed.Complete(new JObject { ["success"]=false,["error"]=new JObject { ["code"]="revision_conflict" } });
        Check("failure keeps original outcome", (string)failed.View()["completionState"] == "failed");
        var slow = new Job { Id="slow", Results=cache, Input=new JObject(), Created=DateTime.UtcNow.AddDays(-1) };
        slow.Complete(Result("just finished"));
        Check("old submission gets full retention after completion", (string)slow.View()["state"] == "succeeded");
        var concurrent = new OperationResults(32768);
        Parallel.For(0,200,i => { concurrent.Save("p"+i,Result(new string('v',1000))); concurrent.Read("p"+i); concurrent.Describe(); });
        Check("concurrent trim get and store remain within budget", (long)concurrent.Describe()["compressedBytes"] <= 32768);
        Console.WriteLine("Checks passed: " + checks);
    }
}
