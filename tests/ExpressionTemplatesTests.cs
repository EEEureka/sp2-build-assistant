using System;
using System.Linq.Expressions;
using System.Runtime.CompilerServices;
using SP2BuildAssistant;

public class ExpressionTemplatesTests
{
    private static int checks;
    public sealed class State { public float Value; public int Calls; public float Next(){Calls++;return ++Value;} }
    private static void Check(bool value,string name){checks++;if(!value)throw new Exception(name);}
    private static T Run<T>(Expression body){return ExpressionTemplates.Compile(Expression.Lambda<Func<T>>(body))();}
    private static void Same<T>(Expression body,string name){var e=Expression.Lambda<Func<T>>(body);Check(object.Equals(e.Compile()(),ExpressionTemplates.Compile(e)()),name);}
    private static Expression Read(State state){return Expression.Field(Expression.Constant(state),"Value");}
    private static Func<float> Next(State state){return ExpressionTemplates.Compile(Expression.Lambda<Func<float>>(Expression.Call(Expression.Constant(state),typeof(State).GetMethod("Next"))));}
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference ReleasedBinding(){var state=new State{Value=17};var weak=new WeakReference(state);Check(Next(state)()==18,"temporary binding executed");return weak;}
    public static void Main(){
        var a=new State{Value=2};var b=new State{Value=11};var fa=Next(a);var fb=Next(b);
        Check(fa()==3 && fb()==12 && fa()==4 && b.Calls==1,"stateful bindings isolated");
        b.Value=80;Check(fb()==81,"reads live context, not captured value snapshot");
        var addA=Expression.Add(Read(a),Expression.Constant(5f));var addB=Expression.Add(Read(b),Expression.Constant(7f));
        Check(Run<float>(addA)==9 && Run<float>(addB)==88,"same template different literals and instances");
        foreach(float value in new[]{0f,-0f,1.5f,float.NaN,float.PositiveInfinity,float.NegativeInfinity})Same<float>(Expression.Constant(value),"float constant");
        foreach(string value in new[]{null,"","中文","a:b;end"})Same<string>(Expression.Constant(value,typeof(string)),"string constant");
        var p=Expression.Variable(typeof(float),"same");var q=Expression.Variable(typeof(float),"same");
        Same<float>(Expression.Block(new[]{p,q},Expression.Assign(p,Expression.Constant(1f)),Expression.Assign(q,Expression.Constant(3f)),Expression.Subtract(p,q)),"distinct same-name scopes");
        Same<float>(Expression.Block(new[]{p,q},Expression.Assign(p,Expression.Constant(1f)),Expression.Assign(q,Expression.Constant(3f)),Expression.Subtract(q,p)),"parameter identity in cache key");
        var dangerous=Expression.Call(Expression.Constant(a),typeof(State).GetMethod("Next"));int calls=a.Calls;
        Check(!Run<bool>(Expression.AndAlso(Expression.Constant(false),Expression.GreaterThan(dangerous,Expression.Constant(0f)))) && a.Calls==calls,"short circuit preserved");
        Check(Run<float>(Expression.Condition(Expression.Constant(true),Expression.Constant(7f),dangerous))==7 && a.Calls==calls,"branch laziness preserved");
        Same<int>(Expression.Call(typeof(Math).GetMethod("Abs",new[]{typeof(int)}),Expression.Constant(-3)),"int overload");
        Same<double>(Expression.Call(typeof(Math).GetMethod("Abs",new[]{typeof(double)}),Expression.Constant(-4.5)),"double overload");
        Same<int?>(Expression.Add(Expression.Constant(null,typeof(int?)),Expression.Constant((int?)4,typeof(int?))),"lifted nullable");
        Same<bool>(Expression.TypeIs(Expression.Constant(a,typeof(object)),typeof(State)),"type test");
        Same<bool>(Expression.TypeIs(Expression.Constant(a,typeof(object)),typeof(string)),"different type test key");
        Same<float>(Expression.Invoke(Expression.Constant(new Func<float>(()=>2.5f))),"delegate invocation");
        Same<int>(Expression.ArrayIndex(Expression.Constant(new[]{4,6}),Expression.Constant(1)),"array index");
        Same<DateTime>(Expression.New(typeof(DateTime).GetConstructor(new[]{typeof(long)}),Expression.Constant(1L)),"unsupported constructor falls back");
        try{Run<int>(Expression.Divide(Expression.Constant(1),Expression.Constant(0)));throw new Exception("missing exception");}catch(DivideByZeroException){checks++;}
        var weak=ReleasedBinding();GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();Check(!weak.IsAlive,"cache must not root discarded context");
        for(int depth=1;depth<=260;depth++){Expression body=Expression.Constant(1);for(int i=0;i<depth;i++)body=Expression.Add(body,Expression.Constant(1));Check(Run<int>(body)==depth+1,"eviction semantics");}
        object report=ExpressionTemplates.Describe();int count=(int)report.GetType().GetProperty("count").GetValue(report,null);
        long evictions=(long)report.GetType().GetProperty("evictions").GetValue(report,null);Check(count==256 && evictions>0,"bounded cache evicts");
        Check(fa()==5 && fb()==82,"existing delegates remain valid after eviction");
        Console.WriteLine("Expression templates: "+checks+" checks passed.");
    }
}
