using System;
using System.Collections.Generic;
using System.Linq.Expressions;
using System.Reflection;
using System.Reflection.Emit;
using BepInEx.Logging;
using HarmonyLib;
using Jundroo.Common.Expressions;

namespace SP2BuildAssistant
{
    internal static class DesignerExpressionLifetime
    {
        private const string AuditedModule="c56a8895-a9df-4a02-a34b-b00231672b56";
        private static bool installed;
        private static int mainThread;
        internal static void Install(Harmony harmony,ManualLogSource log){
            if(typeof(Parser).Assembly.ManifestModule.ModuleVersionId.ToString()!=AuditedModule){
                log.LogWarning("Designer expression template reuse disabled for unaudited expression module.");return;
            }
            mainThread=System.Threading.Thread.CurrentThread.ManagedThreadId;
            var method=typeof(Parser).GetMethod("Process");
            foreach(var type in new[]{typeof(float),typeof(bool),typeof(string)})
                harmony.Patch(method.MakeGenericMethod(type),transpiler:new HarmonyMethod(typeof(DesignerExpressionLifetime).GetMethod("Rewrite",BindingFlags.Static|BindingFlags.NonPublic)));
            installed=true;
        }
        private static IEnumerable<CodeInstruction> Rewrite(IEnumerable<CodeInstruction> instructions){
            int replaced=0;
            foreach(var instruction in instructions){
                if(instruction.operand is MethodInfo call && call.Name=="Compile" && call.GetParameters().Length==0 &&
                    call.DeclaringType.IsGenericType && call.DeclaringType.GetGenericTypeDefinition()==typeof(Expression<>)){
                    var resultType=call.ReturnType.GetGenericArguments()[0];
                    instruction.opcode=OpCodes.Call;
                    instruction.operand=typeof(DesignerExpressionLifetime).GetMethod("Compile",BindingFlags.Static|BindingFlags.NonPublic).MakeGenericMethod(resultType);
                    replaced++;
                }
                yield return instruction;
            }
            if(replaced!=1)throw new InvalidOperationException("Audited parser compile call changed.");
        }
        private static Func<T> Compile<T>(Expression<Func<T>> expression){
            return System.Threading.Thread.CurrentThread.ManagedThreadId==mainThread && UnityEngine.SceneManagement.SceneManager.GetActiveScene().name=="Designer"
                ?ExpressionTemplates.Compile(expression):expression.Compile();
        }
        internal static object Describe(){return new {installed,auditedExpressionModule=AuditedModule,
            scope="Designer only; original parsed expression tree and compiler, separately bound constants",templates=ExpressionTemplates.Describe()};}
    }
}
