"""Independent PNG and exact XML comparison for native UI replay fixtures."""
import json,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw
from precision_acceptance import ROOT
from precision_diff import compare
for name in sys.argv[1:]:
 root=ROOT/name
 def data(label):return json.loads((root/(label+'.json')).read_text(encoding='utf-8-sig'))['data']
 a,b=data('native-views'),data('cli-views');pairs=[]
 canvas=Image.new('RGB',(480*len(a['views']),650),'white');draw=ImageDraw.Draw(canvas)
 for i,(va,vb) in enumerate(zip(a['views'],b['views'])):
  pa=Path(a['outputDirectory'])/va['file'];pb=Path(b['outputDirectory'])/vb['file']
  ia=Image.open(pa).convert('RGB');ib=Image.open(pb).convert('RGB');diff=ImageChops.difference(ia,ib)
  pairs.append({'view':va['name'],'native':str(pa),'cli':str(pb),'identicalPixels':diff.getbbox() is None,'differenceBounds':diff.getbbox()})
  for row,img in enumerate((ia,ib)):
   img.thumbnail((480,300));canvas.paste(img,(i*480,row*325+25));draw.text((i*480+5,row*325+5),('native UI' if row==0 else 'CLI')+' '+va['name'],fill='black')
 canvas.save(root/'native-cli-contact.png')
 result={'imagePairs':pairs,'exactXmlDifferences':compare(data('native-target')['xml'],data('cli-target')['xml']),'meaning':'Independent file comparison; contact sheet must also be opened. No claim about untested adapter fields or dynamic flight behavior.'}
 (root/'independent-image-state-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(name,[(x['view'],x['identicalPixels']) for x in pairs],len(result['exactXmlDifferences']))
