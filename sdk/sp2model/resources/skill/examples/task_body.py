"""Run with: python -m sp2model run task_body.py --instance ... --craft ...

The host injects session and task_parameters. Preview is the default. To apply
this new plan, explicitly supply --params '{"apply":true}'. An uncertain prior
run must be recovered through the host's resume command, not by rerunning this.
"""
from sp2model import Frame, Section

plan = session.plan(frame=Frame.world(), length_unit="m", writable=[])
body = plan.body("task_body", (0, 3, -3), (0, 3, 3),
                 [Section(2, 1), Section(1, .6)])
plan.expect(body, length_m=6, position_m=(0, 3, 0), tolerance_m=.002)
preview = plan.preview()
result = {"applied": False, "preview": preview}
if task_parameters.get("apply") is True:
    receipt = plan.apply(preview.token)
    result = {"applied": True, "receipt": receipt, "verification": session.verify(receipt)}
