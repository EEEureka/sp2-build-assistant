using System;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;

namespace SP2BuildAssistant { internal class ApiError : Exception { public string Code; public ApiError(string code,string message):base(message){Code=code;} } }
class ShapeCodecTests
{
    static int count;
    static void Check(string label,bool pass) { if(!pass)throw new Exception(label);count++;Console.WriteLine("PASS "+label); }
    static XElement Body() {return XElement.Parse("<Part partType='JFuselage-1'><JFuselage.State version='4' offset='1,2,3' hollow='true'><Slice size='1,2' cornerRadii='0.1,0.2,0.3,0.4' cutting=',,,'/><Slice size='2,3'/></JFuselage.State><FuelTank.State fuel='12'/></Part>");}
    static XElement Wing() {return XElement.Parse("<Part partType='JWing-1'><JWing.State version='3'><Slice position='0' airfoil='NACA2412' scale='2' offset='0'/><Slice position='3' airfoil='NACA0012' scale='1' offset='0'/></JWing.State></Part>");}
    static void Patch(XElement p,string json){ShapeCodec.Patch(p,JObject.Parse(json),s=>s.StartsWith("NACA") && s.Length==8);}
    static void Reject(string label,XElement p,string json){bool bad=false;try{Patch(p,json);}catch(ApiError){bad=true;}Check(label,bad);}
    static void Main(string[] args)
    {
        var b=Body();Patch(b,"{length:6,sections:[{index:0,width:4,cutting:{top:0.64},cornerRadius:{topLeft:0.2}}]}");
        var s=ShapeCodec.State(b);var section=s.Element("Slice");
        Check("Length preserves lateral offset",(string)s.Attribute("offset")=="1,2,6");
        Check("Width preserves height",(string)section.Attribute("size")=="4,2");
        Check("Cutting uses top right bottom left with automatic nulls",(string)section.Attribute("cutting")=="0.64,,,");
        Check("Preserves unrelated modifier",(string)b.Element("FuelTank.State").Attribute("fuel")=="12");
        Check("Named corner maps to native top left index 0",(string)section.Attribute("cornerRadii")=="0.2,0.2,0.3,0.4");
        var original=new XElement(s);ShapeCodec.Mirror(s);Check("Mirror reverses lateral offset",(string)s.Attribute("offset")=="-1,2,6");ShapeCodec.Mirror(s);Check("Double mirror preserves all state",XNode.DeepEquals(original,s));
        Patch(b,"{sections:[{index:0,cutting:{top:null,right:0.25},cornerStretch:{bottomRight:true}}]}");
        ShapeCodec.Mirror(s);Check("Mirror swaps right and left cuts",(string)s.Element("Slice").Attribute("cutting")==",,,0.25");
        Check("Mirror swaps bottom corner flags",(string)s.Element("Slice").Attribute("cornerStretch")=="false,false,false,true");
        Reject("Reject entire cross-section removal",Body(),"{sections:[{index:0,cutting:{top:0.6,bottom:0.4}}]}");
        Reject("Reject string instead of number",Body(),"{length:'6'}");
        Reject("Reject infinite dimensions",Body(),"{length:Infinity}");
        Reject("Reject unknown nested field",Body(),"{sections:[{index:0,cutting:{north:0.3}}]}");
        Reject("Reject ambiguous offset and length",Body(),"{length:4,offset:[0,0,4]}");
        Reject("Reject duplicate patch index",Body(),"{sections:[{index:0,width:1},{index:0,width:2}]}");
        Reject("Reject fractional mesh sample count",Body(),"{sections:[{index:0,cornerSamples:{topLeft:3.5}}]}");
        var legacy=Body();ShapeCodec.State(legacy).SetAttributeValue("legacyThickness",true);Reject("Legacy thickness cannot be mislabeled as fraction",legacy,"{sections:[{index:0,thicknessFraction:0.2}]}");
        var curved=Body();curved.SetAttributeValue("partType","JFuselage-2");ShapeCodec.State(curved).Add(new XElement("Slice",new XAttribute("size","1,1")));Reject("Curved middle slice has no cutting",curved,"{sections:[{index:1,cutting:{top:0.2}}]}");
        var capabilities=(JArray)ShapeCodec.Read(curved)["sectionCapabilities"];
        Check("Curve readout explains unsupported middle options",(string)capabilities[1]["role"]=="curve_control"&&!(bool)capabilities[1]["cutting"]&&!(bool)capabilities[1]["syncAdjacent"]&&(bool)capabilities[0]["cutting"]);
        Check("Legacy thickness readout is not advertised writable",!(bool)ShapeCodec.Read(legacy)["sectionCapabilities"][0]["thicknessFraction"]);
        var w=Wing();Patch(w,"{sections:[{index:1,chord:0.5,airfoil:'NACA2412'}]}");Check("Wing patch preserves root",(string)ShapeCodec.State(w).Elements("Slice").First().Attribute("scale")=="2");
        Reject("Reject reversed wing stations",Wing(),"{sections:[{index:1,spanPosition:0}]}");
        Reject("Reject unknown airfoil",Wing(),"{sections:[{index:0,airfoil:'UNKNOWN'}]}");
        Reject("Reject deleting root definition",Wing(),"{sections:[{index:0,airfoil:null}]}");
        Patch(w,"{replaceSections:[{spanPosition:0,chord:2,offset:0,airfoil:'NACA2412'},{spanPosition:1,chord:null,offset:null,airfoil:null},{spanPosition:3,chord:1,offset:0,airfoil:'NACA0012'}]}");
        Check("Explicit interior interpolation is retained",ShapeCodec.State(w).Elements("Slice").ElementAt(1).Attribute("scale")==null);
        var flap=XElement.Parse("<Part><ControlSurfacePart.State style='Slat' range='0,1' startPos='0.2,0.2'/></Part>");Reject("Slat chord fraction obeys native maximum",flap,"{chordFraction:[0.5,0.5]}");
        var wingXml=Wing();string before=wingXml.ToString();Reject("JFuselage fields cannot edit wing slices",wingXml,"{sections:[{index:0,width:2}]}");Check("Rejected field did not touch wing XML",wingXml.ToString()==before);
        foreach(var family in new[]{"fuselage","wing","controlSurface"})Check("Schema "+family,ShapeCodec.Schema(family).Count>3);
        if(args.Length>0) {
            int mapped=0;foreach(var p in XElement.Load(args[0]).Descendants("Part")) if(ShapeCodec.Family(p)!=null){ShapeCodec.Read(p);mapped++;}
            Check("Read real aircraft geometry "+mapped,mapped>0);
        }
        Console.WriteLine("Passed "+count+" checks.");
    }
}
