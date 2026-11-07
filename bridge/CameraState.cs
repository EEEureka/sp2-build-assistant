using System;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // State comparison is independent of Unity. Pose tolerances are absolute;
    // only the derived view-matrix dot products have a float rounding bound.
    // Object identities, modes and projection checks remain independent.
    internal static class CameraState
    {
        internal const double PositionTolerance = .0001;
        internal const double AngleToleranceDegrees = .001;
        internal const double ScalarTolerance = .000001;

        private static bool Numbers(JToken token,int count,out double[] values)
        {
            var array=token as JArray;values=null;
            if(array==null||array.Count!=count||array.Any(x=>x.Type!=JTokenType.Float&&x.Type!=JTokenType.Integer))return false;
            values=array.Select(x=>(double)x).ToArray();
            return values.All(x=>!double.IsNaN(x)&&!double.IsInfinity(x)&&Math.Abs(x)<=float.MaxValue);
        }
        private static bool Matrix(JToken token,out double[][] values)
        {
            values=null;var array=token as JArray;if(array==null||array.Count!=4)return false;
            var rows=new double[4][];
            for(int i=0;i<4;i++)if(!Numbers(array[i],4,out rows[i]))return false;
            values=rows;return true;
        }
        // Half an ULP bounds one correctly rounded float operation. Use the
        // larger binade spacing at powers of two, including subnormal values.
        private static double HalfFloatUlp(double value)
        {
            value=Math.Abs(value);
            if(value>float.MaxValue)return double.PositiveInfinity;
            if(value<Math.Pow(2,-126))return Math.Pow(2,-150);
            double exponent=Math.Floor(Math.Log(value,2));
            return Math.Pow(2,exponent-24);
        }
        private static double DotRoundoff(double[] row,double[] position)
        {
            var products=Enumerable.Range(0,3).Select(i=>row[i]*position[i]).ToArray();
            // A three-term dot product: three multiplications, two additions.
            // Bound either association using the largest pairwise partial sum.
            double partial=Math.Max(Math.Abs(products[0]+products[1]),Math.Max(Math.Abs(products[0]+products[2]),Math.Abs(products[1]+products[2])));
            return products.Sum(HalfFloatUlp)+HalfFloatUlp(partial)+HalfFloatUlp(products.Sum())+HalfFloatUlp(row[3]);
        }
        private static JObject ViewMatrixDifference(JObject before,JObject after,JToken a,JToken b)
        {
            double[][] aa,bb;double[] pa,pb;
            if(!Matrix(a,out aa)||!Matrix(b,out bb)||!Numbers(before["positionWorld"],3,out pa)||!Numbers(after["positionWorld"],3,out pb))
                return new JObject{["field"]="worldToCameraRows",["before"]=a?.DeepClone(),["after"]=b?.DeepClone(),["metric"]="valid_finite_view_matrix",["error"]=null,["tolerance"]=ScalarTolerance,["withinTolerance"]=false};
            double directError=0,rawError=0,adjustedError=0;
            for(int i=0;i<4;i++)for(int j=0;j<4;j++){
                double delta=Math.Abs(bb[i][j]-aa[i][j]);rawError=Math.Max(rawError,delta);
                if(i==3||j<3)directError=Math.Max(directError,delta);
            }
            var rows=new JArray();
            for(int i=0;i<3;i++){
                // t=-R*p. Compensate the OBSERVED pose change, not the allowed
                // angular/position tolerance; a moved camera still fails its
                // separate pose guard. This also preserves custom-matrix offsets.
                double expected=0;
                for(int j=0;j<3;j++)expected-=(bb[i][j]-aa[i][j])*pa[j]+bb[i][j]*(pb[j]-pa[j]);
                double raw=bb[i][3]-aa[i][3],residual=raw-expected;
                double rounding=DotRoundoff(aa[i],pa)+DotRoundoff(bb[i],pb);
                if(double.IsInfinity(rounding))return new JObject{["field"]="worldToCameraRows",["metric"]="finite_float32_dot_product",["error"]=null,["tolerance"]=ScalarTolerance,["withinTolerance"]=false};
                adjustedError=Math.Max(adjustedError,Math.Max(0,Math.Abs(residual)-rounding));
                rows.Add(new JObject{["row"]=i,["rawTranslationDifference"]=raw,["observedPosePropagation"]=expected,["compensatedResidual"]=residual,
                    ["float32RoundoffBound"]=rounding,["tolerance"]=ScalarTolerance+rounding,["withinTolerance"]=Math.Abs(residual)<=ScalarTolerance+rounding});
            }
            double error=Math.Max(directError,adjustedError);
            return new JObject{["field"]="worldToCameraRows",["before"]=a.DeepClone(),["after"]=b.DeepClone(),
                ["metric"]="pose_compensated_excess_over_float32_roundoff",["error"]=error,["tolerance"]=ScalarTolerance,["withinTolerance"]=error<=ScalarTolerance,
                ["maxRawAbsoluteDifference"]=rawError,["linearAndHomogeneousMaxDifference"]=directError,["translationRows"]=rows};
        }

        internal static double QuaternionAngle(JArray a, JArray b)
        {
            double na=Math.Sqrt(a.Sum(x=>Math.Pow((double)x,2))),nb=Math.Sqrt(b.Sum(x=>Math.Pow((double)x,2)));
            if(na==0||nb==0)return double.PositiveInfinity;
            double plus=0,minus=0;
            for(int i=0;i<4;i++){double x=(double)a[i]/na,y=(double)b[i]/nb;plus+=(x-y)*(x-y);minus+=(x+y)*(x+y);}
            return 4*Math.Asin(Math.Min(1,Math.Sqrt(Math.Min(plus,minus))/2))*180/Math.PI;
        }
        internal static JArray Compare(JObject before,JObject after)
        {
            var diffs=new JArray();
            foreach(string key in before.Properties().Select(p=>p.Name).Union(after.Properties().Select(p=>p.Name))){
                var a=before[key];var b=after[key];
                if(key=="worldToCameraRows"){
                    double[][] unchanged;
                    if(JToken.DeepEquals(a,b)&&Matrix(a,out unchanged))continue;
                    var matrixDiff=ViewMatrixDifference(before,after,a,b);
                    if(!JToken.DeepEquals(a,b)||!(bool)matrixDiff["withinTolerance"])diffs.Add(matrixDiff);
                    continue;
                }
                if(JToken.DeepEquals(a,b))continue;
                double tolerance=ScalarTolerance,error=double.PositiveInfinity;
                string metric="absolute";
                if(a!=null&&b!=null){
                    if(key.EndsWith("Quaternion")){error=QuaternionAngle((JArray)a,(JArray)b);tolerance=AngleToleranceDegrees;metric="degrees";}
                    else if(key.EndsWith("Position",StringComparison.OrdinalIgnoreCase)||key.EndsWith("PositionWorld",StringComparison.OrdinalIgnoreCase)||key=="targetWorld"){
                        error=Math.Sqrt(((JArray)a).Select((x,i)=>Math.Pow((double)x-(double)b[i],2)).Sum());tolerance=PositionTolerance;metric="metres";
                    }else if(a.Type==JTokenType.Float&&b.Type==JTokenType.Float){error=Math.Abs((double)a-(double)b);}
                    else if(a is JArray && b is JArray && ((JArray)a).Count==((JArray)b).Count){
                        var aa=((JContainer)a).Descendants().OfType<JValue>().ToArray();var bb=((JContainer)b).Descendants().OfType<JValue>().ToArray();
                        if(aa.Length==bb.Length&&aa.All(x=>x.Type==JTokenType.Float||x.Type==JTokenType.Integer)&&bb.All(x=>x.Type==JTokenType.Float||x.Type==JTokenType.Integer))
                            error=aa.Select((x,i)=>Math.Abs((double)x-(double)bb[i])).DefaultIfEmpty(0).Max();
                    }
                }
                bool strict=key.EndsWith("InstanceId")||key=="enabled"||key=="projection"||key=="cullingMask"||key=="clearFlags";
                if(strict){error=double.PositiveInfinity;tolerance=0;metric="exact";}
                diffs.Add(new JObject{["field"]=key,["before"]=a?.DeepClone(),["after"]=b?.DeepClone(),["metric"]=metric,
                    ["error"]=double.IsInfinity(error)?(JToken)null:error,["tolerance"]=tolerance,["withinTolerance"]=!double.IsNaN(error)&&error<=tolerance});
            }
            return diffs;
        }
        internal static bool Passed(JArray differences){return differences.All(x=>(bool)x["withinTolerance"]);}
    }
}
