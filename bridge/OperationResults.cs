using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // Only completed payloads are evicted. The server's operation/request-id
    // records remain alive, so expiration can never schedule an edit again.
    internal sealed class OperationResults
    {
        private sealed class Entry
        {
            public string Id;
            public byte[] Bytes;
            public long JsonBytes;
            public DateTime Completed;
        }
        private readonly object gate = new object();
        private readonly Dictionary<string, LinkedListNode<Entry>> entries = new Dictionary<string, LinkedListNode<Entry>>();
        private readonly LinkedList<Entry> order = new LinkedList<Entry>();
        private readonly Func<DateTime> clock;
        private readonly long budget;
        private readonly TimeSpan lifetime;
        private long retainedBytes, retainedJsonBytes, ageExpirations, capacityExpirations, oversized;
        internal OperationResults(long budgetBytes = 64L * 1024 * 1024, TimeSpan? lifetime = null, Func<DateTime> clock = null)
        {
            if (budgetBytes < 1) throw new ArgumentOutOfRangeException(nameof(budgetBytes));
            this.budget = budgetBytes;
            this.lifetime = lifetime ?? TimeSpan.FromMinutes(15);
            this.clock = clock ?? (() => DateTime.UtcNow);
        }
        internal bool Save(string id, JObject value)
        {
            // Compact JSON plus compression replaces retained JObject trees.
            // No Unity state is referenced by this cache. Temporary packing and
            // in-flight HTTP buffers are excluded from its retained byte budget.
            byte[] raw = Encoding.UTF8.GetBytes(value.ToString(Formatting.None));
            byte[] packed;
            using (var buffer = new MemoryStream())
            {
                using (var zip = new GZipStream(buffer, CompressionMode.Compress, true)) zip.Write(raw, 0, raw.Length);
                packed = buffer.ToArray();
            }
            lock (gate)
            {
                Trim();
                if (entries.ContainsKey(id)) throw new InvalidOperationException("A completed operation cannot replace its result.");
                if (packed.LongLength > budget) { oversized++; return false; }
                while (retainedBytes + packed.LongLength > budget) { RemoveFirst(); capacityExpirations++; }
                var e = new Entry { Id = id, Bytes = packed, JsonBytes = raw.LongLength, Completed = clock() };
                entries.Add(id, order.AddLast(e)); retainedBytes += packed.LongLength; retainedJsonBytes += raw.LongLength;
                return true;
            }
        }
        internal string Read(string id)
        {
            byte[] packed;
            lock (gate)
            {
                Trim();
                if (!entries.TryGetValue(id, out LinkedListNode<Entry> entry)) return null;
                packed = entry.Value.Bytes;
            }
            using (var source = new MemoryStream(packed, false))
            using (var zip = new GZipStream(source, CompressionMode.Decompress))
            using (var reader = new StreamReader(zip, Encoding.UTF8)) return reader.ReadToEnd();
        }
        private void Trim()
        {
            DateTime now = clock();
            while (order.First != null && now - order.First.Value.Completed >= lifetime) { RemoveFirst(); ageExpirations++; }
        }
        private void RemoveFirst()
        {
            var e = order.First.Value; retainedBytes -= e.Bytes.LongLength; retainedJsonBytes -= e.JsonBytes;
            entries.Remove(e.Id); order.RemoveFirst();
        }
        internal JObject Describe()
        {
            lock (gate)
            {
                Trim();
                return new JObject { ["retainedResults"] = entries.Count, ["compressedBytes"] = retainedBytes,
                    ["uncompressedJsonBytes"] = retainedJsonBytes, ["budgetBytes"] = budget, ["maximumAgeSeconds"] = lifetime.TotalSeconds,
                    ["expiredByAge"] = ageExpirations, ["expiredByCapacity"] = capacityExpirations, ["oversizedResults"] = oversized,
                    ["meaning"] = "Completed result payloads only; oldest completion expires at 15 minutes or capacity. In-flight packing/HTTP buffers and compact lifetime request-id records are outside this budget. Expiration never reruns an operation." };
            }
        }
    }

    internal sealed class Job
    {
        public string Id, Key, Signature, State = "queued";
        public JObject Input;
        public OperationResults Results;
        public DateTime Created = DateTime.UtcNow;
        public bool CancelRequested;
        public readonly object Sync = new object();
        private DateTime? completed;
        private string missingReason;
        public void Complete(JObject result)
        {
            string reason = null;
            // A cache failure happens after execution, and must not strand a
            // running job or turn a retry into another mutation.
            try { if (!Results.Save(Id, result)) reason = "single_result_exceeds_capacity"; }
            catch (Exception) { reason = "retention_failed"; }
            lock (Sync)
            {
                Input = null;
                State = result.Value<bool>("success") ? "succeeded" : ((string)result["error"]?["code"] == "cancelled" ? "cancelled" : "failed");
                completed = DateTime.UtcNow; missingReason = reason;
            }
        }
        public JObject View()
        {
            lock (Sync)
            {
                string json = completed.HasValue ? Results.Read(Id) : null;
                var view = new JObject { ["operationId"] = Id, ["state"] = completed.HasValue && json == null ? "result_expired" : State,
                    ["createdAt"] = Created.ToString("o"), ["result"] = json == null ? null : new JRaw(json) };
                if (completed.HasValue)
                {
                    view["completedAt"] = completed.Value.ToString("o"); view["completionState"] = State;
                    view["resultRetention"] = json != null ? "available" : (missingReason ?? "age_or_capacity_limit");
                }
                return view;
            }
        }
    }
}
