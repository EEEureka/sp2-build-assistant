using System;
using System.Globalization;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // InputControllerData serializes these fields but omits most from overload metadata.
    // Keep this allowlist independent of Unity so input validation can be regression-tested.
    internal static class InputControllerFields
    {
        internal static readonly string[] Names = { "input", "activationGroup", "invert", "min", "max", "zeroOnDeactivate", "invertType" };
        internal static readonly string[] CommonInputs = { "Trim", "VTOL", "Throttle", "Brake", "Roll", "Aileron", "Pitch", "Yaw", "Flaps", "Disabled" };
        internal static bool TryValidate(string element, string attribute, JToken value)
        {
            if (element != "InputController.State" || !Names.Contains(attribute)) return false;
            if (value == null || value.Type == JTokenType.Null) throw new ApiError("required_attribute", attribute + " cannot be removed; write an explicit value.");
            string s = value.Type == JTokenType.String ? value.Value<string>() : value.ToString(Newtonsoft.Json.Formatting.None);
            if (attribute == "input" || attribute == "activationGroup")
            {
                if (value.Type != JTokenType.String || string.IsNullOrWhiteSpace(s) || s.Length > 4096)
                    throw new ApiError("invalid_input_controller", attribute + " requires a nonempty string of at most 4096 characters.");
                // Numerical activation groups outside 0..8 silently disable in native code.
                // Other strings are boolean expressions, compiled against the part context.
                if (attribute == "activationGroup" && double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out double group)
                    && (double.IsNaN(group) || double.IsInfinity(group) || group != Math.Truncate(group) || group < 0 || group > 8
                        || !int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out int _)))
                    throw new ApiError("out_of_range", "activationGroup requires an integer string from 0 to 8, or a boolean expression.");
            }
            else if (attribute == "invert" || attribute == "zeroOnDeactivate")
            {
                if ((value.Type != JTokenType.Boolean && value.Type != JTokenType.String) || (s != "true" && s != "false"))
                    throw new ApiError("invalid_boolean", attribute + " requires true or false.");
            }
            else if (attribute == "invertType")
            {
                if (value.Type != JTokenType.String || (s != "Axis" && s != "Output")) throw new ApiError("invalid_enum", "invertType requires Axis or Output.");
            }
            else
            {
                if ((value.Type != JTokenType.Float && value.Type != JTokenType.Integer && value.Type != JTokenType.String)
                    || !double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out double number)
                    || double.IsNaN(number) || double.IsInfinity(number) || Math.Abs(number) > float.MaxValue)
                    throw new ApiError("invalid_number", attribute + " requires a finite single-precision value.");
                // min > max is a meaningful native output mapping; do not reorder or clamp it.
            }
            return true;
        }
        internal static JObject Description()
        {
            var descriptions = new[] {
                "Native axis ID or float Funky Trees expression. Aileron uses the connected wing's flipped state to choose the Roll sign; ordinary Roll does not.",
                "Integer string 0..8 (0 means always active), or boolean Funky Trees expression in the part context.",
                "Invert input or output according to invertType.",
                "Finite output value at input -1. May exceed max for an intentionally reversed mapping.",
                "Finite output value at input +1. No automatic ordering with min.",
                "Reset output to zero while inactive; false retains the previous output.",
                "Axis negates the input before min/max mapping; Output negates the mapped output." };
            return new JObject { ["element"]="InputController.State", ["source"]="plugin_allowlist_from_native_serializer_and_controller",
                ["operation"]="part.update", ["pathPattern"]="InputController.State[index]", ["minimumPluginVersion"]="0.4.8",
                ["expressionValidation"]="Changed input and activationGroup are compiled without evaluating telemetry; unchanged controllers are not revalidated.",
                ["attributes"]=new JArray(Names.Select((name,index)=>new JObject { ["name"]=name,
                    ["type"]=(name=="min" || name=="max")?"finiteFloat":(name=="invert" || name=="zeroOnDeactivate")?"boolean":"string",
                    ["description"]=descriptions[index] })), ["commonInputIds"]=new JArray(CommonInputs),
                ["inputAllowsExpression"]=true, ["invertTypes"]=new JArray("Axis","Output") };
        }
    }
}
