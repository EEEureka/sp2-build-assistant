import importlib.util
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'cli'))
import designer_control
import contracts
import jsonschema
spec=importlib.util.spec_from_file_location('scene_cli',Path(__file__).parents[1]/'cli/sp2build.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)

class DesignerControlTests(unittest.TestCase):
    def test_schema_guards_discard_and_selection(self):
        schema=designer_control.input_schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        base={'action':'load','expectedScene':'Designer','craftSessionId':'s','expectedRevision':1,
            'expectedCraftName':'Lab','requestId':'r','craftId':'lab.xml','discardCurrent':True}
        jsonschema.validate(base,schema)
        for patch_value in ({'discardCurrent':False},{'discardCurrent':'true'},{'expectedScene':'MainMenu'},
                            {'partId':3},{'action':'select'},{'craftId':None}):
            with self.subTest(patch_value=patch_value),self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate({**base,**patch_value},schema)
        jsonschema.validate({'action':'enter','expectedScene':'MainMenu','requestId':'r'},schema)

    def test_older_bridge_is_not_sent_navigation(self):
        with patch.object(cli,'select_instance',return_value={'pid':1}),patch.object(cli,'load_args',return_value={}), \
             patch.object(cli,'http',return_value={'operationId':'probe'}) as http, \
             patch.object(cli,'wait',return_value={'success':True,'data':{}}):
            with self.assertRaises(cli.CliError) as exc:cli.execute(['designer','control'])
            self.assertEqual(exc.exception.code,'unsupported_bridge_feature')
            self.assertEqual(http.call_count,1)
            self.assertEqual(http.call_args.args[2]['command'],'designer.status')

    def test_commands_and_output_schemas_are_discoverable(self):
        for command in ('designer.control','designer.crafts'):
            self.assertIn(command,cli.command_names())
            schema=contracts.output_schema(command)
            self.assertIsNotNone(schema)
            jsonschema.Draft202012Validator.check_schema(schema)

    def test_cli_boolean_and_integer_flags(self):
        args=cli.load_args('designer.control',{'action':'select','expected-scene':'Designer','part-id':'3','request-id':'r'})
        self.assertEqual(args['partId'],3)
        with self.assertRaises(cli.CliError):cli.load_args('designer.control',{'action':'quit','expected-scene':'Designer','discard-current':'yes','request-id':'r'})

if __name__=='__main__':unittest.main()
