from direct_build import Session,raw
s=Session('S12')
s.guard('craft.checkpoint.create',name='S12 before control variables')
s.check('No preexisting global setters',s.read('variables.list',flags=('--view','structured'))['setters']==[])
ops=[{'kind':'variable.add','variable':'BuildFlapCommand','function':'clamp(Flaps,0,1)','priority':0},{'kind':'variable.add','variable':'BuildBrakeCommand','function':'clamp(Brake,0,1)','priority':0},
     {'kind':'output.bind','partId':3,'modifier':'Cockpit.State','outputId':'Speed','variable':'BuildSpeed','priority':0},
     {'kind':'output.bind','partId':3,'modifier':'Cockpit.State','outputId':'PosY','variable':'BuildAltitude','priority':0}]
ops += [raw(i,input='BuildFlapCommand') for i in (17,18,19,20)]
ops += [{'kind':'part.update','partId':i,'changes':[{'path':'InputController.State[1]','attribute':'input','value':'BuildBrakeCommand'}]} for i in (21,22)]
s.apply(*ops,label='formal-control-variables')
variables=s.read('variables.list',flags=('--view','structured'));s.check('Two normalized global commands',[(r['variable'],r['function']) for r in variables['setters']]==[('BuildFlapCommand','clamp(Flaps,0,1)'),('BuildBrakeCommand','clamp(Brake,0,1)')])
def bindings(): return s.read('outputs.list',flags=('--part',3,'--view','structured'))['sources'][0]['modifiers'][0]['bindings']
b=bindings();s.check('Two native outputs bound to named variables',{x['variable'] for x in b}=={'BuildSpeed','BuildAltitude'})
formal=s.read('craft.snapshot');cp=s.guard('craft.checkpoint.create',name='S12 formal variables and output bindings')
s.apply({'kind':'variable.add','variable':'BuildProbeA','function':'0.25','priority':1},{'kind':'variable.add','variable':'BuildProbeB','function':'0.5','priority':2},{'kind':'variable.update','index':2,'function':'0.75'},{'kind':'variable.reorder','order':[3,2,0,1]},label='add-update-reorder-setters')
v=s.read('variables.list',flags=('--view','structured'))['setters'];s.check('Order lists old indices in desired new order',[r['variable'] for r in v]==['BuildProbeB','BuildProbeA','BuildFlapCommand','BuildBrakeCommand'] and v[1]['function']=='0.75')
s.apply({'kind':'variable.delete','index':1},{'kind':'variable.delete','index':0},{'kind':'output.update','partId':3,'modifier':'Cockpit.State','outputId':'Speed','variable':'BuildSpeedProbe'},label='delete-temporaries-rename-output')
s.check('Temporary setters explicitly deleted',len(s.read('variables.list',flags=('--view','structured'))['setters'])==2)
s.check('Output variable renamed',any(x['variable']=='BuildSpeedProbe' for x in bindings()))
before_unbind=s.read('craft.snapshot')
s.apply({'kind':'output.unbind','partId':3,'modifier':'Cockpit.State','outputId':'Speed'},label='unbind-output')
s.check('Unbinding removes exactly one binding',len(bindings())==1)
s.read('craft.history');s.guard('craft.undo')
s.check('Native undo restores exact prior fingerprint',s.read('craft.snapshot')['identity']['fingerprint']==before_unbind['identity']['fingerprint'])
s.guard('craft.rollback',checkpointId=cp['id']);s.check('Checkpoint restores formal variables and names',s.read('craft.snapshot')['identity']['fingerprint']==formal['identity']['fingerprint'])
bad=s.apply({'kind':'variable.add','variable':'BuildInvalidProbe','function':'clamp('},require=False,label='invalid-global-expression')
s.check('Invalid setter rejected and recovered',not bad['success'] and bad['rollbackResult']['restored'])
s.check('No malformed setter residual',s.read('craft.snapshot')['identity']['fingerprint']==formal['identity']['fingerprint'])
s.read('variables.list',flags=('--view','structured'));s.read('outputs.list',flags=('--part',3,'--view','structured'))
print('S12 configuration tests complete; no telemetry evaluated')
