using System;

namespace SP2BuildAssistant
{
    internal static class ReplacementLifetime
    {
        // Native AssignAircraft destroys the first child named Aircraft, which
        // may already be queued for destruction by an earlier swap this frame.
        internal static void Adopt(Action assign, Func<bool> outgoingIsCurrent,
            Action deactivateOutgoing, Action reactivateOutgoing, Action destroyOutgoing)
        {
            deactivateOutgoing();
            try { assign(); }
            catch
            {
                if (outgoingIsCurrent()) reactivateOutgoing();
                else destroyOutgoing();
                throw;
            }
            destroyOutgoing();
        }
    }
}
