"""Enumerate the entire live catalog through the globally installed CLI."""
import json
import sys
from precision_acceptance import Run
run=Run(sys.argv[1] if len(sys.argv)>1 else "dev3-catalog")
before=run.call("before","craft.snapshot",{"includeXml":True})["data"]
entries=[];offset=0
while True:
    page=run.call("catalog-"+str(offset),"catalog.list",{"offset":offset,"limit":200})["data"]["listing"]
    entries.extend(page["items"]);offset+=len(page["items"])
    if offset>=page["total"]:break
    if not page["items"]:raise RuntimeError("Catalog pagination stalled.")
coverage=[]
for i,e in enumerate(entries):
    result=run.call(f"template-{i:03}","properties.describe",{"templateId":e["id"],"limit":1000})
    run.check("template "+e["id"],result.get("success"),result.get("error"))
    coverage.append({"template":e,"success":result.get("success"),"parts":result.get("data",{}).get("parts"),"error":result.get("error")})
(run.root/"coverage.json").write_text(json.dumps({"gameVersion":before["identity"]["gameVersion"],"templateCount":len(entries),"entries":coverage,"releaseStatus":"discovery_audit_not_adapter_certification"},ensure_ascii=False,indent=2),encoding="utf-8")
after=run.call("after","craft.snapshot",{"includeXml":True})["data"]
run.check("catalog discovery never mutates current craft",after["identity"]["fingerprint"]==before["identity"]["fingerprint"])
