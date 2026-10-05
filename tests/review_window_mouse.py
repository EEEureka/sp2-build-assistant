"""Supplement mouse observations without changing the retained strict XML result."""
import json
from decimal import Decimal
from PIL import Image,ImageDraw
from precision_acceptance import ROOT
from precision_diff import compare

names=['dev15-window-mouse-edit','dev15-window-mouse-cli','dev15-window-mouse-native','dev15-window-mouse-restored']
def data(name,label):return json.loads((ROOT/name/(label+'.json')).read_text(encoding='utf-8-sig'))['data']
diffs=compare(data(names[1],'snapshot')['xml'],data(names[2],'snapshot')['xml'])
allowed={'Aircraft/Assembly[0]/Parts[0]/Part[id=6]/ProceduralWindow.State[0]/@'+n for n in ('lowerSpan','upperSpan')}
numeric=all(d['path'] in allowed and [Decimal(x) for x in d['before'].split(',')]==[Decimal(x) for x in d['after'].split(',')] for d in diffs)
selected=[data(n,'selection')['selectedPartId'] for n in names]
cameras=[data(n,'view')['repeatableViews'] for n in names]
canvas=Image.new('RGB',(1280,840),'white');draw=ImageDraw.Draw(canvas)
for i,n in enumerate(names):
    d=data(n,'view');image_path=ROOT/n/'view'/d['captureId']/d['views'][0]['file']
    im=Image.open(image_path).convert('RGB');im.thumbnail((640,400))
    x=(i%2)*640;y=(i//2)*420
    canvas.paste(im,(x,y+20));draw.text((x+5,y+3),n+' selected #'+str(selected[i]),fill='black')
out={'rawXmlDifferences':diffs,'exactDecimalSpanEquivalence':numeric,'selectedPartIds':selected,
     'expectedSelections':[4,6,6,4],'nativeAndCliMouseBehaviorMatches':selected==[4,6,6,4],
     'sameCameraDescription':all(c==cameras[0] for c in cameras),
     'meaning':'Actual desktop clicks at window-relative 1080,533; no synthetic selection. Span strings differ only in trailing decimal zeros; strict original failure remains. Current native images include selection helpers.'}
dest=ROOT/names[2];(dest/'supplemental-mouse-audit.json').write_text(json.dumps(out,indent=2))
canvas.save(dest/'mouse-contact.png');print(json.dumps(out,indent=2))
