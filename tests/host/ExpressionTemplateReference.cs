using System;
using System.Reflection;
using System.Runtime.CompilerServices;
using HarmonyLib;
using Jundroo.Common.Expressions;
using Newtonsoft.Json.Linq;

namespace SP2Acceptance
{
    internal static class ExpressionTemplateReference
    {
        public sealed class State {
            public float value;public int calls;
            [Exposed] public float Value { get { return value; } }
            [Exposed] public float Next(){calls++;return ++value;}
        }
        [MethodImpl(MethodImplOptions.NoInlining)] private static Func<float> FloatOriginal(string input,Context context){throw new Exception("reverse patch required");}
        [MethodImpl(MethodImplOptions.NoInlining)] private static Func<bool> BoolOriginal(string input,Context context){throw new Exception("reverse patch required");}
        [MethodImpl(MethodImplOptions.NoInlining)] private static Func<string> StringOriginal(string input,Context context){throw new Exception("reverse patch required");}
        private static Context C(State state){return new Context(true,state);}
        internal static JObject Run(Harmony harmony){
            foreach(var pair in new[]{Tuple.Create(typeof(float),"FloatOriginal"),Tuple.Create(typeof(bool),"BoolOriginal"),Tuple.Create(typeof(string),"StringOriginal")})
                harmony.CreateReversePatcher(typeof(Parser).GetMethod("Process").MakeGenericMethod(pair.Item1),
                    new HarmonyMethod(typeof(ExpressionTemplateReference).GetMethod(pair.Item2,BindingFlags.Static|BindingFlags.NonPublic))).Patch();
            var checks=new JArray();
            foreach(string input in new[]{"0","1.25","-7.5","1/0","0/0","sqrt(-1)","clamp(Value,-1,1)","sin(Value)+cos(Value)",
                "Value*2+3","Value>0?Next():0","Value<0?0:Next()","Next()+Next()","abs(Value)","min(Value,4)","max(Value,4)"}){
                var a=new State{value=2};var b=new State{value=2};var expected=FloatOriginal(input,C(a));var actual=Parser.Process<float>(input,C(b));
                for(int i=0;i<3;i++){
                    a.value+=.3f;b.value+=.3f;float x=expected(),y=actual();bool pass=x.Equals(y)&&a.calls==b.calls;
                    checks.Add(new JObject{["expression"]=input,["iteration"]=i,["type"]="float",["expected"]=x,["actual"]=y,["passed"]=pass});
                    if(!pass)throw new Exception("Float native mismatch: "+input);
                }
            }
            foreach(string input in new[]{"true","false","Value>1","Value<0&Next()>0","Value>0|Next()<0","!(Value>3)"}){
                var a=new State{value=2};var b=new State{value=2};bool x=BoolOriginal(input,C(a))(),y=Parser.Process<bool>(input,C(b))();
                bool pass=x==y&&a.calls==b.calls;checks.Add(new JObject{["expression"]=input,["type"]="bool",["passed"]=pass});if(!pass)throw new Exception("Bool native mismatch");
            }
            foreach(string input in new[]{"\"hello\"","\"中文\"","Value>0?\"a\":\"b\""}){
                string x=StringOriginal(input,C(new State{value=2}))(),y=Parser.Process<string>(input,C(new State{value=2}))();
                bool pass=x==y;checks.Add(new JObject{["expression"]=input,["type"]="string",["passed"]=pass});if(!pass)throw new Exception("String native mismatch");
            }
            // Independently bound returned delegates must stay attached to the
            // correct mutable state even when they share one compiled template.
            var left=new State{value=10};var right=new State{value=100};var fl=Parser.Process<float>("Next()",C(left));var fr=Parser.Process<float>("Next()",C(right));
            bool isolated=fl()==11&&fr()==101&&fl()==12&&right.calls==1;
            checks.Add(new JObject{["case"]="independent live stateful bindings",["passed"]=isolated});if(!isolated)throw new Exception("Cross-context reuse");
            return new JObject{["passed"]=true,["checks"]=checks,["evidence"]="Original parser reverse patch vs patched parser in installed Unity Mono; separate mutable contexts, repeated evaluation, float/bool/string, laziness and stateful bindings. No flight telemetry or GC forced."};
        }
    }
}
