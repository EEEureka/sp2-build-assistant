using System.Collections.Generic;

namespace SP2BuildAssistant
{
    // Admission and eviction share this gate. A queue snapshot alone leaves a
    // race between accepting a restore request and evicting its checkpoint.
    internal sealed class RecoveryLeases
    {
        internal readonly object Gate=new object();
        private readonly Dictionary<string,string> targets=new Dictionary<string,string>();
        internal void Reserve(string operationId,string checkpointId){lock(Gate)targets[operationId]=checkpointId;}
        internal void Release(string operationId){lock(Gate)targets.Remove(operationId);}
        internal HashSet<string> Snapshot(){lock(Gate)return new HashSet<string>(targets.Values);}
    }
}
