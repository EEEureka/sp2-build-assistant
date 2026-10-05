using System;
using Newtonsoft.Json.Linq;
using SP2BuildAssistant;
namespace SP2BuildAssistant { internal class ApiError : Exception { public string Code; public ApiError(string code,string message):base(message){Code=code;} } }
class InputControllerFieldsTests
{
    static int count;
    static void Check(string label,bool value){if(!value)throw new Exception(label);count++;}
    static bool Valid(string key,JToken value){return InputControllerFields.TryValidate("InputController.State",key,value);}
    static void Reject(string key,JToken value,string code){try{Valid(key,value);throw new Exception("Accepted invalid "+key);}catch(ApiError e){Check(key+" error",e.Code==code);}}
    static void Main()
    {
        Check("Aileron",Valid("input","Aileron")); Check("Expression",Valid("input","clamp(Roll, -1, 1)"));
        Check("Activation always",Valid("activationGroup","0")); Check("Activation eight",Valid("activationGroup","8"));
        Check("Activation expression",Valid("activationGroup","Brake > 0"));
        Check("Boolean",Valid("invert",true)); Check("String boolean",Valid("zeroOnDeactivate","false"));
        Check("Output invert",Valid("invertType","Output"));
        Check("Reversed min allowed",Valid("min",1.0)); Check("Reversed max allowed",Valid("max",-1.0));
        Check("String float",Valid("max","0.75"));
        Reject("input",null,"required_attribute"); Reject("input"," ","invalid_input_controller");
        Reject("input",new JArray("Roll"),"invalid_input_controller"); Reject("input",new string('x',4097),"invalid_input_controller");
        Reject("activationGroup","9","out_of_range"); Reject("activationGroup","-1","out_of_range");
        Reject("activationGroup","1.5","out_of_range"); Reject("activationGroup","1e0","out_of_range");
        Reject("invert",1,"invalid_boolean"); Reject("zeroOnDeactivate","yes","invalid_boolean");
        Reject("invertType","axis","invalid_enum"); Reject("max","NaN","invalid_number");
        Reject("min","Infinity","invalid_number"); Reject("max",1e100,"invalid_number");
        Reject("min",true,"invalid_number");
        Check("Unknown attribute remains unsupported",!Valid("unregistered","Roll"));
        Check("Other element remains unsupported",!InputControllerFields.TryValidate("Other.State","input","Roll"));
        Console.WriteLine("Input controller validation checks: "+count);
    }
}
