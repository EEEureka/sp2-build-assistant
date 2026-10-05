using System;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    internal static class ReadModels
    {
        internal static string View(JObject args)
        {
            if (args["view"] == null) return "legacy";
            if (args["view"].Type != JTokenType.String || ((string)args["view"] != "legacy" && (string)args["view"] != "structured"))
                throw new ApiError("invalid_input", "view must be legacy or structured.");
            return (string)args["view"];
        }
        private static int Number(string value, string field)
        {
            if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsed))
                throw new ApiError("invalid_native_data", "Invalid native integer: " + field);
            return parsed;
        }
        private static JArray PointIds(XAttribute value)
        { return new JArray(((string)value ?? "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries).Select(v => Number(v, value?.Name.ToString()))); }
        internal static JArray Connections(XElement root)
        {
            return new JArray((root?.Elements("Connection") ?? Enumerable.Empty<XElement>()).Select(e => new JObject {
                ["partA"] = Number((string)e.Attribute("partA"), "partA"), ["partB"] = Number((string)e.Attribute("partB"), "partB"),
                ["attachPointsA"] = PointIds(e.Attribute("attachPointsA")), ["attachPointsB"] = PointIds(e.Attribute("attachPointsB")) }));
        }
        internal static JArray Setters(XElement root)
        {
            return new JArray((root?.Elements("Setter") ?? Enumerable.Empty<XElement>()).Select((e, index) => new JObject {
                ["index"] = index, ["variable"] = (string)e.Attribute("variable"), ["function"] = (string)e.Attribute("function"),
                ["priority"] = Number((string)e.Attribute("priority") ?? "0", "priority"), ["activator"] = (string)e.Attribute("activator") }));
        }
        internal static int[] Reorder(JToken token, int count)
        {
            var array = token as JArray;
            const string message = "order lists ALL old zero-based setter indices in the desired NEW sequence (e.g. [2,0,1] moves old index 2 first). Use each integer exactly once.";
            if (array == null || array.Count != count) throw new ApiError("invalid_order", message);
            var order = new int[count];
            for (int i = 0; i < count; i++)
                if (array[i].Type != JTokenType.Integer || !int.TryParse(array[i].ToString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out order[i]) || order[i] < 0 || order[i] >= count)
                    throw new ApiError("invalid_order", message);
            if (order.Distinct().Count() != count) throw new ApiError("invalid_order", message);
            return order;
        }
    }
}
