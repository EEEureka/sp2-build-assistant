from direct_build import Session
s=Session('S13-runtime')
formal=s.read('craft.snapshot',{'includeXml':True});cp=s.guard('craft.checkpoint.create',name='S13 full formal thirty-part design')
r=s.apply({'kind':'part.add','templateId':'tpl-f748657136c8ca1a','temporaryId':'tempBody','position':[20,2.5,0]},{'kind':'shape.update','partId':'tempBody','patch':{'length':1,'autoResize':False}},label='isolated-refresh-probe')['data'];body=r['temporaryIds']['tempBody']
def hits():return s.read('designer.raycast',{'origin':[20,6,1.5],'direction':[0,-1,0],'distance':8})['hits']
s.check('Ray misses short body',not any(x['partId']==body for x in hits()))
s.apply({'kind':'shape.update','partId':body,'patch':{'length':4}},label='extend-body-four-metres')
g=s.read('parts.geometry',flags=('--id',body))['geometry']
s.check('Render and editor bounds both extended',any(r['bounds']['size'][2]>3.99 for r in g['renderers']) and any(r['bounds']['size'][2]>3.99 for r in g['editorColliders']))
s.check('Ray hits newly extended area',any(x['partId']==body for x in hits()))
s.apply({'kind':'shape.update','partId':body,'patch':{'length':1}},label='shrink-body')
s.check('Old selectable area removed',not any(x['partId']==body for x in hits()))
r=s.apply({'kind':'part.delete','partId':body},{'kind':'part.add','templateId':'tpl-f748657136c8ca1a','temporaryId':'replacement','position':[20,2.5,0]},label='delete-and-reuse-id')['data']
replacement=r['temporaryIds']['replacement'];s.check('ID reuse explicitly reported',bool(r['reusedPartIds']) and replacement==body)
r=s.apply({'kind':'part.add','templateId':'tpl-97190f079a25a6e4','temporaryId':'tempWing','position':[21,2.5,0]},
          {'kind':'wing.control.add','wingPartId':'tempWing','style':'StandardFlap','temporaryId':'tempFlap','patch':{'spanRange':[.1,.9],'chordFraction':[.2,.2]}},
          {'kind':'wing.control.add','wingPartId':'tempWing','style':'Slat','temporaryId':'tempSlat','patch':{'spanRange':[.1,.9],'chordFraction':[.1,.1]}},
          {'kind':'connection.connect','partA':'tempWing','partB':replacement,'attachPointA':0,'attachPointB':6},label='bounded-assembly-probe')['data']
ids=r['temporaryIds'];scope=s.read('parts.assembly',flags=('--id',ids['tempWing']))['assembly']
s.check('Assembly includes owned controls, excludes external fuselage',set(scope['memberPartIds'])==set(ids.values()) and replacement not in scope['memberPartIds'] and bool(scope['externalConnections']))
r=s.apply({'kind':'part.delete','partId':ids['tempWing'],'assembly':True},label='delete-native-assembly')['data']
s.check('Deletion reports exact owned member set',set(r['actualChanges'][0]['deletedPartIds'])==set(ids.values()))
snapshot=s.read('craft.snapshot');s.check('Independent host retained',replacement in {p['id'] for p in snapshot['parts']} and len(snapshot['parts'])==31)
s.guard('craft.rollback',checkpointId=cp['id'])
end=s.read('craft.snapshot',{'includeXml':True});s.check('Formal thirty-part design restored exactly',len(end['parts'])==30 and end['identity']['fingerprint']==formal['identity']['fingerprint'])
s.guard('craft.checkpoint.create',name='Completed direct build before 0.4.9 readout patch')
s.read('connections.list',flags=('--view','structured'));s.read('symmetry.get');s.read('variables.list',flags=('--view','structured'));s.read('outputs.list',flags=('--view','structured'))
centers=s.read('craft.centers',{'images':True,'detail':'contributors','limit':50},flags=('--output-dir',str((s.path/'centers').resolve())))
print('CENTER IMAGES',centers.get('visual',{}).get('recommendedImages'))
print('FINAL',end['identity'],centers['centers'])
