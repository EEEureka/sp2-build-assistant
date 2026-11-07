"""Public lifecycle example, run through sp2model with a persistent --project.

Read Modeling-Workflow.md before adapting. Default action is resume (read only).
Write actions require apply:true. Never rerun build to recover an unknown result.
The toy contract covers declared geometry only, not whole-vehicle acceptance.
"""
from pathlib import Path
from sp2model import Section,ModelingError

action=task_parameters.get('action','resume')
path=Path(task_parameters['task_path']).resolve()
write=action in ('build','save','reopen','keep_best','restore')
if write and task_parameters.get('apply') is not True:
    raise ModelingError('apply_required','Review this action and explicitly set apply:true')
if action=='build':
    if path.exists():raise ModelingError('task_exists','Resume the original task, inspect its outcome and build a separate reviewed correction plan')
    task=session.task(path,name='Square housing',intent='1 m square, 2 m long; centred at (0,3,0) metres',
        max_candidates=task_parameters.get('max_candidates',8),max_iterations=task_parameters.get('max_iterations',12),
        max_native_operations=task_parameters.get('max_native_operations',800))
    task.reference('oral',kind='verbal',source='1 m square housing, 2 m long, centre (0,3,0)',subject='housing')
    task.component('shell',intent='closed square housing',strategy='one native Body')
    for id,axis,value in [('width',(1,0,0),1),('height',(0,1,0),1),('length',(0,0,1),2)]:
        task.extent(id,component='shell',reference_id='oral',axis=axis,value_m=value)
    points=[(-.5,2.5,0),(.5,2.5,0),(.5,3.5,0),(-.5,3.5,0)]
    task.contour('mid-profile',component='shell',reference_id='oral',origin=(0,3,0),normal=(0,0,1),segments=[(points[i],points[(i+1)%4]) for i in range(4)])
    task.pose('installation',component='shell',reference_id='oral',position_m=(0,3,0))
    task.freeze();task.candidate('body-a',components=['shell'],strategy='one native Body',part_budget=1)
    plan=session.plan(writable=[])
    plan.body('housing',(0,3,-1),(0,3,1),[Section(1,1),Section(1,1)])
    receipt=task.apply('body-a',plan)
    task.bind('body-a','shell',[receipt.objects['housing']])
    result=task.check('body-a')
else:
    task=session.task(path)
    if action=='resume':result=task.resume()
    elif action=='check':result=task.check('body-a')
    elif action=='rebind':result=task.rebind('body-a',from_best=task_parameters.get('from_best',False))
    elif action=='save':result=task.save(task_parameters['save_name'],overwrite=task_parameters.get('overwrite',False))
    elif action=='reopen':
        task=task.reopen(task_parameters['craft_id'],discard_current=task_parameters.get('discard_current',False))
        result=task.report()  # bindings and measurements intentionally stay stale
    elif action=='keep_best':result=task.keep_best('body-a')
    elif action=='restore_preview':result=task.restore_preview()
    elif action=='restore':result=task.restore(task_parameters['review_token'],accept_whole_craft=task_parameters.get('accept_whole_craft',False))
    else:raise ModelingError('invalid_action','Choose a documented lifecycle action')
