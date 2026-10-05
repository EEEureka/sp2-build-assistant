using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
namespace SP2BuildAssistant { internal sealed class ApiError:Exception { public string Code; public ApiError(string code,string message):base(message){Code=code;} } }
class ReadModelsTests
{
    static int passed;
    static void Check(string label,bool value) { if(!value)throw new Exception(label);passed++;Console.WriteLine("PASS "+label); }
    static void Reject(string label,string code,Action action) { try{action();}catch(ApiError e){Check(label,e.Code==code);return;}throw new Exception(label); }
    static void Main(string[] args)
    {
        try { Run(args); }
        catch(Exception error) { Console.WriteLine("FAIL "+error.GetType().FullName+": "+error.Message); Console.WriteLine(error.StackTrace); Environment.Exit(1); }
    }
    static void Run(string[] args)
    {
        Check("Default read view preserves legacy",ReadModels.View(new JObject())=="legacy");
        Check("Structured view accepted",ReadModels.View(JObject.Parse("{view:'structured'}"))=="structured");
        Reject("Unknown view rejected","invalid_input",()=>ReadModels.View(JObject.Parse("{view:'typo'}")));
        Check("Missing connection collection is empty",ReadModels.Connections(null).Count==0);
        var rows=ReadModels.Connections(XElement.Parse("<Connections><Connection partA='4' partB='7' attachPointsA='1,2' attachPointsB='3,4'/></Connections>"));
        Check("Multi-point connection remains a single row with both sets",rows.Count==1&&(int)rows[0]["partA"]==4&&((JArray)rows[0]["attachPointsA"]).Count==2&&(int)rows[0]["attachPointsB"][1]==4);
        Reject("Bad native ID is not converted to zero","invalid_native_data",()=>ReadModels.Connections(XElement.Parse("<Connections><Connection partA='bad' partB='7'/></Connections>")));
        var setters=ReadModels.Setters(XElement.Parse("<Variables><Setter variable='A' function='clamp(IAS,0,1)'/><Setter variable='B' function='A' priority='2' activator='GearDown'/></Variables>"));
        Check("Setter order and optional defaults preserved",setters.Count==2&&(int)setters[1]["index"]==1&&(string)setters[0]["function"]=="clamp(IAS,0,1)"&&(int)setters[0]["priority"]==0&&(string)setters[0]["activator"]==null&&(string)setters[1]["activator"]=="GearDown");
        Check("No variables is empty list",ReadModels.Setters(null).Count==0);
        Check("Reorder specifies old indices in new sequence",ReadModels.Reorder(JArray.Parse("[2,0,1]"),3).SequenceEqual(new[]{2,0,1}));
        Check("Empty reorder supported for zero setters",ReadModels.Reorder(new JArray(),0).Length==0);
        foreach(string invalid in new[]{"[0.1,1,2]","['0',1,2]","[0,0,2]","[-1,1,2]","[0,1,3]","[0,1]","[0,null,2]","[0,1,99999999999999999999999999999]","null","{}"})
            Reject("Reject non-permutation "+invalid,"invalid_order",()=>ReadModels.Reorder(JToken.Parse(invalid),3));
        if(args.Length>0) {
            var snapshot=JObject.Parse(File.ReadAllText(args[0]))["data"];var xml=XElement.Parse((string)snapshot["xml"]);
            var nativeConnections=xml.Element("Assembly").Element("Connections").Elements("Connection").ToArray();
            var flat=ReadModels.Connections(xml.Element("Assembly").Element("Connections"));
            Check("Real aircraft connection count preserved",flat.Count==nativeConnections.Length);
            Check("Real endpoints and AP sets preserved",flat.Cast<JObject>().Select((row,i)=>(int)row["partA"]==(int)nativeConnections[i].Attribute("partA")&&(int)row["partB"]==(int)nativeConnections[i].Attribute("partB")&&string.Join(",",row["attachPointsA"].Values<int>())==(string)nativeConnections[i].Attribute("attachPointsA")&&string.Join(",",row["attachPointsB"].Values<int>())==(string)nativeConnections[i].Attribute("attachPointsB")).All(x=>x));
            var nativeSetters=xml.Element("Variables").Elements("Setter").ToArray();var flatSetters=ReadModels.Setters(xml.Element("Variables"));
            Check("Real variable functions and order preserved",flatSetters.Count==nativeSetters.Length&&flatSetters.Cast<JObject>().Select((row,i)=>(int)row["index"]==i&&(string)row["variable"]==(string)nativeSetters[i].Attribute("variable")&&(string)row["function"]==(string)nativeSetters[i].Attribute("function")).All(x=>x));
        }
        Console.WriteLine("Read model checks: "+passed);
    }
}
