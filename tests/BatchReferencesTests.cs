using System;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
namespace SP2BuildAssistant { internal sealed class ApiError:Exception { public string Code; public ApiError(string code,string message):base(message){Code=code;} } }
class BatchReferencesTests
{
    static int passed;
    static JObject P(int id,string type="Missile",string name="original") { return new JObject{["id"]=id,["type"]=type,["name"]=name}; }
    static void Check(string label,bool value) { if(!value)throw new Exception(label);passed++;Console.WriteLine("PASS "+label); }
    static void Reject(string label,string code,Action a) {try{a();}catch(ApiError e){Check(label,e.Code==code);return;}throw new Exception(label);}
    static void Main()
    {
        var r=new BatchReferences(new[]{P(214),P(19,"Wing")});
        r.OperationIndex=0;r.Observe(new[]{P(19,"Wing")});
        Reject("Deleted numeric reference fails before reuse","stale_part_reference",()=>r.Resolve(new JValue(214)));
        r.OperationIndex=1;r.Add("pod-new",214);r.Observe(new[]{P(214,"Pod","new"),P(19,"Wing")});
        Check("New temporary binding resolves recycled ID",r.Resolve(new JValue("pod-new"))==214);
        Reject("Old integer cannot target replacement","stale_part_reference",()=>r.Resolve(new JValue(214)));
        Check("Reuse has both identities and operation indices",(string)r.ReusedPartIds[0]["previous"]["type"]=="Missile"&&(string)r.ReusedPartIds[0]["current"]["type"]=="Pod"&&(int)r.ReusedPartIds[0]["deletedAtOperationIndex"]==0&&(int)r.ReusedPartIds[0]["createdAtOperationIndex"]==1);
        r.OperationIndex=2;r.Observe(new[]{P(214,"Pod","renamed"),P(19,"Wing")});
        Check("Native rebuild and rename preserve logical reference",r["pod-new"]==214&&r.ReusedPartIds.Count==1);
        r.OperationIndex=3;r.Observe(new[]{P(19,"Wing")});
        Reject("Deleted temporary reference is rejected","deleted_temporary_reference",()=>r.Resolve(new JValue("pod-new")));
        r.OperationIndex=4;r.Add("pod-newer",214);r.Observe(new[]{P(214,"Pod","newest"),P(19,"Wing")});
        Reject("Old temporary reference cannot follow same-type replacement","deleted_temporary_reference",()=>r.Resolve(new JValue("pod-new")));
        Check("Repeated reuse retains distinct events",r.ReusedPartIds.Count==2&&(string)r.ReusedPartIds[1]["previous"]["name"]=="renamed");
        Check("Only live bindings are returned",r.LiveBindings["pod-new"]==null&&(int)r.LiveBindings["pod-newer"]==214&&r.InvalidatedBindings.Count==1);
        Reject("Deleted temporary names cannot be rebound","duplicate_temporary_id",()=>r.Add("pod-new",214));
        Check("Unrelated parts remain usable",r.Resolve(new JValue(19))==19);
        Reject("Unknown temporary name stays explicit","temporary_id_not_found",()=>r.Resolve(new JValue("missing")));
        Reject("Invalid reference shape cannot coerce","invalid_part_reference",()=>r.Resolve(new JValue(true)));
        var many=new BatchReferences(new[]{P(1),P(2),P(3)});many.Observe(new JObject[0]);many.Add("root",1);many.Observe(new[]{P(1),P(2),P(3)});
        Check("All template/symmetry child ID reuse is reported",many.ReusedPartIds.Count==3);
        Console.WriteLine("Batch reference checks: "+passed);
    }
}
