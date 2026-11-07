"""0.7.2 nested contracts; production CLI stays standard-library only."""
from copy import deepcopy

def obj(properties,required=(),**extra):return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False,**extra}
S={'type':'string','minLength':1};B={'type':'boolean'};I={'type':'integer','minimum':0}
IDS={'type':'array','items':I,'uniqueItems':True}
REF={'type':['integer','string'],'description':'Current native ID or earlier live temporary handle; never a reused deleted numeric ID'}
V={'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3,'description':'metres, explicit world coordinates'}

def enrich_loop(command,schema):
    result=deepcopy(schema);p=result['properties']
    if 'goals' in p:
        scope=obj({'partIds':IDS,'impactPartIds':IDS,'description':S})
        boundary=obj({'id':S,'partIds':IDS,'expected':S,'type':S},['id'])
        protected=obj({'partId':I,'path':{'type':'string','pattern':'^/','description':'JSON pointer into current native part snapshot'},'expected':{},'reason':S},['partId','path'])
        verification=obj({'requiredEvidenceKinds':{'type':'array','minItems':1,'items':S},'coverageMode':{'enum':['complete','finite_sampled'],'default':'complete'},
                          'limitationsAccepted':{'type':['string','object'],'description':'Required nonempty reason and source when finite_sampled is chosen'},'checkIds':{'type':'array','items':S}},
                         allOf=[{'if':{'properties':{'coverageMode':{'const':'finite_sampled'}},'required':['coverageMode']},'then':{'required':['limitationsAccepted']}}])
        goal=obj({'id':S,'expected':{'type':'string','minLength':1,'description':'Concrete expected outcome text. The actual key is expected, not expectedOutcome or outcome.'},
                  'partIds':IDS,'scope':scope,'boundaries':{'type':'array','items':boundary},'protectedFields':{'type':'array','items':protected},'verification':verification,
                  'channel':{'enum':['subject','impact']},'task':{'enum':['repair','inspect']},'priority':{'type':['string','number']}},['expected'],
                 anyOf=[{'required':['partIds'],'properties':{'partIds':{'minItems':1}}},
                        {'required':['scope'],'properties':{'scope':{'required':['partIds'],'properties':{'partIds':{'minItems':1}}}}},
                        {'required':['boundaries'],'properties':{'boundaries':{'contains':{'required':['partIds'],'properties':{'partIds':{'minItems':1}}}}}}])
        p['goals']={'type':'array','minItems':1,'items':goal}
    if command=='build.loop.init':
        result['required']=list(dict.fromkeys(result['required']+['userObjective','goals']))
        p['stagnationRounds']={'type':'integer','minimum':2,'default':3}
        p['completionRequirements']={'type':'array','items':{'enum':['visual','nativeSaved','userAestheticApproval']},'uniqueItems':True}
        result['examples']=[{'journalPath':'loop.jsonl','userObjective':'Restore the native hull contour','goals':[{'id':'hull','partIds':[1],'expected':'Complete side contour within the original 2 mm tolerance'}]},
            {'journalPath':'loop-with-boundary.jsonl','userObjective':'Revise one panel and preserve its seam','goals':[{'id':'panel','partIds':[1],'expected':'Specified panel section within 2 mm',
             'scope':{'partIds':[1],'impactPartIds':[2]},'boundaries':[{'id':'seam','partIds':[1,2],'expected':'Shared complete interface contour remains continuous'}],
             'protectedFields':[{'partId':2,'path':'/position'}],'verification':{'requiredEvidenceKinds':['native_mesh_measurement'],'coverageMode':'complete'}}]}]
    if 'snapshot' in p:
        identity=obj({'craftSessionId':S,'revision':I,'fingerprint':S,'stateUncertain':{'const':False}},['craftSessionId','revision'],description='Native sampling identity; stateUncertain must be false for modeling')
        identity['additionalProperties']=True
        part=obj({'id':I,'type':S,'name':{'type':'string'},'position':V,'rotationQuaternion':{'type':'array','items':{'type':'number'},'minItems':4,'maxItems':4}},['id'])
        part['additionalProperties']=True
        native=obj({'identity':identity,'parts':{'type':'array','items':part},'name':{'type':'string'},'xml':{'type':'string'}},['identity','parts']);native['additionalProperties']=True
        p['snapshot']={'anyOf':[S,native,obj({'success':{'const':True},'data':native},['data'])],
                       'description':'Native snapshot object (identity plus current parts), its success/data envelope, or a UTF-8 JSON file path. An identity object alone is not a snapshot. Omit to collect current native evidence.'}
    return result

def enrich(command,schema):
    result=deepcopy(schema);p=result['properties']
    if command in ('batch.preview','batch.apply'):
        p['modelScope']=obj({'version':{'const':'sp2model.scope/1'},'writablePartIds':IDS,'variableNames':{'type':'array','maxItems':512,'items':S},'paletteAppend':B},['version','writablePartIds'],description='Explicit current native write set; dependencies are candidates for review, never automatic permission to expand it')
    if command in ('native.state','mechanical.get','wing.stations'):result['required']=['id']+(['positions'] if command=='wing.stations' else [])
    if command=='wing.stations':p['positions']={'type':'array','minItems':1,'maxItems':256,'items':{'type':'number','minimum':0,'maximum':1000,'description':'Native span station metres; host span remains authoritative'}}
    if command=='mechanical.update':
        for key in ('startWorld','endWorld'):p[key]=V
        p['radiusMultiplier']={'type':'number','minimum':.5,'maximum':2,'description':'Native dimensionless radius UI multiplier'}
        result['required']=['kind','partId'];result['description']='Native visual JDriveShaft endpoints; connected endpoints remain fixed. Length is endpoint spacing, not object scale or a mesh certificate.'
    if command=='native.state' and 'changes' in p:
        change=obj({'action':{'enum':['set','remove','rename']},'path':S,'attribute':S,'value':{},'newName':S},['action','attribute'],
                   allOf=[{'if':{'properties':{'action':{'const':'set'}}},'then':{'required':['value']}},{'if':{'properties':{'action':{'const':'rename'}}},'then':{'required':['newName']}}])
        p['changes']={'type':'array','minItems':1,'maxItems':500,'items':change};result['required']=['kind','partId','changes']
    if command=='part.retype':result['required']=['kind','partId','partType','acceptConnectionLoss'];p['acceptConnectionLoss']={'const':True}
    if command=='craft.checkpoint.prune':
        p['ids']={'type':'array','minItems':1,'uniqueItems':True,'items':S};result['required']=['craftSessionId','expectedRevision','ids']
    if command=='parts.query':
        p['partIds']=IDS;p['fields']={'type':'array','minItems':1,'uniqueItems':True,'items':S};p['offset']=I;p['limit']={'type':'integer','minimum':1,'maximum':200,'default':50}
    if command=='model.dependencies':p['partIds']={**IDS,'minItems':1};result['required']=['craftSessionId','expectedRevision','partIds']
    if command=='airfoils.describe':
        p['anglesDegrees']={'type':'array','minItems':1,'maxItems':181,'items':{'type':'number','minimum':-180,'maximum':180}}
        p['reynolds']={'type':'number','minimum':1000,'maximum':1e9};p['mach']={'type':'number','minimum':0,'maximum':10}
        result['allOf']=[{'if':{'required':['anglesDegrees']},'then':{'required':['name','reynolds','mach']}}]
    return result
