using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // No Unity dependencies: the same codec is exercised by the offline regression tests.
    internal static class ShapeCodec
    {
        internal static readonly string[] Corners = { "topLeft", "topRight", "bottomRight", "bottomLeft" };
        internal static readonly string[] Edges = { "top", "right", "bottom", "left" };
        private static readonly CultureInfo C = CultureInfo.InvariantCulture;
        internal sealed class Field
        {
            public string Attribute, Type, Unit; public double Min, Max; public object Default; public bool Nullable;
            public Field(string attr, string type, double min = 0, double max = 1, object def = null, string unit = null, bool nullable = false)
            { Attribute = attr; Type = type; Min = min; Max = max; Default = def; Unit = unit; Nullable = nullable; }
        }
        private static Field N(string a, double min, double max, double def, string unit = null) { return new Field(a, "number", min, max, def, unit); }
        private static Field B(string a, bool def = false) { return new Field(a, "boolean", def: def); }
        private static Field I(string a, int min, int max, int def, bool nullable = false) { return new Field(a, "integer", min, max, def, nullable: nullable); }
        internal static readonly Dictionary<string, Field> Fuselage = new Dictionary<string, Field> {
            ["hollow"] = B("hollow"), ["glass"] = B("glass"), ["fuelFraction"] = N("fuelProportion",0,1,0),
            ["deadMassKg"] = N("deadMassKg",0,500,0,"kg"), ["buoyancy"] = N("buoyancy",0,1,0),
            ["noseconeRoundness"] = N("noseconeRoundness",0,1,.5), ["autoResize"] = B("autoResize"),
            ["colliderCount"] = I("numColliders",3,16,8), ["colliderCornerSamples"] = I("colliderCornerSamples",1,32,5)
        };
        internal static readonly Dictionary<string, Field> FuselageSection = new Dictionary<string, Field> {
            ["smoothing"] = B("smoothing",true), ["syncAdjacent"] = B("syncSlices",true),
            ["thicknessFraction"] = N("thickness",.01,1,.1), ["trapezium"] = N("trapezium",-1,1,0)
        };
        internal static readonly Dictionary<string, Field> Wing = new Dictionary<string, Field> {
            ["flipped"] = B("flipped"), ["fuelFraction"] = N("fuelFraction",0,1,0), ["disableWingtipVortices"] = B("disableWingtipVortices"),
            ["liftScale"] = N("liftScale",0,100,1), ["zeroLiftDragScale"] = N("zeroLiftDragScale",0,100,1), ["viscousDragScale"] = N("viscousDragScale",0,100,1),
            ["physicsSamples"] = I("physicsSamples",2,256,20,true), ["chordSamples"] = I("chordSamples",3,64,10), ["colliderSamples"] = I("colliderSamples",3,32,5)
        };
        internal static readonly Dictionary<string, Field> WingSection = new Dictionary<string, Field> {
            ["spanPosition"] = N("position",0,1000,0,"m"), ["chord"] = new Field("scale","number",.001,1000,null,"m",true),
            ["offset"] = new Field("offset","number",-1000,1000,null,"m",true),
            ["airfoil"] = new Field("airfoil","string",def:null,nullable:true), ["smoothJoin"] = B("smoothJoin",true),
            ["bendDegrees"] = N("bend",-170,170,0,"degrees"), ["bendRadiusMultiplier"] = N("bendRadiusMultiplier",.01,100,1),
            ["chordSamples"] = I("chordSamples",3,64,10,true), ["colliderSamples"] = I("colliderSamples",3,32,5,true)
        };
        internal static Dictionary<string, Field> Control(string style)
        {
            var f = new Dictionary<string, Field>();
            if (style == "StandardFlap" || style == "FowlerFlap") f["maxDeflectionDegrees"] = N("maxDeflection",0,90,style=="FowlerFlap"?40:30,"degrees");
            if (style == "Slat") f["maxDeflectionDegrees"] = N("deflectionDegrees",0,90,30,"degrees");
            if (style == "BrakeFlap") {
                f["flapDeflectionDegrees"] = N("flapDeflection",0,90,30,"degrees");
                f["brakeTopDegrees"] = N("brakeDeflectionTop",0,90,80,"degrees"); f["brakeBottomDegrees"] = N("brakeDeflectionBottom",0,90,80,"degrees");
                f["brakeDeflectionSpeed"] = N("brakeDeflectionSpeed",.001,100,.8);
            }
            return f;
        }
        internal static string Family(XElement part)
        {
            if (part.Element("JFuselage.State") != null) return "fuselage";
            if (part.Element("JWing.State") != null) return "wing";
            if (part.Element("ControlSurfacePart.State") != null) return "controlSurface";
            return null;
        }
        internal static XElement State(XElement part)
        { return part.Element("JFuselage.State") ?? part.Element("JWing.State") ?? part.Element("ControlSurfacePart.State"); }
        internal static void Keys(JObject value, IEnumerable<string> allowed)
        {
            if (value == null) throw new ApiError("invalid_shape", "Expected an object.");
            string[] unknown = value.Properties().Select(p=>p.Name).Except(allowed).ToArray();
            if (unknown.Length > 0) throw new ApiError("invalid_shape", "Unknown fields: " + string.Join(", ", unknown));
        }
        internal static double Number(JToken value, double min, double max, string field, bool integer = false)
        {
            if (value == null || (value.Type != JTokenType.Float && value.Type != JTokenType.Integer)) throw new ApiError("invalid_shape", field + " must be a JSON number.");
            double n = (double)value;
            if (double.IsNaN(n) || double.IsInfinity(n) || n < min || n > max || (integer && n != Math.Truncate(n))) throw new ApiError("invalid_shape", field + " must be " + (integer ? "an integer " : "") + "in ["+min+","+max+"].");
            return n;
        }
        private static object Validate(JToken token, Field f, string name)
        {
            if (token.Type == JTokenType.Null && f.Nullable) return null;
            if (f.Type == "boolean") { if (token.Type != JTokenType.Boolean) throw new ApiError("invalid_shape",name+" must be a boolean."); return (bool)token; }
            if (f.Type == "string") { if (token.Type != JTokenType.String || string.IsNullOrWhiteSpace((string)token)) throw new ApiError("invalid_shape",name+" must be a nonempty string."); return (string)token; }
            return Number(token, f.Min, f.Max, name, f.Type == "integer");
        }
        private static void WriteFields(XElement state, JObject patch, Dictionary<string, Field> fields)
        { foreach (var pair in fields) if (patch[pair.Key] != null) Set(state,pair.Value.Attribute,Validate(patch[pair.Key],pair.Value,pair.Key)); }
        private static JObject ReadFields(XElement state, Dictionary<string, Field> fields)
        {
            var result = new JObject();
            foreach (var pair in fields) {
                string v = (string)state.Attribute(pair.Value.Attribute); var f = pair.Value;
                if (v == null) result[pair.Key] = f.Nullable || f.Default == null ? JValue.CreateNull() : JToken.FromObject(f.Default);
                else if (f.Type == "boolean") result[pair.Key] = bool.Parse(v);
                else if (f.Type == "string") result[pair.Key] = v;
                else result[pair.Key] = double.Parse(v,C);
            }
            return result;
        }
        internal static void Set(XElement e, string name, object value)
        { e.SetAttributeValue(name,value is double ? ((double)value).ToString("R",C) : value); }
        internal static double[] Vector(XElement e, string name, string defaults)
        { return ((string)e.Attribute(name) ?? defaults).Split(',').Select(n=>double.Parse(n,C)).ToArray(); }
        internal static void SetVector(XElement e,string attr,IEnumerable<double> v)
        { e.SetAttributeValue(attr,string.Join(",",v.Select(n=>n.ToString("R",C)))); }
        private static void NamedVector(XElement section, JObject patch, string field, string attr, string[] names, double min, double max, string defaults, bool integer = false, bool boolean = false, bool nullable = false)
        {
            if (patch[field] == null) return;
            var obj = patch[field] as JObject; Keys(obj,names);
            var values = ((string)section.Attribute(attr) ?? defaults).Split(',');
            if (values.Length != names.Length) throw new ApiError("invalid_shape", "Unsupported native vector format: " + attr);
            for (int i=0;i<names.Length;i++) if (obj[names[i]] != null) {
                var token=obj[names[i]];
                if (nullable && token.Type==JTokenType.Null) values[i]="";
                else if (boolean) { if (token.Type!=JTokenType.Boolean) throw new ApiError("invalid_shape",field+" requires booleans."); values[i]=((bool)token)?"true":"false"; }
                else values[i]=Number(token,min,max,field+"."+names[i],integer).ToString("R",C);
            }
            section.SetAttributeValue(attr,string.Join(",",values));
        }
        private static JObject ReadNamed(XElement s,string attr,string[] names,string defaults,bool boolean=false)
        {
            string[] values=((string)s.Attribute(attr) ?? defaults).Split(','); var result=new JObject();
            for(int i=0;i<names.Length;i++) result[names[i]] = string.IsNullOrWhiteSpace(values[i]) ? JValue.CreateNull() : boolean ? new JValue(bool.Parse(values[i])) : new JValue(double.Parse(values[i],C));
            return result;
        }
        internal static JObject Read(XElement part)
        {
            string family=Family(part); XElement state=State(part);
            if (family==null) return new JObject { ["family"]="unmapped", ["typedEditingSupported"]=false, ["hint"]="Use catalog.schema and the complex-parts inventory; do not guess nested XML." };
            var config=ReadFields(state,family=="fuselage"?Fuselage:family=="wing"?Wing:Control((string)state.Attribute("style")));
            var result=new JObject { ["family"]=family, ["typedEditingSupported"]=true, ["configuration"]=config };
            if(family=="fuselage") {
                double[] offset=Vector(state,"offset","0,0,1"); config["offset"]=new JArray(offset); config["length"]=Math.Abs(offset[2]);
                result["lengthMeaning"]="absolute local Z separation; setting length preserves X/Y offset and Z sign";
                result["thicknessMode"]=(bool?)state.Attribute("legacyThickness")==true?"legacy":"fraction";
                int sectionCount=state.Elements("Slice").Count();
                result["sectionCapabilities"]=new JArray(Enumerable.Range(0,sectionCount).Select(i=>{
                    bool middle=i>0&&i<sectionCount-1;
                    bool coneTip=((string)part.Attribute("partType")??"").Contains("Cone")&&i==sectionCount-1;
                    return new JObject{["index"]=i,["role"]=middle?"curve_control":coneTip?"cone_tip":"end",
                        ["cutting"]=!middle,["smoothing"]=!middle&&!coneTip,["syncAdjacent"]=!middle&&!coneTip,
                        ["thicknessFraction"]=(bool?)state.Attribute("legacyThickness")!=true,
                        ["meaning"]=middle?"Native curve control section; dimensions influence the interpolated surface and are not a literal measured cross-section.":"Native end section; dimensions describe the configured section."};
                }));
                config["sections"]=new JArray(state.Elements("Slice").Select((s,i)=> {
                    var x=ReadFields(s,FuselageSection); x["index"]=i; double[] size=Vector(s,"size","1,1");x["width"]=size[0];x["height"]=size[1];
                    x["cornerRadius"]=ReadNamed(s,"cornerRadii",Corners,"1,1,1,1"); x["cornerStretch"]=ReadNamed(s,"cornerStretch",Corners,"false,false,false,false",true);
                    x["cornerSamples"]=ReadNamed(s,"cornerSamples",Corners,"7,7,7,7");x["edgeCurvature"]=ReadNamed(s,"edgeCurvature",Edges,"0,0,0,0");
                    x["edgeSamples"]=ReadNamed(s,"edgeSamples",Edges,"7,7,7,7");x["cutting"]=ReadNamed(s,"cutting",Edges,",,,"); return x;
                }));
            } else if(family=="wing") {
                config["sections"]=new JArray(state.Elements("Slice").Select((s,i)=> {var x=ReadFields(s,WingSection);x["index"]=i;return x;}));
                var tip=state.Element("Wingtip");config["wingtip"]=tip==null?null:new JObject{["stretch"]=(double?)tip.Attribute("stretch")??1};
                result["wingtipStyle"]=tip==null?null:(string)tip.Attribute("style");
            } else {
                result["style"]=(string)state.Attribute("style"); config["spanRange"]=new JArray(Vector(state,"range","0,2"));
                if(state.Attribute("startPos")!=null) config["hingePosition"]=new JArray(Vector(state,"startPos","0,0"));
                result["hingePositionMeaning"]="native chordwise metres at spanRange start/end; prefer chordFraction in writes";
            }
            return result;
        }
        internal static void Patch(XElement part,JObject patch,Func<string,bool> airfoilValid)
        {
            string family=Family(part); var state=State(part);
            if(family==null) throw new ApiError("shape_not_supported","No typed editor for this part; inspect shape.get and knowledge complex.");
            if(family=="fuselage") PatchFuselage(part,state,patch);
            else if(family=="wing") PatchWing(state,patch,airfoilValid);
            else PatchControl(state,patch);
        }
        private static void PatchFuselage(XElement part,XElement state,JObject patch)
        {
            Keys(patch,Fuselage.Keys.Concat(new[]{"offset","length","sections"}));
            if(patch["noseconeRoundness"]!=null && !((string)part.Attribute("partType")??"").Contains("Cone")) throw new ApiError("invalid_shape","noseconeRoundness only applies to a cone.");
            WriteFields(state,patch,Fuselage);
            if(patch["offset"]!=null && patch["length"]!=null) throw new ApiError("invalid_shape","Specify offset OR length.");
            double[] offset=Vector(state,"offset","0,0,1");
            if(patch["offset"]!=null) offset=ArrayNumbers(patch["offset"],3,-1000,1000,"offset");
            if(patch["length"]!=null) offset[2]=Number(patch["length"],.001,1000,"length")*(offset[2]<0?-1:1);
            if(Math.Abs(offset[2])<.001) throw new ApiError("invalid_shape","Fuselage local Z separation must be at least 0.001 m.");
            SetVector(state,"offset",offset);
            var sections=state.Elements("Slice").ToArray();
            if(sections.Length<2) throw new ApiError("shape_version_unsupported","Typed fuselage requires native version 4 Slice state.");
            if(patch["sections"]!=null) {
                var updates=SectionPatches(patch["sections"],sections.Length);
                foreach(var update in updates) {
                    int index=(int)update["index"]; XElement s=sections[index];
                    Keys(update,FuselageSection.Keys.Concat(new[]{"index","width","height","cornerRadius","cornerStretch","cornerSamples","edgeCurvature","edgeSamples","cutting"}));
                    if((bool?)state.Attribute("legacyThickness")==true && update["thicknessFraction"]!=null) throw new ApiError("shape_version_unsupported","Legacy thickness has different units; it cannot be edited as a fraction.");
                    bool middle=index>0 && index<sections.Length-1; bool coneTip=((string)part.Attribute("partType")??"").Contains("Cone") && index==sections.Length-1;
                    if((middle && new[]{"cutting","smoothing","syncAdjacent"}.Any(k=>update[k]!=null)) || (coneTip && new[]{"smoothing","syncAdjacent"}.Any(k=>update[k]!=null))) throw new ApiError("unsupported_section_capability","This native slice does not support the requested cutting/smoothing/sync option.");
                    WriteFields(s,update,FuselageSection);
                    double[] size=Vector(s,"size","1,1");
                    if(update["width"]!=null) size[0]=Number(update["width"],0,1000,"width");
                    if(update["height"]!=null) size[1]=Number(update["height"],0,1000,"height");
                    SetVector(s,"size",size);
                    NamedVector(s,update,"cornerRadius","cornerRadii",Corners,0,1000,"1,1,1,1");
                    NamedVector(s,update,"cornerStretch","cornerStretch",Corners,0,1,"false,false,false,false",boolean:true);
                    var stretch=((string)s.Attribute("cornerStretch")??"false,false,false,false").Split(',').Select(bool.Parse).ToArray();
                    var radii=Vector(s,"cornerRadii","1,1,1,1");
                    for(int corner=0;corner<4;corner++)if(stretch[corner] && radii[corner]>1)throw new ApiError("invalid_shape","Stretched corner radius must be in [0,1].");
                    NamedVector(s,update,"cornerSamples","cornerSamples",Corners,1,32,"7,7,7,7",integer:true);
                    NamedVector(s,update,"edgeCurvature","edgeCurvature",Edges,0,1,"0,0,0,0");
                    NamedVector(s,update,"edgeSamples","edgeSamples",Edges,1,32,"7,7,7,7",integer:true);
                    NamedVector(s,update,"cutting","cutting",Edges,0,1,",,,",nullable:true);
                    var cuts=((string)s.Attribute("cutting")??",,,").Split(',').Select(x=>x==""?0:double.Parse(x,C)).ToArray();
                    if(cuts[0]+cuts[2]>=1 || cuts[1]+cuts[3]>=1) throw new ApiError("invalid_shape","Opposite cuts must sum to less than 1; otherwise the section is entirely removed.");
                }
            }
            if(sections.All(s=>Vector(s,"size","1,1").Any(n=>n<=0))) throw new ApiError("invalid_shape","At least one fuselage section must have positive width and height.");
        }
        private static List<JObject> SectionPatches(JToken token,int count)
        {
            var a=token as JArray;
            if(a==null || a.Count==0 || a.Any(x=>!(x is JObject))) throw new ApiError("invalid_shape","sections must be a nonempty array of indexed objects.");
            var result=a.Cast<JObject>().ToList();
            foreach(var p in result) Number(p["index"],0,count-1,"section index",true);
            if(result.Select(p=>(int)p["index"]).Distinct().Count()!=result.Count) throw new ApiError("invalid_shape","Duplicate section index.");
            return result;
        }
        private static void PatchWing(XElement state,JObject patch,Func<string,bool> airfoilValid)
        {
            Keys(patch,Wing.Keys.Concat(new[]{"sections","replaceSections","wingtip"})); WriteFields(state,patch,Wing);
            if(patch["sections"]!=null && patch["replaceSections"]!=null) throw new ApiError("invalid_shape","Use sections OR replaceSections.");
            if(patch["replaceSections"]!=null) {
                var sections=patch["replaceSections"] as JArray;
                if(sections==null || sections.Count<2 || sections.Count>32) throw new ApiError("invalid_shape","replaceSections requires 2..32 sections.");
                var nodes=new List<XElement>();
                foreach(JToken token in sections) { var x=token as JObject;Keys(x,WingSection.Keys);var s=new XElement("Slice");WriteFields(s,x,WingSection);nodes.Add(s); }
                state.Elements("Slice").Remove();state.Add(nodes);
            }
            var slices=state.Elements("Slice").ToArray();
            if(patch["sections"]!=null) foreach(var x in SectionPatches(patch["sections"],slices.Length)) {Keys(x,WingSection.Keys.Concat(new[]{"index"}));WriteFields(slices[(int)x["index"]],x,WingSection);}
            double previous=-1;
            for(int i=0;i<slices.Length;i++) {
                var s=slices[i]; double position=double.Parse((string)s.Attribute("position")??"NaN",C);
                if(double.IsNaN(position) || (i==0 && position!=0) || position-previous<.001) throw new ApiError("invalid_shape","Wing positions start at zero and strictly increase by at least 0.001 m."); previous=position;
                bool end=i==0 || i==slices.Length-1;
                if((end && (s.Attribute("scale")==null || s.Attribute("offset")==null)) || (i==0 && s.Attribute("airfoil")==null)) throw new ApiError("invalid_shape","Root and tip need chord and offset; root needs an airfoil; other null airfoils use native interpolation/inheritance.");
                string airfoil=(string)s.Attribute("airfoil");
                if(airfoil!=null && !airfoilValid(airfoil)) throw new ApiError("invalid_airfoil","Native parser rejected airfoil: "+airfoil);
            }
            if(patch["wingtip"]!=null) {
                if(patch["wingtip"].Type==JTokenType.Null) state.Element("Wingtip")?.Remove();
                else { var tip=patch["wingtip"] as JObject;Keys(tip,new[]{"stretch"});double stretch=Number(tip["stretch"],0,4,"wingtip.stretch");var e=new XElement("Wingtip",new XAttribute("style","Rounded"),new XAttribute("stretch",stretch.ToString("R",C)));state.Element("Wingtip")?.Remove();state.Add(e); }
            }
        }
        private static void PatchControl(XElement state,JObject patch)
        {
            var fields=Control((string)state.Attribute("style"));Keys(patch,fields.Keys.Concat(new[]{"spanRange","chordFraction"}));WriteFields(state,patch,fields);
            if(patch["spanRange"]!=null) {double[] range=ArrayNumbers(patch["spanRange"],2,0,1000,"spanRange");if(range[1]-range[0]<.001) throw new ApiError("invalid_shape","spanRange end must exceed start.");SetVector(state,"range",range);}
            // chordFraction is mapped through the attached wing by the runtime, not guessed here.
            if(patch["chordFraction"]!=null) ArrayNumbers(patch["chordFraction"],2,.05,(string)state.Attribute("style")=="Slat"?.4:.8,"chordFraction");
        }
        internal static double[] ArrayNumbers(JToken token,int count,double min,double max,string field)
        { var a=token as JArray;if(a==null || a.Count!=count)throw new ApiError("invalid_shape",field+" requires "+count+" numbers.");return a.Select(x=>Number(x,min,max,field)).ToArray(); }
        internal static void Mirror(XElement state)
        {
            if(state.Name=="JFuselage.State") {
                double[] offset=Vector(state,"offset","0,0,1");offset[0]=-offset[0];SetVector(state,"offset",offset);
                foreach(var s in state.Elements("Slice")) {
                    foreach(string attr in new[]{"cornerRadii","cornerStretch","cornerSamples"}) Permute(s,attr,new[]{1,0,3,2});
                    foreach(string attr in new[]{"edgeCurvature","edgeSamples","cutting"}) Permute(s,attr,new[]{0,3,2,1});
                }
            } else if(state.Name=="JWing.State") Set(state,"flipped",!((bool?)state.Attribute("flipped")??false));
            else if(state.Name=="ControlSurfacePart.State") Set(state,"dummyPartFlipped",!((bool?)state.Attribute("dummyPartFlipped")??false));
        }
        private static void Permute(XElement e,string name,int[] order)
        { var a=e.Attribute(name);if(a==null)return;var values=a.Value.Split(',');a.Value=string.Join(",",order.Select(i=>values[i])); }
        internal static JObject Schema(string family)
        {
            if(!new[]{"fuselage","wing","controlSurface"}.Contains(family))throw new ApiError("shape_not_supported","family must be fuselage, wing or controlSurface.");
            var result=new JObject { ["family"]=family,["units"]="metres, degrees, fractions in [0,1]; named directions are local +Y top, +X right",
                ["boundsPolicy"]="Native UI constraints where available; mesh/sample/dimension limits are conservative tool limits, not claims about all game-legal overload values.",
                ["patchSemantics"]="Only supplied fields change; sections use zero-based index; unknown keys rejected; failed native generation rolls back the transaction." };
            Func<Dictionary<string,Field>,JObject> describe=fs=>new JObject(fs.Select(x=>new JProperty(x.Key,new JObject { ["xmlAttribute"]=x.Value.Attribute,["type"]=x.Value.Type,["nullable"]=x.Value.Nullable,["minimum"]=x.Value.Min,["maximum"]=x.Value.Max,["unit"]=x.Value.Unit })));
            result["fields"]=describe(family=="fuselage"?Fuselage:family=="wing"?Wing:Control("StandardFlap"));
            if(family=="fuselage") {
                result["sectionFields"]=describe(FuselageSection);result["additionalFields"]=JArray.FromObject(new[]{"length (0.001..1000)","offset [x,y,z], mutually exclusive with length","sections [{index,width,height,cornerRadius,cornerStretch,cornerSamples,edgeCurvature,edgeSamples,cutting,...}]"});
                result["corners"]=new JArray(Corners);result["edgesAndCutting"]=new JArray(Edges);
                result["sectionRules"]=new JArray("width/height 0..1000 m; at least one nondegenerate section", "cornerRadius 0..1000 m; native geometry clamps radius against adjacent edges", "cornerStretch boolean per corner; corner/edge samples integer 1..32", "edgeCurvature fraction 0..1; cutting fraction 0..1 or null=automatic; opposite cuts sum <1", "curved middle slice has no cutting/smoothing/sync; cone tip has cutting only", "legacyThickness blocks thicknessFraction writes");
            } else if(family=="wing") {result["sectionFields"]=describe(WingSection);result["additionalFields"]=new JArray("sections patches [{index,...}]", "replaceSections complete ordered list, 2..32 entries", "wingtip null or {stretch:0..4}"); result["airfoilExamples"]=new JArray("NACA0012","NACA2412","Symmetric","Semi-Symmetric","Flat Bottom");}
            else {result["styles"]=new JObject(new[]{"StandardFlap","FowlerFlap","Slat","BrakeFlap"}.Select(s=>new JProperty(s,describe(Control(s)))));result["readOnlyStyles"]=new JArray("Spoiler","SplitFlap");result["additionalFields"]=new JArray("spanRange [start,end] metres within attached wing", "chordFraction [root,tip], 0.05..0.8 (Slat 0.05..0.4)");}
            return result;
        }
    }
}
