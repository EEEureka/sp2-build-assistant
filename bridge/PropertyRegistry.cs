using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Design.PartProperties.Attributes;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // Discover UI data, native metadata and serialized state independently. Missing
    // overload metadata must never conceal a native UI field or imply read-only.
    internal sealed class PropertyEntry
    {
        internal string Id,Family,MemberName,Unit="native_unspecified",Frame="not_applicable",Condition;
        internal PartModifierData Modifier;
        internal MemberInfo Member;
        internal DesignerPropertyAttribute Attribute;
        internal Type ValueType;
        internal double Min=-double.MaxValue,Max=double.MaxValue;
        internal bool Writable,Derived;
        internal JArray Choices;
        internal object RawValue(){return Member is FieldInfo?((FieldInfo)Member).GetValue(Modifier):((PropertyInfo)Member).GetValue(Modifier,null);}
        internal JObject Describe(bool live)
        {
            var o=new JObject{["propertyId"]=Id,["family"]=Family,["nativeMember"]=MemberName,["type"]=PropertyValues.TypeName(ValueType),["nativeType"]=ValueType.FullName,
                ["label"]=Attribute?.Label??MemberName,["description"]=Attribute?.Tooltip,["unit"]=Unit,["frame"]=Frame,
                ["source"]="native_designer_attribute_and_registered_adapter",["valueSource"]=live?"live_modifier":"isolated_template_modifier",
                ["editability"]=Writable?"conditional":Derived?"readOnly":"unsupported",["writeOperation"]=Writable?"properties.set":null,
                ["condition"]=Condition??(Writable?"Check currentCondition, native limits and referenced resources before applying.":null),
                ["verification"]=Writable?"representative_adapter_cases_only":"outside_typed_write_matrix",["acceptsExpression"]=false,
                ["refresh"]=Writable?new JArray("native_setter_callback","geometry_settle","collider","editorPicking"):new JArray()};
            try{o["value"]=PropertyValues.Read(RawValue());o["valueAvailable"]=true;}catch(Exception e){o["value"]=null;o["valueAvailable"]=false;o["valueError"]=e.GetBaseException().Message;}
            if(Writable)o["currentCondition"]=NativePropertyAdapter.CurrentCondition(this,live);
            if(ValueType.IsEnum)o["enumValues"]=new JArray(Enum.GetNames(ValueType));else if(Choices!=null)o["enumValues"]=Choices.DeepClone();
            if(Min!=-double.MaxValue||Max!=double.MaxValue)o["limits"]=new JObject{["min"]=Min==-double.MaxValue?(JToken)null:Min,["max"]=Max==double.MaxValue?(JToken)null:Max,["source"]="native_ui_and_adapter"};
            if(Attribute is DesignerPropertyButtonAttribute||Attribute is DesignerPropertyLabelAttribute){o["editability"]="readOnly";o["reason"]="Native action/display field, not a configuration value.";}
            return o;
        }
    }
    internal static class PropertyRegistry
    {
        internal const string Version="0.5.0";
        internal static IEnumerable<PropertyEntry> Entries(PartData part)
        {
            var counts=new Dictionary<Type,int>();
            foreach(var modifier in part.Modifiers){
                var concrete=modifier.GetType();int index;counts.TryGetValue(concrete,out index);counts[concrete]=index+1;
                string family=concrete.Name.EndsWith("Data")?concrete.Name.Substring(0,concrete.Name.Length-4):concrete.Name;
                var names=new HashSet<string>();
                for(Type type=concrete;type!=null&&typeof(PartModifierData).IsAssignableFrom(type);type=type.BaseType)
                    foreach(var member in type.GetMembers(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.DeclaredOnly)){
                        if(!(member is FieldInfo)&&!(member is PropertyInfo))continue;
                        var attr=member.GetCustomAttributes(typeof(DesignerPropertyAttribute),false).Cast<DesignerPropertyAttribute>().FirstOrDefault();
                        if(attr==null||!names.Add(member.Name))continue;
                        var fieldType=member is FieldInfo?((FieldInfo)member).FieldType:((PropertyInfo)member).PropertyType;
                        var e=new PropertyEntry{Id=family+"["+index+"]."+member.Name.TrimStart('_'),Family=family,Modifier=modifier,Member=member,MemberName=member.Name,Attribute=attr,ValueType=fieldType};
                        if(attr is DesignerPropertySpinnerAttribute){var x=(DesignerPropertySpinnerAttribute)attr;e.Min=(double)x.MinValue;e.Max=(double)x.MaxValue;}
                        if(attr is DesignerPropertySliderAttribute){var x=(DesignerPropertySliderAttribute)attr;e.Min=x.MinValue;e.Max=x.MaxValue;}
                        if(attr is DesignerPropertyVectorAttribute){var x=(DesignerPropertyVectorAttribute)attr;e.Min=(double)x.MinValue;e.Max=(double)x.MaxValue;}
                        NativePropertyAdapter.Configure(e);yield return e;
                    }
                foreach(var entry in NativePropertyAdapter.Extras(modifier,family,index))yield return entry;
            }
        }
        internal static JArray Describe(PartData part,XElement xml,bool live)
        {
            var output=new JArray(Entries(part).Select(e=>e.Describe(live)));
            var metadata=part.GetOverloadMetadataLookup();
            foreach(var node in xml.DescendantsAndSelf()){
                string path=Path(xml,node);
                var attributes=new HashSet<string>(node.Attributes().Select(a=>a.Name.LocalName));
                if(metadata.ContainsKey(node.Name.LocalName))foreach(var m in metadata[node.Name.LocalName].Attributes)attributes.Add(m.Name);
                foreach(string name in attributes){
                    var m=metadata.ContainsKey(node.Name.LocalName)?metadata[node.Name.LocalName].Attributes.FirstOrDefault(x=>x.Name==name):null;
                    bool structural=new[]{"id","partType","symmetryId","symmetryDisabled","materials"}.Contains(name);
                    bool input=node.Name.LocalName=="InputController.State"&&new[]{"input","activationGroup","invert","min","max","zeroOnDeactivate","invertType"}.Contains(name);
                    output.Add(new JObject{["propertyId"]="xml:"+path+"@"+name,["family"]=node.Name.LocalName,["path"]=path,["attribute"]=name,
                        ["label"]=m?.Label??name,["description"]=m?.Tooltip,["source"]=m==null?"native_serialized_state":"native_overload_metadata",
                        ["value"]=(string)node.Attribute(name),["valueAvailable"]=node.Attribute(name)!=null,["defaultValue"]=m?.DefaultValue==null?null:JToken.FromObject(m.DefaultValue),
                        ["valueSource"]=node.Attribute(name)==null?"omitted_use_typed_effective_value":"serialized_value",
                        ["type"]="string",["nativeType"]=m?.DataType.ToString(),["unit"]="native_unspecified",["frame"]="see_native_field",["expressionMode"]=input&&name=="input"?"native_input_expression_compile_without_flight_evaluation":"not_declared_by_this_descriptor",
                        ["editability"]=structural?"readOnly":input?"editable":m==null?"unknown":m.IsReadOnly?"readOnly":"conditional",
                        ["writeOperation"]=structural?null:input||m!=null&&!m.IsReadOnly?"part.update":null,
                        ["condition"]=structural?"Structural references require dedicated operations.":m!=null&&!m.IsReadOnly?"part.update validates the native metadata and existing path; dynamic conditions are checked at apply.":null,
                        ["enumValues"]=m?.EnumValues==null?null:JToken.FromObject(m.EnumValues)});
                }
            }
            return output;
        }
        private static string Path(XElement root,XElement node)
        {
            if(root==node)return "Part";
            var segments=new Stack<string>();for(var p=node;p!=root;p=p.Parent){int i=p.ElementsBeforeSelf(p.Name).Count();segments.Push(p.Name.LocalName+"["+i+"]");}
            return string.Join("/",segments);
        }
    }
}
