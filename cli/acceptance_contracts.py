"""Development-only native reference path, never an ordinary editing shortcut."""
def input_schema():
    common = ['craftSessionId', 'expectedRevision', 'expectedCraftName', 'requestId', 'action']
    return {'type': 'object', 'additionalProperties': False,
        'description': 'Test-only dev17+ acceptance build and the exact currently open precision lab required. No desktop input. Native callback evidence does not certify UI pointer interactions.',
        'properties': {
            'craftSessionId': {'type': 'string'}, 'expectedRevision': {'type': 'integer', 'minimum': 0},
            'expectedCraftName': {'type': 'string', 'pattern': '^SP2Build 050 Precision Lab'},
            'requestId': {'type': 'string', 'minLength': 1},
            'action': {'enum': ['inspect', 'undo', 'redo', 'reload', 'property', 'overload']},
            'partId': {'type': 'integer'}, 'modifierType': {'type': 'string'},
            'modifierIndex': {'type': 'integer', 'minimum': 0}, 'member': {'type': 'string'},
            'element': {'enum': ['Piston.State', 'GearLeg.State', 'JetEngineShroud.State']}, 'attribute': {'type':'string'},
            'value': {'type': ['boolean', 'string', 'number', 'array', 'object']}},
        'required': common,
        'allOf': [{'if': {'properties': {'action': {'not': {'const':'overload'}}}},
                   'then': {'not': {'anyOf':[{'required':['element']},{'required':['attribute']}]}}}],
        'oneOf': [
            {'properties': {'action': {'const':'overload'}, 'value': {'type':'string'}}, 'required':['partId','element','attribute','value'],
             'not': {'anyOf':[{'required':[k]} for k in ('modifierType','modifierIndex','member')]}},
            {'properties': {'action': {'const': 'inspect'}}, 'required': ['partId', 'modifierType'],
             'not': {'anyOf': [{'required': ['member']}, {'required': ['value']}]}},
            {'properties': {'action': {'const': 'property'}}, 'required': ['partId', 'modifierType', 'member', 'value']},
            {'properties': {'action': {'enum': ['undo', 'redo', 'reload']}},
             'not': {'anyOf': [{'required': [key]} for key in ('partId', 'modifierType', 'modifierIndex', 'member', 'value')]}}]}

def output_data_schema():
    scalar = {'type': ['boolean', 'string', 'number', 'array', 'object', 'null']}
    return {'type': 'object', 'required': ['identity', 'action', 'desktopInputUsed', 'evidenceSource'],
        'properties': {'identity': {'$ref': '#/$defs/Identity'},
            'action': {'enum': ['inspect', 'undo', 'redo', 'reload', 'property', 'overload']},
            'desktopInputUsed': {'const': False},
            'evidenceSource': {'enum': ['native_declarations_not_desktop_ui', 'native_api_callback_not_desktop_ui', 'native_ui_controls_api_not_desktop_input', 'native_overload_panel_api_not_desktop_input']},
            'beforeFingerprint': {'type': 'string'}, 'sessionChanged': {'type': 'boolean'},
            'beforeValue': scalar, 'effectiveValue': scalar,
            'controls': {'type': 'array', 'items': {'type': 'object',
                'required': ['member', 'controlType', 'nativeType', 'visible', 'value', 'referenceSetterSupported'],
                'properties': {'member': {'type': 'string'}, 'controlType': {'type': 'string'},
                    'nativeType': {'type': 'string'}, 'label': {'type': 'string'}, 'visible': {'type': 'boolean'},
                    'value': scalar, 'referenceSetterSupported': {'type': 'boolean'}}}},
            'changes': {'type': 'object', 'required': ['totalChanges', 'truncated', 'comparison', 'changes'],
                'properties': {'totalChanges': {'type': 'integer'}, 'truncated': {'type': 'boolean'},
                    'comparison': {'type': 'string'}, 'changes': {'type': 'array', 'items': {'type': 'object',
                        'required': ['path', 'before', 'after'], 'properties': {'path': {'type': 'string'},
                            'before': {'type': ['string', 'null']}, 'after': {'type': ['string', 'null']}}}}}},
            'sceneIntegrity': {'$ref': '#/$defs/DesignerSceneIntegrity'},
            'limitations': {'type': 'array', 'items': {'type': 'string'}}}}
