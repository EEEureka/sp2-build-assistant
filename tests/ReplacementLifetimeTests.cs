using System;
using System.Collections.Generic;
using System.Linq;
using SP2BuildAssistant;

class ReplacementLifetimeTests
{
    sealed class Aircraft { internal bool Active=true, DestroyQueued; }
    sealed class Scene
    {
        internal readonly List<Aircraft> Roots=new List<Aircraft>();
        internal Aircraft Current;
        internal Scene(){Current=new Aircraft();Roots.Add(Current);}
        internal void NativeAssign(Aircraft next)
        {
            // Unity's deferred Destroy leaves the first named child findable
            // for the remainder of the frame. It may not be Current anymore.
            if(Roots.Count>0)Roots[0].DestroyQueued=true;
            Roots.Add(next);Current=next;
        }
        internal void EndFrame(){Roots.RemoveAll(r=>r.DestroyQueued);}
        internal void OldSwap(){Current.Active=false;NativeAssign(new Aircraft());}
        internal void Swap(bool failBefore=false,bool failAfter=false)
        {
            Aircraft old=Current;
            ReplacementLifetime.Adopt(()=>{
                if(failBefore)throw new Exception("before publication");
                NativeAssign(new Aircraft());
                if(failAfter)throw new Exception("after publication");
            },()=>Current==old,()=>old.Active=false,()=>old.Active=true,()=>old.DestroyQueued=true);
        }
    }
    static int checks;
    static void Check(bool result,string message){checks++;if(!result)throw new Exception(message);Console.WriteLine("PASS "+message);}
    static void Main()
    {
        var legacy=new Scene();legacy.OldSwap();legacy.OldSwap();legacy.EndFrame();
        Check(legacy.Roots.Count==2,"Reproduce legacy inactive scene leak after two swaps in one frame");
        legacy.NativeAssign(new Aircraft());legacy.EndFrame();
        Check(legacy.Roots.Count(r=>r.Active)==2,"Reproduce native undo leaving two active aircraft after legacy leak");
        var fixedScene=new Scene();
        for(int frame=0;frame<4;frame++){
            for(int op=0;op<7;op++)fixedScene.Swap();
            fixedScene.EndFrame();
            Check(fixedScene.Roots.Count==1 && fixedScene.Current.Active,"Multi-operation frame owns exactly one live aircraft "+frame);
        }
        fixedScene.NativeAssign(new Aircraft());fixedScene.EndFrame();
        Check(fixedScene.Roots.Count==1,"Native UI undo after bridge swaps has no stale named child to select");
        var prior=fixedScene.Current;
        try{fixedScene.Swap(failBefore:true);}catch(Exception){}
        fixedScene.EndFrame();
        Check(fixedScene.Current==prior && prior.Active && fixedScene.Roots.Count==1,"Failed adoption restores exact outgoing object when still current");
        try{fixedScene.Swap(failAfter:true);}catch(Exception){}
        fixedScene.EndFrame();
        Check(fixedScene.Current!=prior && !fixedScene.Roots.Contains(prior),"Failure after publication never reactivates stale outgoing object");
        fixedScene.Swap();fixedScene.EndFrame();
        Check(fixedScene.Roots.Count==1 && fixedScene.Current.Active,"Recovery replacement leaves one live aircraft");
        Console.WriteLine("Replacement lifetime checks: "+checks);
    }
}
