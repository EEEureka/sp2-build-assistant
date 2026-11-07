using System;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Xml.Linq;

namespace SP2BuildAssistant
{
    // Normalize native generated target sets and aerodynamic caches for content identity.
    // Raw XML/save/restore retains the caches; all editable drag settings remain significant.
    public static class SnapshotState
    {
        public const string Algorithm = "xml-sha256-native-derived-caches-v3";
        public const double RestoreEulerToleranceDegrees = 0.0001;
        public static bool EquivalentAfterNativeRestore(XElement expected, XElement actual)
        {
            // This tolerance is ONLY for validating a native reconstruction. Revision
            // fingerprints remain exact, so small player edits still invalidate stale writes.
            XElement left = new XElement(expected), right = new XElement(actual);
            var leftAssembly = left.Element("Assembly"); var rightAssembly = right.Element("Assembly");
            if (leftAssembly == null || rightAssembly == null || leftAssembly.Element("Parts") == null || rightAssembly.Element("Parts") == null) return false;
            var leftParts = leftAssembly.Element("Parts").Elements("Part").ToArray();
            var rightParts = rightAssembly.Element("Parts").Elements("Part").ToArray();
            if (leftParts == null || rightParts == null || leftParts.Length != rightParts.Length) return false;
            for (int i = 0; i < leftParts.Length; i++)
            {
                if ((string)leftParts[i].Attribute("id") != (string)rightParts[i].Attribute("id")) return false;
                var a = leftParts[i].Attribute("rotation"); var b = rightParts[i].Attribute("rotation");
                if (a == null || b == null || a.Value == b.Value) continue;
                double[] av, bv;
                try { av = a.Value.Split(',').Select(v => double.Parse(v, CultureInfo.InvariantCulture)).ToArray();
                      bv = b.Value.Split(',').Select(v => double.Parse(v, CultureInfo.InvariantCulture)).ToArray(); }
                catch (FormatException) { return false; }
                if (av.Length != 3 || bv.Length != 3) return false;
                for (int axis = 0; axis < 3; axis++)
                {
                    double delta = av[axis] - bv[axis]; delta -= Math.Floor((delta + 180) / 360) * 360;
                    if (double.IsNaN(delta) || double.IsInfinity(delta) || Math.Abs(delta) > RestoreEulerToleranceDegrees) return false;
                }
                b.Value = a.Value;
            }
            return Fingerprint(left) == Fingerprint(right);
        }
        public static string Fingerprint(XElement xml)
        {
            XElement copy = new XElement(xml);
            // PartDrag.WriteToXml emits only these computed arrays. Restrict omission to
            // actual part roots and Aircraft's direct CraftDrag, never modifier attributes.
            // Designer rendering/save can recalculate them without any player content edit.
            if (copy.Name == "Part") RemoveDragCache(copy);
            if (copy.Name == "Aircraft")
            {
                var parts = copy.Element("Assembly")?.Element("Parts");
                if (parts != null) foreach (var part in parts.Elements("Part")) RemoveDragCache(part);
                foreach (var drag in copy.Elements("CraftDrag")) RemoveDragCache(drag);
            }
            foreach (var element in copy.DescendantsAndSelf())
            {
                var ids = element.Name.LocalName == "PartTargeting.State" ? element.Attribute("partIds") : null;
                if (ids != null && (string)element.Attribute("targetMode") != "Custom")
                {
                    string[] values = ids.Value.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                    int parsed;
                    if (values.All(v => int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed)))
                        ids.Value = string.Join(",", values.Select(v => int.Parse(v, CultureInfo.InvariantCulture)).Distinct().OrderBy(v => v));
                }
                var attributes = element.Attributes().OrderBy(a => a.Name.ToString(), StringComparer.Ordinal).Select(a => new XAttribute(a)).ToArray();
                element.RemoveAttributes(); element.Add(attributes);
            }
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(copy.ToString(SaveOptions.DisableFormatting)))).Replace("-", "").ToLowerInvariant();
        }
        private static void RemoveDragCache(XElement element)
        {
            element.Attribute("drag")?.Remove();
            element.Attribute("dragArea")?.Remove();
        }
    }
}
