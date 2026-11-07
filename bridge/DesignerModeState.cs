namespace SP2BuildAssistant
{
    // Pure state decision shared by status and native navigation. Scene names
    // alone cannot distinguish flight from the in-flight designer.
    internal static class DesignerModeState
    {
        internal static bool Ready(string scene, bool designerActive, bool aircraftActive, bool flightDesignerActive, bool transitioning)
        {
            return !transitioning && designerActive && aircraftActive &&
                (scene == "Designer" || (scene == "Terrain" && flightDesignerActive));
        }
        internal static string Mode(string scene, bool ready)
        {
            return ready ? (scene == "Terrain" ? "flight" : "standalone") : "inactive";
        }
    }
}
