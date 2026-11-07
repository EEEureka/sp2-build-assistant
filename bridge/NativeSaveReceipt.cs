using System;
using Assets.Scripts.Craft.CraftFiles;
using HarmonyLib;
using System.Xml.Linq;

namespace SP2BuildAssistant
{
    // Designer.Save catches CraftDatabaseException itself. A scoped receipt of
    // the exact native database return distinguishes that failure from a save.
    internal sealed class NativeSaveReceipt : IDisposable
    {
        private static NativeSaveReceipt active;
        private readonly string target;
        internal CraftFileInfo Saved;
        internal NativeSaveReceipt(string target){
            if(active!=null)throw new InvalidOperationException("A native save receipt is already active.");
            this.target=target;active=this;
        }
        public void Dispose(){if(active==this)active=null;}
        [HarmonyPatch(typeof(CraftDatabase),"SaveCraft",new[]{typeof(string),typeof(XElement),typeof(bool),typeof(bool)})]
        private static class CaptureSave
        {
            private static void Postfix(string relativePath,CraftFileInfo __result){
                if(active!=null&&__result!=null&&string.Equals(relativePath,active.target,StringComparison.OrdinalIgnoreCase))
                    active.Saved=__result;
            }
        }
    }
}
