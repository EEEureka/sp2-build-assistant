using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    internal static partial class VisualCore
    {
        private static readonly string[] CenterKeys = { "com", "col", "cot" };
        private static readonly byte[][] CenterColors = { new byte[] { 255, 118, 118 }, new byte[] { 91, 185, 255 }, new byte[] { 255, 217, 83 } };
        private static V[] CenterPoints(JObject report)
        { return report == null ? new V[0] : CenterKeys.Select(k => report["centers"][k]["positionFrameMeters"]).Where(CentersCore.Vector).Select(CentersCore.V).ToArray(); }
        private static MeshData[] CenterFitMeshes(MeshData[] meshes, JObject report)
        {
            var points = CenterPoints(report);
            // Fit-only points never enter rasterization or part-ID buffers.
            return points.Length == 0 ? meshes : meshes.Concat(new[] { new MeshData { Vertices = points, Indices = Enumerable.Range(0, points.Length).ToArray() } }).ToArray();
        }
        internal static void DrawCenters(Image img, JObject report, View view, V target, double scale)
        {
            var projected = new JArray(); var coords = new Dictionary<string, int[]>();
            foreach (string key in CenterKeys)
            {
                var c = report["centers"][key]; if (!CentersCore.Vector(c["positionFrameMeters"])) continue;
                var delta = CentersCore.V(c["positionFrameMeters"]) - target;
                double x = img.Width * .5 + delta.Dot(view.Right) * scale, y = img.Height * .5 - delta.Dot(view.Up) * scale;
                projected.Add(new JObject { ["center"] = key, ["pixel"] = new JArray(x, y), ["status"] = c["status"].DeepClone(), ["positionFrameMeters"] = c["positionFrameMeters"].DeepClone() });
                if (x >= 0 && x < img.Width && y >= 0 && y < img.Height) coords[key] = new[] { (int)Math.Round(x), (int)Math.Round(y) };
            }
            if (coords.TryGetValue("com", out int[] origin)) foreach (string key in new[] { "col", "cot" }) if (coords.TryGetValue(key, out int[] p))
            {
                int steps = Math.Max(Math.Abs(p[0] - origin[0]), Math.Abs(p[1] - origin[1]));
                for (int n = 0; n <= steps; n++) if (n % 10 < 5) Pixel(img, origin[0] + (int)((p[0] - origin[0]) * (double)n / Math.Max(1,steps)), origin[1] + (int)((p[1] - origin[1]) * (double)n / Math.Max(1,steps)), 215, 222, 236);
            }
            // Fixed separate legend rows and leaders keep coincident markers at their true location.
            for (int index = 0; index < CenterKeys.Length; index++)
            {
                string key = CenterKeys[index]; var color = CenterColors[index]; int labelY = 30 + index * 18;
                string status = (string)report["centers"][key]["status"];
                Text(img, 12, labelY, key.ToUpperInvariant() + (status == "unavailable" ? " N A" : status == "partial" ? " PARTIAL" : ""), color[0], color[1], color[2], true);
                if (!coords.TryGetValue(key, out int[] p)) continue;
                DrawLine(img, 86, labelY + 3, p[0], p[1], color[0], color[1], color[2]);
                int radius = 6 + index * 3;
                if (index == 0) { for (int a = 0; a < 360; a++) Pixel(img, p[0] + (int)Math.Round(Math.Cos(a*Math.PI/180)*radius), p[1] + (int)Math.Round(Math.Sin(a*Math.PI/180)*radius), color[0], color[1], color[2]); }
                else if (index == 1) { DrawLine(img,p[0],p[1]-radius,p[0]-radius,p[1]+radius,color[0],color[1],color[2]);DrawLine(img,p[0]-radius,p[1]+radius,p[0]+radius,p[1]+radius,color[0],color[1],color[2]);DrawLine(img,p[0]+radius,p[1]+radius,p[0],p[1]-radius,color[0],color[1],color[2]); }
                else { int[] x={0,radius,0,-radius,0},y={-radius,0,radius,0,-radius};for(int i=0;i<4;i++)DrawLine(img,p[0]+x[i],p[1]+y[i],p[0]+x[i+1],p[1]+y[i+1],color[0],color[1],color[2]); }
            }
            int line = img.Height - 72;
            foreach (string key in new[] { "colFromCom", "cotFromCom", "cotFromCol" })
            {
                var relation = report["relations"][key] as JObject; if (relation == null) continue;
                var v = CentersCore.V(relation["deltaFrameMeters"]);
                string name = key == "colFromCom" ? "COL-COM" : key == "cotFromCom" ? "COT-COM" : "COT-COL";
                Func<double,string> f = n => n.ToString("0.###", CultureInfo.InvariantCulture);
                Text(img,12,line,name+"  X "+f(v.X)+"  Y "+f(v.Y)+"  Z "+f(v.Z)+" M",225,232,242,true); line += 11;
            }
            Text(img,12,img.Height-35,"FRAME AXES - DESIGNER PROXIES - NOT STABILITY",205,213,229,true);
            img.Info["centersOverlay"] = new JObject { ["analysisId"] = report["analysisId"].DeepClone(), ["markers"] = projected,
                ["meaning"] = "Always-on-top annotations, not surface hits. Dashed lines are projected separations; XYZ labels are signed frame deltas in metres. Circle COM, triangle COL, diamond COT. Raw and ID images exclude annotations." };
        }
        private static void RenderCentersDetails(Result result, MeshData[] meshes, int[] ids, Dictionary<int,int> tokens, JObject report, double overviewScale, int width, int height, Action check, ref long work, ref long pixels)
        {
            var points = CenterPoints(report); var status = new JObject { ["status"] = "not_needed", ["minimumPairSeparationPixels"] = 96 };
            result.Manifest["centersDetailStatus"] = status;
            if (points.Length == 0) { status["status"] = "no_available_centers"; return; }
            double minDistance = double.PositiveInfinity;
            for (int i=0;i<points.Length;i++) for (int j=i+1;j<points.Length;j++) { var d=points[i]-points[j];minDistance=Math.Min(minDistance,Math.Sqrt(d.Dot(d))); }
            var views = new[] { NamedView("right"), NamedView("top"), NamedView("front") };
            if (points.Length > 1 && minDistance * overviewScale < 96)
            {
                if (pixels+(long)width*height*3>16000000) status["status"]="budget_exceeded";
                else
                {
                    var box=new Box();foreach(var point in points)box.Add(point);var target=box.Center;
                    // Keep at least half a metre of shared context, including exactly coincident centers.
                    var padding=new V(.25,.25,.25);var fit=new[]{new MeshData{Vertices=points.Concat(new[]{target-padding,target+padding}).ToArray(),Indices=Enumerable.Range(0,points.Length+2).ToArray()}};
                    double zoom=Fit(fit,views,target,width,height);status["status"]="generated";status["pixelsPerMetre"]=zoom;
                    foreach(var view in views)
                    {
                        check();pixels+=(long)width*height;var img=Raster(meshes,ids,tokens,view,target,zoom,width,height,check,ref work,report);DrawCenters(img,report,view,target,zoom);
                        img.Info["detail"]=true;img.Info["cropMeaning"]="Center cluster detail; aircraft can extend beyond image. All centers share one scale.";
                        string name="centers-detail-"+view.Name;AddImage(result,name,img);RecommendCenterImage(result,name,"center_cluster_detail",zoom);img.Pixels=null;img.RawPixels=null;
                    }
                }
            }
            // A distant center must not make the model impossible to inspect in the sole recommendation.
            var modelTarget=Bounds(meshes).Center;double modelScale=Fit(meshes,views,modelTarget,width,height);
            if (overviewScale < modelScale*.5 && pixels+(long)width*height<=16000000)
            {
                var view=NamedView("isometric");double zoom=Fit(meshes,new[]{view},modelTarget,width,height);check();pixels+=(long)width*height;
                var img=Raster(meshes,ids,tokens,view,modelTarget,zoom,width,height,check,ref work,report);img.Info["cropMeaning"]="Aircraft context at a different scale; no centers drawn here. Use overview for center relationships.";
                AddImage(result,"centers-aircraft-context",img);RecommendCenterImage(result,"centers-aircraft-context","aircraft_small_in_center_overview",zoom);img.Pixels=null;img.RawPixels=null;
            }
        }
        private static void RecommendCenterImage(Result result,string name,string reason,double scale)
        {
            ((JArray)result.Manifest["recommendedImages"]).Add(name+".png");
            ((JArray)result.Manifest["imageRecommendations"]).Add(new JObject{["file"]=name+".png",["view"]=name,["reason"]=reason,["pixelsPerMetre"]=scale,["meaning"]="Additional view at its stated scale. Never compare raw pixel lengths across images."});
        }
    }
}
