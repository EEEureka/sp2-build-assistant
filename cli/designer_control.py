"""Contracts for native scene and selection control without desktop input."""
def input_schema():
    return {'type':'object','additionalProperties':False,
        'properties':{'action':{'enum':['enter','load','select','menu','quit']},
            'expectedScene':{'enum':['MainMenu','Designer']},'requestId':{'type':'string','minLength':1},
            'craftSessionId':{'type':'string'},'expectedRevision':{'type':'integer','minimum':0},
            'expectedCraftName':{'type':'string'},'discardCurrent':{'type':'boolean'},
            'craftId':{'type':'string','minLength':1},'partId':{'type':'integer','minimum':0},'clear':{'type':'boolean'}},
        'required':['action','expectedScene','requestId'],
        'allOf':[
            {'if':{'properties':{'expectedScene':{'const':'Designer'}}},
             'then':{'required':['craftSessionId','expectedRevision','expectedCraftName']}},
            {'if':{'properties':{'action':{'enum':['load','menu','quit']},'expectedScene':{'const':'Designer'}}},
             'then':{'required':['discardCurrent'],'properties':{'discardCurrent':{'const':True}}}},
            {'if':{'properties':{'action':{'const':'load'}}},'then':{'required':['craftId']},'else':{'not':{'required':['craftId']}}},
            {'if':{'properties':{'action':{'const':'select'}}},
             'then':{'oneOf':[{'required':['partId'],'not':{'required':['clear']}},
                              {'required':['clear'],'properties':{'clear':{'const':True}},'not':{'required':['partId']}}]},
             'else':{'not':{'anyOf':[{'required':['clear']},{'required':['partId']}]}}},
            {'if':{'properties':{'action':{'enum':['load','select','menu']}}},'then':{'properties':{'expectedScene':{'const':'Designer'}}}},
            {'if':{'properties':{'action':{'const':'enter'}}},'then':{'properties':{'expectedScene':{'const':'MainMenu'}}}}],
        'description':'Native game APIs, not desktop input. Switching/closing explicitly discards the current in-memory craft; save desired edits first. Session checkpoints do not survive loading.'}

def output_data_schema():
    return {'type':'object','required':['action','scene','desktopInputUsed'],
        'properties':{'action':{'enum':['enter','load','select','menu','quit']},'scene':{'type':'string'},
            'desktopInputUsed':{'const':False},'identity':{'anyOf':[{'$ref':'#/$defs/Identity'},{'type':'null'}]},
            'craftName':{'type':['string','null']},'selectedPartId':{'type':['integer','null']},
            'sessionChanged':{'type':'boolean'},'saved':{'const':False},'shutdownScheduled':{'type':'boolean'},'meaning':{'type':'string'}}}
