using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Xml.Linq;

namespace SP2BuildAssistant
{
    // 0.7.9 adds craftXmlVersion to the native modifier restore API. Resolve
    // signatures at runtime so the bridge can still run with 0.7.8 assemblies.
    internal static class NativeModifierState
    {
        private sealed class RestoreMethod
        {
            internal MethodInfo Method;
            internal bool TakesVersion;
        }
        private static readonly Dictionary<Type, RestoreMethod> Methods = new Dictionary<Type, RestoreMethod>();

        private static RestoreMethod Resolve(Type type)
        {
            if (type == null) throw new ArgumentNullException(nameof(type));
            lock (Methods)
            {
                RestoreMethod cached;
                if (Methods.TryGetValue(type, out cached)) return cached;
                const BindingFlags flags = BindingFlags.Public | BindingFlags.Instance;
                var method = type.GetMethod("RestoreFromState", flags, null, new[] { typeof(XElement), typeof(int) }, null);
                bool takesVersion = method != null;
                if (method == null) method = type.GetMethod("RestoreFromState", flags, null, new[] { typeof(XElement) }, null);
                if (method == null || method.ReturnType != typeof(void) || method.ContainsGenericParameters)
                    throw new MissingMethodException(type.FullName, "RestoreFromState(XElement, int) or RestoreFromState(XElement)");
                cached = new RestoreMethod { Method = method, TakesVersion = takesVersion };
                Methods.Add(type, cached);
                return cached;
            }
        }

        internal static void Validate(Type type) { Resolve(type); }

        internal static void Restore(object modifier, XElement state, int craftXmlVersion)
        {
            if (modifier == null) throw new ArgumentNullException(nameof(modifier));
            if (state == null) throw new ArgumentNullException(nameof(state));
            if (craftXmlVersion < 0) throw new ArgumentOutOfRangeException(nameof(craftXmlVersion));
            var restore = Resolve(modifier.GetType());
            try
            {
                restore.Method.Invoke(modifier, restore.TakesVersion ? new object[] { state, craftXmlVersion } : new object[] { state });
            }
            catch (TargetInvocationException error)
            {
                if (error.InnerException != null) ExceptionDispatchInfo.Capture(error.InnerException).Throw();
                throw;
            }
        }
    }
}
