"""One task-level script, reusable Python construction, one explicit batch.

This demonstrates ordinary Python reuse, not a substitute for the SDK's copy/
array relationship operations. Preview by default; --params '{"apply":true}'
executes a new plan. Use the host resume command after an uncertain submission.
"""
from sp2model import Frame, Section

plan = session.plan(frame=Frame.world(), writable=[])


def beam(name, x):
    part = plan.body(name, (x, 3, -1), (x, 3, 1),
                     [Section(.5, .5), Section(.5, .5)])
    plan.expect(part, length_m=2, position_m=(x, 3, 0), tolerance_m=.002)
    return part


objects = [beam("beam_" + str(index), index * 2) for index in range(3)]
preview = plan.preview()
result = {"applied": False, "objectCount": len(objects), "preview": preview}
if task_parameters.get("apply") is True:
    receipt = plan.apply(preview.token)
    result = {"applied": True, "receipt": receipt, "verification": session.verify(receipt)}
