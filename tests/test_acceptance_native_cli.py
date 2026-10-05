import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'cli'))
import acceptance_contracts
import contracts
try:
    import jsonschema
except ImportError:
    jsonschema = None
spec = importlib.util.spec_from_file_location('native_cli', Path(__file__).parents[1] / 'cli/sp2build.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

class NativeAcceptanceContractTests(unittest.TestCase):
    def setUp(self):
        self.base = {'craftSessionId': 'session', 'expectedRevision': 1,
            'requestId': 'request', 'expectedCraftName': 'SP2Build 050 Precision Lab F2'}

    @unittest.skipIf(jsonschema is None, 'Optional schema validation requires jsonschema (tests/.deps).')
    def test_schema_rejects_player_craft_and_ambiguous_actions(self):
        schema = acceptance_contracts.input_schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        for action in ('undo', 'redo', 'reload'):
            jsonschema.validate({**self.base, 'action': action}, schema)
        invalid = [
            {**self.base, 'action': 'reload', 'expectedCraftName': 'VLS128s'},
            {**self.base, 'action': 'reload', 'partId': 1},
            {**self.base, 'action': 'inspect', 'partId': 1, 'modifierType': 'PistonData', 'value': 1},
            {**self.base, 'action': 'property', 'partId': 1, 'modifierType': 'PistonData', 'member': '_range'},
            {**self.base, 'action': 'load-file', 'path': 'another.xml'},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(payload, schema)

    @unittest.skipIf(jsonschema is None, 'Optional schema validation requires jsonschema (tests/.deps).')
    def test_output_schema_resolves_shared_definitions(self):
        schema = contracts.output_schema('acceptance.native')
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertIn('DesignerSceneIntegrity', schema['$defs'])
        self.assertIn('Identity', schema['$defs'])
        jsonschema.validate({'success': False, 'schemaVersion': '1',
            'error': {'code': 'acceptance_build_required', 'message': 'disabled'}}, schema)

    def test_shipping_or_older_bridge_never_receives_native_mutation(self):
        for data in ({}, {'acceptanceNative': {'available': False}}):
            with patch.object(cli, 'select_instance', return_value={'pid': 1}), \
                 patch.object(cli, 'load_args', return_value={**self.base, 'action': 'reload'}), \
                 patch.object(cli, 'http', return_value={'operationId': 'probe'}) as http, \
                 patch.object(cli, 'wait', return_value={'success': True, 'data': data}):
                with self.assertRaises(cli.CliError) as error:
                    cli.execute(['acceptance', 'native'])
                self.assertEqual(error.exception.code, 'acceptance_build_required')
                self.assertEqual(http.call_count, 1)
                self.assertEqual(http.call_args.args[2]['command'], 'designer.status')

    def test_enabled_bridge_preserves_request_id_and_guards(self):
        payload = {**self.base, 'action': 'undo'}
        with patch.object(cli, 'select_instance', return_value={'pid': 1}), \
             patch.object(cli, 'load_args', return_value=payload), \
             patch.object(cli, 'http', side_effect=[{'operationId': 'probe'}, {'operationId': 'native'}]) as http, \
             patch.object(cli, 'wait', side_effect=[{'success': True, 'data': {'acceptanceNative': {'available': True}}}, {'success': True, 'data': {}}]), \
             patch.object(cli, 'visual_download', side_effect=lambda instance, result, options: result):
            cli.execute(['acceptance', 'native'])
            sent = http.call_args.args[2]
            self.assertEqual(sent['command'], 'acceptance.native')
            self.assertEqual(sent['requestId'], self.base['requestId'])
            self.assertEqual(sent['args']['craftSessionId'], self.base['craftSessionId'])
            self.assertEqual(sent['args']['expectedRevision'], 1)

    def test_primitive_cli_values_and_global_request_id(self):
        args = cli.load_args('acceptance.native', {'action': 'property',
            'craft-session-id': 'session', 'expected-revision': '1', 'request-id': 'request',
            'expected-craft-name': 'SP2Build 050 Precision Lab F2', 'part-id': '12',
            'modifier-type': 'PistonData', 'member': '_cycle', 'value': 'true'})
        self.assertIs(args['value'], True)
        self.assertEqual(args['partId'], 12)

    @unittest.skipIf(jsonschema is None, 'Optional schema validation requires jsonschema (tests/.deps).')
    def test_complex_native_references_do_not_mix_actions(self):
        schema=acceptance_contracts.input_schema()
        generic={**self.base,'action':'property','partId':2,'modifierType':'GearBayData','member':'_hingeAxisPose'}
        jsonschema.validate({**generic,'value':{'position':[0,0,0],'rotationQuaternion':[0,0,0,1]}},schema)
        overload={**self.base,'action':'overload','partId':2,'element':'Piston.State','attribute':'preventBreaking','value':'true'}
        jsonschema.validate(overload,schema)
        for bad in ({**generic,'element':'Piston.State','value':1}, {**overload,'modifierType':'PistonData'}, {**overload,'element':'Part'}):
            with self.subTest(payload=bad),self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)

if __name__ == '__main__':
    unittest.main()
