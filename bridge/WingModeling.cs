using System;
using System.Linq;
using System.Collections.Generic;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Wings;
using Assets.Scripts.Craft.Wings.Airfoils;
using Assets.Scripts.Craft.Wings.Physics;
using Newtonsoft.Json.Linq;
using UnityEngine;
using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private JObject WingStations(JObject args)
        {
            var part=Part(Int(args,"id"));var wing=part.GetModifier<JWingData>();
            if(wing==null)throw new ApiError("shape_not_supported","Native JWing required.");
            var positions=args["positions"] as JArray;
            if(positions==null||positions.Count==0||positions.Count>256)throw new ApiError("invalid_input","positions needs 1..256 native span stations in metres.");
            var slices=wing.WingSlices.Select(s=>s.Clone()).ToList();WingBuilder.InterpolateAllOffsetScale(slices);
            var derived=wing.WingSlices.SelectMany(s=>new[]{s.LastDerivedSliceRoot,s.LastDerivedSliceTip}).Where(s=>s!=null).OrderBy(s=>s.SpanPosition).ToArray();
            var result=new JArray();var t=part.PartScript.transform;
            foreach(var token in positions){
                float pos=(float)PropertyValues.Convert(token,typeof(float),0,wing.WingSpan,"span station metres");
                var values=WingBuilder.GetInterpolatedSlice(pos,slices);
                var left=derived.LastOrDefault(s=>s.SpanPosition<=pos+.000001f);var right=derived.FirstOrDefault(s=>s.SpanPosition>=pos-.000001f);
                bool exact=left!=null&&right!=null&&(Math.Abs(left.SpanPosition-right.SpanPosition)<.000001f||Vector3.Distance((Vector3)left.Up,(Vector3)right.Up)<.000001f);
                Vector3? point=null;Vector3? tangent=null;
                if(exact){float fraction=right.SpanPosition==left.SpanPosition?0:(pos-left.SpanPosition)/(right.SpanPosition-left.SpanPosition);
                    point=t.TransformPoint(Vector3.Lerp((Vector3)left.Position,(Vector3)right.Position,fraction));
                    tangent=t.TransformVector((Vector3)left.SpanVec);}
                result.Add(new JObject{["spanPositionMetres"]=pos,["nativeChordMetres"]=values.Scale,["nativeOffsetMetres"]=values.Offset,
                    ["effectiveChordMetres"]=values.Scale*t.TransformVector(Vector3.forward).magnitude,
                    ["chordScale"]=t.TransformVector(Vector3.forward).magnitude,["worldCenter"]=point.HasValue?new JArray(Vec(point.Value)):null,
                    ["worldSpanVectorPerStation"]=tangent.HasValue?new JArray(Vec(tangent.Value)):null,
                    ["worldPositionStatus"]=exact?"native_derived_unbent_interval":"incomplete_curved_bend_requires_mesh_measurement"});
            }
            return new JObject{["identity"]=JToken.FromObject(Identity()),["partId"]=part.Id,["spanMetres"]=wing.WingSpan,["stations"]=result,
                ["source"]="native_WingBuilder_interpolation_and_current_derived_slices",["flipped"]=wing.Flipped,
                ["meaning"]="Neutral chord geometry; does not certify a deployed surface, render mesh or lift force."};
        }
        private unsafe JObject AirfoilInfo(JObject args)
        {
            if(args["name"]==null)return new JObject{["source"]="native_AirfoilRegistry_and_runtime_evaluator",["presets"]=new JArray(AirfoilRegistry.SimpleAirfoilPresets.Keys),
                ["families"]=new JArray(new JObject{["syntax"]="NACAabcd",["supported"]=true,["constraints"]="four digits, cd=01..99; a>0 requires b>0; native camber/geometry and runtime polars retained"},
                    new JObject{["syntax"]="NACA five-digit and modified",["supported"]=false,["reason"]="Current native runtime contains NotImplementedException; parser recognition is insufficient"},
                    new JObject{["syntax"]="Biconvex <positive thickness fraction>",["supported"]=true}),
                ["polarMethod"]="supply name, reynolds, mach, anglesDegrees; native section coefficients, not whole-aircraft flight validation"};
            string name=Required(args,"name");
            if(!AirfoilValid(name))throw new ApiError("unsupported_airfoil","Invalid or runtime-unsupported native airfoil: "+name);
            var foil=AirfoilRegistry.ParseAirfoil(name);var points=new JArray();
            for(int i=0;i<=40;i++){float x=i/40f;var p=foil.SamplePoint(x);if(float.IsNaN(p.x)||float.IsNaN(p.y)||float.IsInfinity(p.x)||float.IsInfinity(p.y))throw new ApiError("invalid_airfoil_geometry","Native sample is not finite.");points.Add(new JArray(x,p.x,p.y));}
            var result=new JObject{["name"]=name,["nativeType"]=foil.GetType().Name,["geometrySamples"]=points,["geometryUnits"]="fraction of chord: x, upper, lower",["polarStatus"]="not_assessed"};
            if(args["anglesDegrees"]!=null){
                var angles=args["anglesDegrees"] as JArray;if(angles==null||angles.Count==0||angles.Count>181)throw new ApiError("invalid_input","anglesDegrees needs 1..181 explicit angles.");
                float re=(float)PropertyValues.Convert(args["reynolds"],typeof(float),1000,1000000000,"chord Reynolds number");
                float mach=(float)PropertyValues.Convert(args["mach"],typeof(float),0,10,"free stream Mach");
                var pointers=new List<IntPtr>();
                try{
                    var runtime=foil.GetRuntimeAirfoil(pointers);SlicePolar polar;
                    runtime.function.Invoke(re,mach,in runtime,out polar);var samples=new JArray();
                    foreach(var angle in angles){float degrees=(float)PropertyValues.Convert(angle,typeof(float),-180,180,"angle degrees");
                        Unity.Mathematics.float2 cl,cd,cm;polar.Sample(degrees*Mathf.Deg2Rad,mach,out cl,out cd,out cm);
                        if(float.IsNaN(cl.x)||float.IsNaN(cd.x)||float.IsNaN(cm.x)||float.IsInfinity(cl.x)||float.IsInfinity(cd.x)||float.IsInfinity(cm.x))throw new ApiError("invalid_airfoil_polar","Native polar is not finite at these conditions.");
                        samples.Add(new JObject{["angleDegrees"]=degrees,["liftCoefficient"]=cl.x,["dragCoefficient"]=cd.x,["momentCoefficient"]=cm.x});}
                    result["polarStatus"]="native_section_evaluated";result["conditions"]=new JObject{["chordReynolds"]=re,["freeStreamMach"]=mach};result["polarSamples"]=samples;
                }finally{foreach(var pointer in pointers)UnsafeUtility.Free((void*)pointer,Allocator.Persistent);}
            }
            result["source"]="current_native_IAirfoil_SamplePoint_RuntimeAirfoil_and_SlicePolar.Sample";
            result["limitations"]="Section coefficients at declared conditions only, without installed-wing transforms/control-surface increments or whole-aircraft flight response.";
            return result;
        }
    }
}
