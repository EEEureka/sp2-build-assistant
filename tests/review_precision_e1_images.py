"""Create inspection contact sheets and exact native-image difference crops."""
from pathlib import Path
import sys,json
import numpy as np
from PIL import Image,ImageDraw
gold=Path(sys.argv[1]);fit=Path(sys.argv[2]);labels=['gold','trial-1','trial-2','trial-3']
sheet=Image.new('RGB',(1800,4*630),'white');draw=ImageDraw.Draw(sheet)
for row,label in enumerate(labels):
    for col,view in enumerate(('top','right','front')):
        suffix='front' if view=='front' else 'plan-side'
        parent=gold/('gold-'+suffix) if label=='gold' else fit/(label+'-final-native-'+suffix)
        src=Image.open(next(parent.rglob(view+'.png'))).convert('RGB');src.thumbnail((600,600))
        sheet.paste(src,(col*600,row*630+30));draw.text((col*600+8,row*630+8),label+' '+view,fill='black')
sheet.save(fit/'native-results-contact.png')
g=Image.open(next((gold/'gold-front').rglob('front.png'))).convert('RGB');a=np.asarray(g,dtype=int)
for trial in (1,3):
    f=Image.open(next((fit/('trial-'+str(trial)+'-final-native-front')).rglob('front.png'))).convert('RGB');b=np.asarray(f,dtype=int)
    yy,xx=np.where(np.max(np.abs(a-b),axis=2)>2)
    if len(xx):
        rect=(max(0,int(xx.min())-15),max(0,int(yy.min())-15),min(2048,int(xx.max())+16),min(2048,int(yy.max())+16))
        out=Image.new('RGB',((rect[2]-rect[0])*2,rect[3]-rect[1]),'white');out.paste(g.crop(rect));out.paste(f.crop(rect),(rect[2]-rect[0],0));out.save(fit/('trial-'+str(trial)+'-front-diff-crop.png'))
        print(json.dumps({'trial':trial,'crop':rect,'pixelsOver2':len(xx)}))
