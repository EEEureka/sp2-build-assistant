"""Independent XML field audit. No plugin comparator code is imported."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

def fields(node,path="Aircraft"):
    result={path+"/@"+k:v for k,v in node.attrib.items()}
    if node.text and node.text.strip(): result[path+"/#text"]=node.text
    counter={}
    for child in node:
        i=counter.get(child.tag,0); counter[child.tag]=i+1
        suffix="id="+child.attrib["id"] if child.tag=="Part" and "id" in child.attrib else str(i)
        result.update(fields(child,path+"/"+child.tag+"["+suffix+"]"))
    return result

def compare(left,right):
    a=fields(ET.fromstring(left)); b=fields(ET.fromstring(right))
    return [{"path":p,"before":a.get(p),"after":b.get(p)} for p in sorted(a.keys()|b.keys()) if a.get(p)!=b.get(p)]

if __name__=="__main__":
    a,b=[json.loads(Path(p).read_text(encoding="utf-8-sig"))["data"]["xml"] for p in sys.argv[1:3]]
    diffs=compare(a,b)
    if len(sys.argv)>3: Path(sys.argv[3]).write_text(json.dumps(diffs,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"count":len(diffs),"differences":diffs[:80]},ensure_ascii=False,indent=2))
