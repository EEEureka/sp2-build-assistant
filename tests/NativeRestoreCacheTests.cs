using System;
using System.Xml.Linq;
using SP2BuildAssistant;

class NativeRestoreCacheTests
{
    static int count;
    static void Check(string name,bool value){if(!value)throw new Exception(name);count++;Console.WriteLine("PASS "+name);}
    static XElement Craft(string mass,string extra="")
    {
        return XElement.Parse("<Aircraft><Assembly><Parts><Part id='6' partType='JFuselage-1' position='0,5,1.65' rotation='0,0,0'><JFuselage.State mass='"+mass+"' offset='0,0,1.2' "+extra+"><SectionA size='1.2,1'/><SectionB size='.24,.3'/></JFuselage.State></Part></Parts><Connections/></Assembly></Aircraft>");
    }
    static void Main()
    {
        var expected=Craft("-1.42143E-08,-5.957177E-09,-0.3028488,0.110626");
        var actual=Craft("-1.420337E-08,-5.903507E-09,-0.3028488,0.110626");
        string original=actual.ToString();var plan=NativeRestoreCachePlan.Create(expected,actual);
        Check("Live E1 drift permits exact cache retention",plan!=null && plan.Count==1 && plan[0].PartId==6);
        Check("Validation is not loosened by plan discovery",!SnapshotState.EquivalentAfterNativeRestore(expected,actual));
        Check("Discovery leaves input untouched",actual.ToString()==original);
        Check("Exact live cache serialization restores equality",SnapshotState.EquivalentAfterNativeRestore(expected,Craft(plan[0].Expected)));
        Check("Already matching state needs no retention",NativeRestoreCachePlan.Create(expected,expected)==null);
        Check("Actual shape differences cannot be masked",NativeRestoreCachePlan.Create(expected,XElement.Parse(actual.ToString().Replace(".24,.3",".25,.3")))==null);
        Check("Actual pose differences cannot be masked",NativeRestoreCachePlan.Create(expected,XElement.Parse(actual.ToString().Replace("0,5,1.65","0,5,1.650001")))==null);
        Check("Unexpected state attributes cannot be masked",NativeRestoreCachePlan.Create(expected,Craft("0,0,-0.3028488,0.110626","fuel='1'"))==null);
        Check("Large center drift rejected",NativeRestoreCachePlan.Create(expected,Craft("0.0001,0,-0.3028488,0.110626"))==null);
        Check("Large mass drift rejected",NativeRestoreCachePlan.Create(expected,Craft("0,0,-0.3028488,0.1107"))==null);
        Check("NaN rejected",NativeRestoreCachePlan.Create(expected,Craft("NaN,0,-0.3028488,0.110626"))==null);
        Check("Infinite mass rejected",NativeRestoreCachePlan.Create(expected,Craft("0,0,-0.3028488,Infinity"))==null);
        var thirdExpected=Craft("-8.772826E-09,5.29334E-09,-0.3028488,0.1106259");
        var thirdActual=Craft("-5.70805E-09,1.748306E-09,-0.3028488,0.110626");
        Check("Third live E1 mass rounding retains checkpoint",NativeRestoreCachePlan.Create(thirdExpected,thirdActual)!=null);
        Check("Wrong part ID rejected",NativeRestoreCachePlan.Create(expected,XElement.Parse(actual.ToString().Replace("id=\"6\"","id=\"7\"")))==null);
        Console.WriteLine("Checks passed: "+count);
    }
}
