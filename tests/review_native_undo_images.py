"""Independent before/edit/native-undo PNG comparison; open contact after running."""
import json,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
from precision_acceptance import ROOT

prep,verify=ROOT/sys.argv[1],ROOT/sys.argv[2]
def load(folder,label):return json.loads((folder/(label+'.json')).read_text(encoding='utf-8-sig'))['data']
rows=[('before',load(prep,'baseline-views')),('CLI edit',load(prep,'changed-views')),('native Undo',load(verify,'restored-views'))]
n=len(rows[0][1]['views']);canvas=Image.new('RGB',(480*n,325*len(rows)),'white');draw=ImageDraw.Draw(canvas)
images=[]
for row,(label,data) in enumerate(rows):
    pixels=[]
    for i,view in enumerate(data['views']):
        im=Image.open(Path(data['outputDirectory'])/view['file']).convert('RGB');pixels.append(im.copy())
        im.thumbnail((480,300));canvas.paste(im,(i*480,row*325+25));draw.text((i*480+5,row*325+5),label+' '+view['name'],fill='black')
    images.append(pixels)
result=[{'view':rows[0][1]['views'][i]['name'],
         'restoredPixelsIdentical':ImageChops.difference(images[0][i],images[2][i]).getbbox() is None,
         'editedPixelsDiffer':ImageChops.difference(images[0][i],images[1][i]).getbbox() is not None} for i in range(n)]
canvas.save(verify/'native-undo-contact.png')
(verify/'independent-image-audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
