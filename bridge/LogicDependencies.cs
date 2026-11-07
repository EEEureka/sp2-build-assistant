using System;
using System.Linq;
using System.Collections.Generic;
using System.Xml.Linq;
using Jundroo.Common.Expressions;
using Jundroo.Common.Expressions.Tokens;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static string[] NativeReferencedNames(string expression)
        {
            var names=new HashSet<string>();var pending=new Stack<Token>();pending.Push(Parser.Parse(expression,true));int visited=0;
            while(pending.Count>0){for(var token=pending.Pop();token!=null;token=token.Next){
                if(++visited>10000)throw new ApiError("expression_budget","Native reference scan exceeded 10000 tokens.");
                var group=token as GroupToken;if(group?.First!=null)pending.Push(group.First);
                var name=token as NameToken;
                if(name!=null&&!(name.Prev is MemberAccessorToken)&&(!(name.Next is GroupToken)||name.Name.StartsWith("v:")))names.Add(name.Name.StartsWith("v:")?name.Name.Substring(2):name.Name);
            }}
            return names.OrderBy(s=>s,StringComparer.Ordinal).ToArray();
        }
        private JObject LogicDependencies(JObject args)
        {
            var d=Current();var xml=d.Aircraft.Aircraft.GenerateXml(false);var references=new JArray();var failures=new JArray();
            var declarations=new JArray();var setters=(xml.Element("Variables")?.Elements("Setter")??Enumerable.Empty<XElement>()).ToArray();
            Action<string,string,JObject> record=(expression,field,source)=>{
                if(string.IsNullOrWhiteSpace(expression))return;
                var row=(JObject)source.DeepClone();row["field"]=field;row["expression"]=expression;
                try{row["names"]=new JArray(NativeReferencedNames(expression));references.Add(row);}
                catch(Exception error){row["error"]=error.Message;failures.Add(row);}
            };
            for(int i=0;i<setters.Length;i++){
                var setter=setters[i];declarations.Add(new JObject{["kind"]="setter",["setterIndex"]=i,["variable"]=(string)setter.Attribute("variable"),["priority"]=(int?)setter.Attribute("priority")??0});
                var source=new JObject{["kind"]="setter",["setterIndex"]=i,["variable"]=(string)setter.Attribute("variable")};
                record((string)setter.Attribute("function"),"function",source);record((string)setter.Attribute("activator"),"activator",source);
            }
            foreach(var part in d.Aircraft.Aircraft.Assembly.Parts){
                var state=part.GenerateXml();int index=0;
                foreach(var input in state.Descendants("InputController.State")){
                    var source=new JObject{["kind"]="controller",["partId"]=part.Id,["controllerIndex"]=index++, ["path"]=NativeElementPath(input,state)};
                    record((string)input.Attribute("input"),"input",source);record((string)input.Attribute("activationGroup"),"activationGroup",source);
                }
                foreach(var output in state.Descendants("VariableOutput")){
                    var source=new JObject{["kind"]="output",["partId"]=part.Id,["outputId"]=(string)output.Attribute("id"),["path"]=NativeElementPath(output,state)};
                    var declaration=(JObject)source.DeepClone();declaration["variable"]=(string)output.Attribute("variable");declarations.Add(declaration);
                    record((string)output.Attribute("activator"),"activator",source);
                }
            }
            string selected=(string)args["variable"];
            var providers=declarations.Where(r=>r["variable"]!=null).GroupBy(r=>(string)r["variable"]).ToArray();
            var graph=setters.Where(s=>s.Attribute("variable")!=null).GroupBy(s=>(string)s.Attribute("variable")).ToDictionary(g=>g.Key,g=>references.Where(r=>(string)r["kind"]=="setter"&&(string)r["variable"]==g.Key).SelectMany(r=>r["names"].Values<string>()).Distinct().ToArray());
            var cycles=new JArray();var visited=new HashSet<string>();var active=new List<string>();
            Action<string> visit=null;visit=name=>{
                if(active.Contains(name)){cycles.Add(new JArray(active.Skip(active.IndexOf(name)).Concat(new[]{name})));return;}
                if(!visited.Add(name)||!graph.ContainsKey(name))return;active.Add(name);
                foreach(string child in graph[name])if(graph.ContainsKey(child))visit(child);active.RemoveAt(active.Count-1);
            };foreach(string name in graph.Keys)visit(name);
            return new JObject{["identity"]=JToken.FromObject(Identity()),["variable"]=selected,
                ["declarations"]=selected==null?declarations:new JArray(declarations.Where(r=>(string)r["variable"]==selected)),
                ["references"]=selected==null?references:new JArray(references.Where(r=>r["names"].Values<string>().Contains(selected))),["parseFailures"]=failures,
                ["duplicateProviders"]=new JArray(providers.Where(g=>g.Count()>1).Select(g=>new JObject{["variable"]=g.Key,["providers"]=new JArray(g)})),["possibleCycles"]=cycles,
                ["source"]="native_Parser.Parse_NameToken_graph_without_evaluation",["unknownExpressionFields"]=true,
                ["coverage"]="Native Setters, controller input/activation and output activators. Mod-specific or additional expression-bearing string fields require explicit discovery; lexical references and possible cycles do not prove execution order or physical feedback instability.",
                ["migration"]="Explicit reviewed token-aware changes only; no substring rename or automatic scope expansion."};
        }
        private static string NativeElementPath(XElement element,XElement root)
        {
            var parts=new List<string>();while(element!=root){parts.Add(element.Name.LocalName+"["+element.ElementsBeforeSelf(element.Name).Count()+"]");element=element.Parent;}
            parts.Reverse();return string.Join("/",parts);
        }
    }
}
