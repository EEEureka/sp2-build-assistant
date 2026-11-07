using System;
using System.IO;
using System.Linq;

namespace SP2BuildAssistant
{
    // A native save name, never an arbitrary host filesystem path.
    public sealed class CraftSaveTarget
    {
        public string Id { get; private set; }
        public string Name { get; private set; }
        internal void UseExistingId(string id){Id=id;}
        public static CraftSaveTarget Parse(string name)
        {
            if(string.IsNullOrWhiteSpace(name)||name.Length>200)
                throw new ArgumentException("name must contain 1..200 characters, without .xml.");
            var segments=name.Replace('\\','/').Split('/');
            foreach(var segment in segments){
                if(string.IsNullOrWhiteSpace(segment)||segment.Length>120||segment!=segment.Trim()||segment.EndsWith(".")||
                    segment.Any(c=>c<32||"<>:\"|?*".Contains(c))||segment=="."||segment==".."||segment.StartsWith("__"))
                    throw new ArgumentException("Use a relative craft name with valid folder/name segments; reserved names and traversal are forbidden.");
                string device=segment.Split('.')[0].ToUpperInvariant();
                if(new[]{"CON","PRN","AUX","NUL","CONIN$","CONOUT$"}.Contains(device)||
                    (device.Length==4&&(device.StartsWith("COM")||device.StartsWith("LPT"))&&"123456789¹²³".Contains(device[3])))
                    throw new ArgumentException("Windows device names are not craft names.");
            }
            if(new[]{"Stock Craft","Required Craft","Autosave","Quicksave"}.Contains(segments[0],StringComparer.OrdinalIgnoreCase))
                throw new ArgumentException("Native stock, required, autosave and quicksave directories cannot be save targets.");
            if(segments.Last().EndsWith(".xml",StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Supply name without the .xml extension.");
            return new CraftSaveTarget{Id=string.Join(Path.DirectorySeparatorChar.ToString(),segments)+".xml",Name=segments.Last()};
        }
    }
}
