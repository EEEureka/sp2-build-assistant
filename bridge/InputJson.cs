using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // JSON has strings, not date tokens. Keep exact timestamp guards and user text.
    public static class InputJson
    {
        public static JObject Parse(string body)
        {
            var input = JsonConvert.DeserializeObject<JObject>(body, new JsonSerializerSettings
            {
                DateParseHandling = DateParseHandling.None,
                CheckAdditionalContent = true
            });
            if (input == null) throw new JsonReaderException("Expected a JSON object.");
            return input;
        }
    }
}
