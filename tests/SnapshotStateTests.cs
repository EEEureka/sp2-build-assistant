using System;
using System.IO;
using System.Xml.Linq;
using SP2BuildAssistant;

class SnapshotStateTests
{
    static int checks;
    static void Check(string name, bool result)
    {
        if (!result) throw new Exception("FAILED: " + name);
        checks++; Console.WriteLine("PASS " + name);
    }
    static string Hash(string xml) { return SnapshotState.Fingerprint(XElement.Parse(xml)); }
    static void Main(string[] args)
    {
        string a = "<Aircraft><PartTargeting.State targetMode='MultipleParts' partIds='1,42,82'/></Aircraft>";
        string b = "<Aircraft><PartTargeting.State partIds='82,1,42' targetMode='MultipleParts'/></Aircraft>";
        Check("Native generated target enumeration order", Hash(a) == Hash(b));
        Check("Multiple native colliders for same targeted part", Hash(a) == Hash(b.Replace("82,1,42", "82,82,1,42,42")));
        Check("Actual target membership", Hash(a) != Hash(b.Replace("82,1,42", "82,1,43")));
        Check("Custom target ordering remains significant", Hash(a.Replace("MultipleParts", "Custom")) != Hash(b.Replace("MultipleParts", "Custom")));
        Check("Attribute ordering", Hash("<Part id='1' name='A'/>") == Hash("<Part name='A' id='1'/>"));
        Check("Real property edits", Hash("<Part id='1' name='A'/>") != Hash("<Part id='1' name='B'/>"));
        Check("Setter evaluation order preserved", Hash("<Variables><Setter variable='A'/><Setter variable='B'/></Variables>") != Hash("<Variables><Setter variable='B'/><Setter variable='A'/></Variables>"));
        XElement source = XElement.Parse(a); string original = source.ToString(SaveOptions.DisableFormatting);
        SnapshotState.Fingerprint(source);
        Check("Do not mutate source XML", original == source.ToString(SaveOptions.DisableFormatting));
        string craft = "<Aircraft><Assembly><Parts><Part id='1' rotation='289.1011,83.87779,275.7875' position='0,1,0'/></Parts></Assembly></Aircraft>";
        XElement exact = XElement.Parse(craft);
        XElement nativeFloat = XElement.Parse(craft.Replace("83.87779", "83.87778"));
        Check("Native Euler roundtrip accepted for restore", SnapshotState.EquivalentAfterNativeRestore(exact, nativeFloat));
        Check("Revision detects even tiny rotation edits", SnapshotState.Fingerprint(exact) != SnapshotState.Fingerprint(nativeFloat));
        Check("Actual rotation change rejected for restore", !SnapshotState.EquivalentAfterNativeRestore(exact, XElement.Parse(craft.Replace("83.87779", "84"))));
        Check("Even tiny position change rejected for restore", !SnapshotState.EquivalentAfterNativeRestore(exact, XElement.Parse(craft.Replace("0,1,0", "0,1.000001,0"))));
        if (args.Length >= 2)
            Check("Real Super Wasp read-only snapshots", SnapshotState.Fingerprint(XElement.Parse(File.ReadAllText(args[0]))) == SnapshotState.Fingerprint(XElement.Parse(File.ReadAllText(args[1]))));
        if (args.Length == 4)
            Check("Real Super Wasp native undo reconstruction", SnapshotState.EquivalentAfterNativeRestore(XElement.Parse(File.ReadAllText(args[2])), XElement.Parse(File.ReadAllText(args[3]))));
        Console.WriteLine("Checks passed: " + checks);
    }
}
