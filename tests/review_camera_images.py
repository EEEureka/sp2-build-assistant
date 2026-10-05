"""Make paginated contact sheets for actual inspection; no automatic visual pass."""
import json,sys
from pathlib import Path
from PIL import Image,ImageDraw

root=Path(sys.argv[1]);rows=[]
for f in sorted(root.glob('*.json')):
    if f.name.endswith('.input.json'):continue
    data=json.loads(f.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict):continue
    d=data.get('data',{})
    if data.get('success') and d.get('backend')=='native_designer_camera':
        manifest=Path(d['manifestPath'])
        for v in json.loads(manifest.read_text(encoding='utf-8-sig'))['views']:
            rows.append((f.stem+' '+v['name'],manifest.parent/v['file']))
for page,start in enumerate(range(0,len(rows),8),1):
    selected=rows[start:start+8];sheet=Image.new('RGB',(1280,4*430),'white');draw=ImageDraw.Draw(sheet)
    for i,(name,path) in enumerate(selected):
        x=(i%2)*640;y=(i//2)*430
        src=Image.open(path).convert('RGB');src.thumbnail((640,400))
        sheet.paste(src,(x,y+25));draw.text((x+8,y+6),name,fill='black')
    sheet.save(root/f'inspect-camera-{page:02}.png')
print(json.dumps({'images':len(rows),'pages':(len(rows)+7)//8,'note':'Open every sheet before claiming inspection.'}))
