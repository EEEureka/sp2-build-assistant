using System;
using System.Collections.Generic;
using System.Linq.Expressions;
using System.Reflection;
using System.Text;

namespace SP2BuildAssistant
{
    // Templates contain code and metadata only. Each returned delegate owns its
    // own constants (including part/context/stateful-function instances).
    // Never key on Expression.ToString(), which loses overload and scope data.
    internal static class ExpressionTemplates
    {
        private const int Limit=256;
        private sealed class Entry { internal Delegate Code; internal LinkedListNode<string> Node; }
        private static readonly object Gate=new object();
        private static readonly Dictionary<string,Entry> Cache=new Dictionary<string,Entry>();
        private static readonly LinkedList<string> Lru=new LinkedList<string>();
        private static long hits,compiles,fallbacks,evictions;
        internal static object Describe(){lock(Gate)return new {count=Cache.Count,limit=Limit,hits,compiles,fallbacks,evictions,
            meaning="Bounded compiled templates; per-call constants are never retained by the cache."};}
        internal static Func<T> Compile<T>(Expression<Func<T>> input)
        {
            var shape=new Shape();Expression body;
            try { body=shape.Visit(input.Body); }
            catch(NotSupportedException){lock(Gate)fallbacks++;return input.Compile();}
            string key=shape.Key.ToString();Func<object[],T> code;
            lock(Gate){
                if(Cache.TryGetValue(key,out var entry)){
                    hits++;Lru.Remove(entry.Node);Lru.AddLast(entry.Node);code=(Func<object[],T>)entry.Code;
                }else{
                    code=Expression.Lambda<Func<object[],T>>(body,shape.Bindings).Compile();compiles++;
                    if(Cache.Count==Limit){string oldest=Lru.First.Value;Cache.Remove(oldest);Lru.RemoveFirst();evictions++;}
                    Cache.Add(key,new Entry{Code=code,Node=Lru.AddLast(key)});
                }
            }
            object[] values=shape.Values.ToArray();
            return ()=>code(values);
        }
        private sealed class Shape:ExpressionVisitor
        {
            internal readonly StringBuilder Key=new StringBuilder();
            internal readonly List<object> Values=new List<object>();
            internal readonly ParameterExpression Bindings=Expression.Parameter(typeof(object[]),"bindings");
            private readonly Dictionary<ParameterExpression,int> parameters=new Dictionary<ParameterExpression,int>();
            private void Atom(string text){Key.Append(text.Length).Append(':').Append(text).Append(';');}
            private void Type(Type type){Atom(type.AssemblyQualifiedName);}
            private void Member(MemberInfo member){
                if(member==null){Atom("null-member");return;}
                try { Atom(member.Module.ModuleVersionId.ToString());Atom(member.MetadataToken.ToString());Type(member.DeclaringType); }
                catch(InvalidOperationException){throw new NotSupportedException("Dynamic metadata requires native compilation.");}
                if(member is MethodInfo method && method.IsGenericMethod)
                    foreach(var arg in method.GetGenericArguments())Type(arg);
            }
            public override Expression Visit(Expression node){
                if(node==null){Atom("null-node");return null;}
                // A strict grammar makes unknown extension/dynamic nodes fall
                // back to the game's compiler instead of risking key collisions.
                if(!(node is ConstantExpression || node is ParameterExpression || node is BinaryExpression ||
                    node is UnaryExpression || node is BlockExpression || node is ConditionalExpression ||
                    node is MethodCallExpression || node is MemberExpression || node is InvocationExpression ||
                    node is DefaultExpression || node is IndexExpression || node is TypeBinaryExpression))
                    throw new NotSupportedException("Uncached expression node: "+node.NodeType);
                Atom(node.NodeType.ToString());Type(node.Type);Atom("begin");
                var result=base.Visit(node);Atom("end");return result;
            }
            protected override Expression VisitConstant(ConstantExpression node){
                int slot=Values.Count;Values.Add(node.Value);
                return Expression.Convert(Expression.ArrayIndex(Bindings,Expression.Constant(slot)),node.Type);
            }
            protected override Expression VisitParameter(ParameterExpression node){
                if(!parameters.TryGetValue(node,out int id)){id=parameters.Count;parameters.Add(node,id);}
                Atom(id.ToString());return node;
            }
            protected override Expression VisitBinary(BinaryExpression node){
                Member(node.Method);Atom(node.IsLifted.ToString());Atom(node.IsLiftedToNull.ToString());
                if(node.Conversion!=null)throw new NotSupportedException("Conversion lambda requires native compilation.");
                return base.VisitBinary(node);
            }
            protected override Expression VisitUnary(UnaryExpression node){
                if(node.NodeType==ExpressionType.Quote)throw new NotSupportedException("Quoted code requires native compilation.");
                Member(node.Method);Atom(node.IsLifted.ToString());Atom(node.IsLiftedToNull.ToString());return base.VisitUnary(node);
            }
            protected override Expression VisitBlock(BlockExpression node){
                // Declare scopes before uses; IDs encode parameter identity,
                // including distinct variables with identical names/types.
                Atom(node.Variables.Count.ToString());foreach(var variable in node.Variables)Visit(variable);
                Atom(node.Expressions.Count.ToString());return base.VisitBlock(node);
            }
            protected override Expression VisitMethodCall(MethodCallExpression node){Member(node.Method);Atom(node.Arguments.Count.ToString());return base.VisitMethodCall(node);}
            protected override Expression VisitMember(MemberExpression node){Member(node.Member);return base.VisitMember(node);}
            protected override Expression VisitIndex(IndexExpression node){Member(node.Indexer);Atom(node.Arguments.Count.ToString());return base.VisitIndex(node);}
            protected override Expression VisitTypeBinary(TypeBinaryExpression node){Type(node.TypeOperand);return base.VisitTypeBinary(node);}
        }
    }
}
