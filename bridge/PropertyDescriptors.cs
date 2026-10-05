using System;
using System.Collections;
using System.Globalization;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    internal static class PropertyValues
    {
        internal static JToken Read(object v)
        {
            if(v==null)return JValue.CreateNull();
            if(v is Vector2){var x=(Vector2)v;return new JArray(x.x,x.y);}
            if(v is Vector3){var x=(Vector3)v;return new JArray(x.x,x.y,x.z);}
            if(v is Vector4){var x=(Vector4)v;return new JArray(x.x,x.y,x.z,x.w);}
            if(v is Quaternion){var x=(Quaternion)v;return new JArray(x.x,x.y,x.z,x.w);}
            if(v is Color){var x=(Color)v;return new JArray(x.r,x.g,x.b,x.a);}
            if(v is Pose){var x=(Pose)v;return new JObject{["position"]=Read(x.position),["rotationQuaternion"]=Read(x.rotation)};}
            if(v is Enum)return v.ToString();
            if(v is string||v is bool||v is decimal||v is float||v is double||v is int||v is uint||v is long)return JToken.FromObject(v);
            if(v is IList){var a=new JArray();foreach(var x in (IList)v)a.Add(Read(x));return a;}
            return new JObject{["representation"]="native_complex_value",["nativeType"]=v.GetType().FullName};
        }
        internal static string TypeName(Type t)
        {
            if(t==typeof(bool))return "boolean";if(t.IsEnum||t==typeof(string))return "string";
            if(t==typeof(int)||t==typeof(uint)||t==typeof(long))return "integer";
            if(t==typeof(float)||t==typeof(double)||t==typeof(decimal))return "number";
            if(t==typeof(Pose))return "pose";
            if(t==typeof(Vector2)||t==typeof(Vector3)||t==typeof(Vector4)||t==typeof(Quaternion)||t==typeof(Color)||typeof(IList).IsAssignableFrom(t))return "array";
            return "object";
        }
        internal static double Number(JToken v,double min,double max,string label)
        {
            if(v==null||(v.Type!=JTokenType.Integer&&v.Type!=JTokenType.Float))throw new ApiError("invalid_property_value",label+" needs a JSON number.");
            double n=(double)v;if(double.IsNaN(n)||double.IsInfinity(n)||n<min||n>max)throw new ApiError("property_out_of_range",label+" must be finite and in ["+min.ToString(CultureInfo.InvariantCulture)+", "+max.ToString(CultureInfo.InvariantCulture)+"].");return n;
        }
        internal static object Convert(JToken v,Type t,double min,double max,string label)
        {
            if(t==typeof(string)){if(v?.Type!=JTokenType.String)throw new ApiError("invalid_property_value",label+" needs a string.");if(((string)v).Length>16384)throw new ApiError("invalid_property_value",label+" exceeds 16384 characters.");return (string)v;}
            if(t==typeof(bool)){if(v?.Type!=JTokenType.Boolean)throw new ApiError("invalid_property_value",label+" needs a boolean.");return (bool)v;}
            if(t.IsEnum){if(v?.Type!=JTokenType.String||!Enum.GetNames(t).Contains((string)v))throw new ApiError("invalid_property_value",label+" needs a native enum ID: "+string.Join(", ",Enum.GetNames(t)));return Enum.Parse(t,(string)v);}
            if(t==typeof(Pose)){
                VisualScope.Keys(v as JObject,"position","rotationQuaternion");
                return new Pose((Vector3)Convert(v["position"],typeof(Vector3),-100000,100000,label+".position"),(Quaternion)Convert(v["rotationQuaternion"],typeof(Quaternion),-double.MaxValue,double.MaxValue,label+".rotationQuaternion"));
            }
            int n=t==typeof(Vector2)?2:t==typeof(Vector3)?3:t==typeof(Vector4)||t==typeof(Quaternion)||t==typeof(Color)?4:0;
            if(n!=0){
                var a=v as JArray;if(a==null||a.Count!=n)throw new ApiError("invalid_property_value",label+" needs "+n+" numbers.");
                double[] d=a.Select(x=>Number(x,min,max,label)).ToArray();
                if(t==typeof(Quaternion)){double len=Math.Sqrt(d.Sum(x=>x*x));if(len<1e-12||double.IsInfinity(len))throw new ApiError("invalid_property_value","Quaternion must have finite nonzero length.");return new Quaternion((float)(d[0]/len),(float)(d[1]/len),(float)(d[2]/len),(float)(d[3]/len));}
                if(d.Any(x=>Math.Abs(x)>float.MaxValue))throw new ApiError("invalid_property_value",label+" exceeds native float precision range.");
                if(n==2)return new Vector2((float)d[0],(float)d[1]);if(n==3)return new Vector3((float)d[0],(float)d[1],(float)d[2]);
                if(t==typeof(Color))return new Color((float)d[0],(float)d[1],(float)d[2],(float)d[3]);return new Vector4((float)d[0],(float)d[1],(float)d[2],(float)d[3]);
            }
            if(t==typeof(System.Collections.Generic.List<int>)){
                var a=v as JArray;if(a==null||a.Count>2048)throw new ApiError("invalid_property_value",label+" needs up to 2048 part IDs.");
                var ids=a.Select(x=>{if(x.Type!=JTokenType.Integer)throw new ApiError("invalid_property_value","Part IDs must be integers.");return (int)Number(x,0,int.MaxValue,label);}).ToList();
                if(ids.Distinct().Count()!=ids.Count)throw new ApiError("invalid_property_value","Duplicate target part IDs.");return ids;
            }
            if(TypeName(t)=="integer"&&v?.Type!=JTokenType.Integer)throw new ApiError("invalid_property_value",label+" needs an integer.");
            double scalar=Number(v,min,max,label);
            try {var result=System.Convert.ChangeType(scalar,t,CultureInfo.InvariantCulture);if(result is float&&(float.IsInfinity((float)result)||float.IsNaN((float)result)))throw new OverflowException();return result;}
            catch(Exception e)when(e is OverflowException||e is InvalidCastException){throw new ApiError("invalid_property_value",label+" cannot be represented as "+t.Name+".");}
        }
    }
}
