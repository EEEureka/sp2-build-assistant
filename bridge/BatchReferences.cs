using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // Logical lifetimes, independent of Unity objects: a native craft rebuild
    // replaces every object without replacing the logical parts or their IDs.
    internal sealed class BatchReferences
    {
        private Dictionary<int, JObject> current;
        private readonly Dictionary<int, int> generations = new Dictionary<int, int>();
        private readonly Dictionary<int, JObject> deleted = new Dictionary<int, JObject>();
        private readonly Dictionary<string, KeyValuePair<int, int>> bindings = new Dictionary<string, KeyValuePair<int, int>>();
        internal readonly JArray ReusedPartIds = new JArray();
        internal int OperationIndex;

        internal BatchReferences(IEnumerable<JObject> parts) { current = Map(parts); }
        private static Dictionary<int, JObject> Map(IEnumerable<JObject> parts)
        { return parts.ToDictionary(p => (int)p["id"], p => (JObject)p.DeepClone()); }
        private int Generation(int id) { return generations.TryGetValue(id, out int n) ? n : 0; }
        internal bool ContainsKey(string name) { return bindings.ContainsKey(name); }
        internal void Add(string name, int id)
        {
            if (ContainsKey(name)) throw new ApiError("duplicate_temporary_id", "Temporary IDs cannot be reused, including deleted bindings: " + name);
            bindings.Add(name, new KeyValuePair<int, int>(id, Generation(id)));
        }
        internal int this[string name] { get { return Resolve(new JValue(name)); } }
        internal int Resolve(JToken value)
        {
            if (value == null) return 0;
            if (value.Type == JTokenType.Integer)
            {
                int id = (int)value;
                if (deleted.ContainsKey(id)) throw new ApiError("stale_part_reference", "Part ID " + id + " was deleted earlier in this batch. Use the new part's temporaryId, not a recycled numeric ID.");
                return id;
            }
            if (value.Type != JTokenType.String) throw new ApiError("invalid_part_reference", "Use an integer part ID or a temporaryId string.");
            string name = (string)value;
            if (!bindings.TryGetValue(name, out var binding)) throw new ApiError("temporary_id_not_found", name);
            if (binding.Value != Generation(binding.Key)) throw new ApiError("deleted_temporary_reference", "Temporary ID " + name + " refers to a deleted part; it never follows recycled IDs.");
            return binding.Key;
        }
        internal int[] Observe(IEnumerable<JObject> parts)
        {
            var next = Map(parts);
            var removed = current.Keys.Except(next.Keys).OrderBy(x => x).ToArray();
            foreach (int id in removed)
            {
                generations[id] = Generation(id) + 1;
                deleted[id] = new JObject { ["previous"] = current[id], ["deletedAtOperationIndex"] = OperationIndex };
            }
            foreach (int id in next.Keys.Except(current.Keys).OrderBy(x => x))
                if (deleted.TryGetValue(id, out JObject prior))
                    ReusedPartIds.Add(new JObject { ["partId"] = id, ["previous"] = prior["previous"].DeepClone(),
                        ["current"] = next[id].DeepClone(), ["deletedAtOperationIndex"] = prior["deletedAtOperationIndex"],
                        ["createdAtOperationIndex"] = OperationIndex,
                        ["temporaryIds"] = new JArray(bindings.Where(b => b.Value.Key == id && b.Value.Value == Generation(id)).Select(b => b.Key)) });
            current = next;
            return removed;
        }
        internal bool WasDeleted(int id) { return deleted.ContainsKey(id); }
        internal void ReplaceLifetime(int id,JObject replacement,string temporary)
        {
            if(!current.ContainsKey(id))throw new ApiError("stale_part_reference","A replaced object must exist at this operation boundary.");
            var prior=current[id];generations[id]=Generation(id)+1;
            deleted[id]=new JObject{["previous"]=prior.DeepClone(),["deletedAtOperationIndex"]=OperationIndex};
            if(!string.IsNullOrEmpty(temporary))Add(temporary,id);
            ReusedPartIds.Add(new JObject{["partId"]=id,["previous"]=prior.DeepClone(),["current"]=replacement.DeepClone(),
                ["deletedAtOperationIndex"]=OperationIndex,["createdAtOperationIndex"]=OperationIndex,["temporaryIds"]=new JArray(bindings.Where(b=>b.Value.Key==id&&b.Value.Value==Generation(id)).Select(b=>b.Key))});
            current[id]=(JObject)replacement.DeepClone();
        }
        internal JObject LiveBindings { get { return new JObject(bindings.Where(b => b.Value.Value == Generation(b.Value.Key) && current.ContainsKey(b.Value.Key)).Select(b => new JProperty(b.Key, b.Value.Key))); } }
        internal JArray InvalidatedBindings { get { return new JArray(bindings.Where(b => b.Value.Value != Generation(b.Value.Key) || !current.ContainsKey(b.Value.Key)).Select(b => b.Key)); } }
    }
}
