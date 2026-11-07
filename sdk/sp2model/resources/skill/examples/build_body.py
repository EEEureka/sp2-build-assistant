"""Run against an explicitly selected test craft; preview unless --apply."""
import argparse
import json
from sp2model import Session, Section

parser = argparse.ArgumentParser()
parser.add_argument("--instance", required=True, help="Exact game PID or instanceId")
parser.add_argument("--craft", required=True, help="Expected current craft name/session")
parser.add_argument("--apply", action="store_true")
parser.add_argument("--resume", help="Existing execution journal; never resubmits")
args = parser.parse_args()
session = Session.attach(instance=args.instance, craft=args.craft)
if args.resume:
    receipt = session.resume(args.resume)
    print(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2))
else:
    scene = session.inspect()
    plan = session.plan(frame=scene.craft_frame, writable=[])
    body = plan.body("main_body", (0,3,-3), (0,3,3), [Section(2,1),Section(1,.6)])
    plan.expect(body, length_m=6, tolerance_m=.002)
    preview = plan.preview()
    print(json.dumps({"plan":plan.to_dict(),"preview":preview.report},ensure_ascii=False,indent=2))
    if args.apply:
        receipt = plan.apply(preview.token)
        print(json.dumps({"receipt":receipt.to_dict(),"verification":session.verify(receipt)},ensure_ascii=False,indent=2))
