"""Live regression for creating controls before native connection callbacks run."""
import os
import argparse
import acceptance_v02 as a

c = a.c

def create(wing, style, start, end, name='cs', fraction=.2):
    return {'kind':'wing.control.add','wingPartId':wing,'style':style,'temporaryId':name,
            'patch':{'spanRange':[start,end],'chordFraction':[fraction,fraction]}}

def invalid_span(style):
    wing=a.add('JWing-1')
    span=c.read('shape.get',id=wing)['shape']['spanMetres']
    count=c.read('craft.snapshot')['partCount']
    response=a.bad(create(wing,style,.1*span,span+1))
    c.check('range rejected before native generation',response['error']['code']=='invalid_control_surface')
    c.check('failed add leaves no part',c.read('craft.snapshot')['partCount']==count)

def overlap_edges_and_resize():
    wing=a.add('JWing-1')
    span=c.read('shape.get',id=wing)['shape']['spanMetres']
    c.apply(create(wing,'StandardFlap',.1*span,.45*span,'first'))
    response=a.bad(create(wing,'FowlerFlap',.3*span,.6*span,'overlap'))
    c.check('overlap rejected explicitly',response['error']['code']=='control_surface_overlap')
    c.apply(create(wing,'Slat',.1*span,.45*span,'leading'))
    c.apply(create(wing,'BrakeFlap',.5*span,.9*span,'second'))
    c.check('three nonconflicting controls',len(c.read('shape.get',id=wing)['shape']['controlSurfaces'])==3)
    response=a.bad({'kind':'shape.update','partId':wing,'symmetric':False,'patch':{'sections':[{'index':1,'spanPosition':span*.5}]}})
    c.check('shrinking wing rejects stranded controls',response['rollbackResult']['restored'])
    c.check('wing size restored',abs(c.read('shape.get',id=wing)['shape']['spanMetres']-span)<.001)
    c.guarded('craft.undo')
    c.check('undo removes only last added control',len(c.read('shape.get',id=wing)['shape']['controlSurfaces'])==2)

def endpoints(style):
    wing=a.add('JWing-1')
    span=c.read('shape.get',id=wing)['shape']['spanMetres']
    result=c.apply(create(wing,style,0,span))
    part=result['temporaryIds']['cs']
    c.check('full span endpoints retained',a.shape(part)['spanRange']==[0,span])
    geometry=c.read('parts.geometry',id=part)['geometry']
    c.check('control has generated geometry',bool(geometry['renderers']) and bool(geometry['colliders']))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=('all','guards','overlap','endpoints'),default='all')
    selected=parser.parse_args().case
    c.check('exact patch build',c.read('designer.status')['buildId']==os.environ['SP2_ACCEPTANCE_BUILD_ID'])
    a.baseline=c.read('craft.snapshot',includeXml=True)
    a.selection=c.read('designer.selection')['selectedPartId']
    a.checkpoint=os.environ.get('SP2_ACCEPTANCE_CHECKPOINT')
    if a.checkpoint:
        c.read('craft.checkpoint.get',id=a.checkpoint)
    else:
        a.checkpoint=c.guarded('craft.checkpoint.create',name='Control creation regression baseline')['data']['id']
    a.entries=c.read('catalog.list',limit=1000)['listing']['items'];a.save()
    if selected in ('all','guards'):
        for style in ('StandardFlap','FowlerFlap','BrakeFlap','Slat'):
            a.case('invalid span '+style,lambda s=style:invalid_span(s),True)
    if selected in ('all','overlap'):
        a.case('control overlap opposite edges wing resize and undo',overlap_edges_and_resize,True)
    if selected in ('all','endpoints'):
        for style in ('StandardFlap','FowlerFlap','BrakeFlap','Slat'):
            a.case('full span geometry '+style,lambda s=style:endpoints(s),True)
    a.finish()

if __name__=='__main__':main()
