"""Compare licensed candidates with rendered reference text; never extract Cera font data.

uv run --with pymupdf --with fonttools --with pillow --with numpy --with reportlab \
  python scripts/compare_instruction_fonts.py REFERENCE.pdf CANDIDATES OUTPUT
"""
from pathlib import Path
import hashlib, json, subprocess, sys
import numpy as np
import pymupdf
from PIL import Image, ImageDraw
from fontTools.ttLib import TTFont as FTFont
from fontTools.varLib.instancer import instantiateVariableFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

reference, candidates, output = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)
dpi, scale = 288, 4
pdf = pymupdf.open(reference)
pages = [2,3,4,5,6,7,8,9,10,14,17,28,34,36]
samples = []
seen = set()
for number in pages:
    page = pdf[number-1]
    target = output / f'reference-{number}'
    if not target.with_suffix('.png').exists():
        subprocess.run(['pdftoppm','-f',str(number),'-l',str(number),'-singlefile','-r',str(dpi),'-png',str(reference),str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    spans = [s for b in page.get_text('dict')['blocks'] if b['type']==0 for line in b['lines'] for s in line['spans'] if s['font'].startswith('CeraPro')]
    for s in spans:
        role = s['font'].split('-')[-1]
        if s['size'] < 9 and role=='Medium' and not (number in [3,34]): continue
        if number==34 and (len(s['text'])>7 or len(samples)>35): continue
        key = (s['text'], round(s['size'],2), role)
        if key in seen: continue
        seen.add(key)
        samples.append(dict(page=number,text=s['text'],size=s['size'],role=role,origin=s['origin'],bbox=s['bbox']))
# The cover title is a rasterised overlay; exclude it from the font-shape score.
weights = {'Regular':400,'Medium':500,'Bold':700}
results = []
visual = []
for family in sorted(p for p in candidates.iterdir() if p.is_dir() and (p/'OFL.txt').exists()):
    names = {}
    for role,weight in weights.items():
        variable = list(family.glob('*[[]wght[]].ttf'))
        destination = output / f'{family.name}-{role}.ttf'
        if variable:
            font = FTFont(variable[0])
            instantiateVariableFont(font,{'wght':weight},inplace=True,updateFontNames=True).save(destination)
        else:
            source = next(family.glob(f'*-{role}.ttf'))
            destination.write_bytes(source.read_bytes())
        name = f'{family.name}-{role}'
        pdfmetrics.registerFont(TTFont(name,str(destination)))
        names[role]=name
    path = output / (family.name+'.pdf')
    c=canvas.Canvas(str(path),pagesize=(400, max(100,len(samples)*38+20)))
    height=max(100,len(samples)*38+20)
    for i,s in enumerate(samples):
        c.setFont(names[s['role']],s['size'])
        c.drawString(20,height-35-i*38,s['text'])
    c.save()
    subprocess.run(['pdftoppm','-singlefile','-r',str(dpi),'-png',str(path),str(path.with_suffix(''))],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    rendered=Image.open(path.with_suffix('.png')).convert('RGB')
    rows=[]
    for i,s in enumerate(samples):
        ref=Image.open(output/f"reference-{s['page']}.png").convert('RGB')
        x0,_,x1,_=s['bbox']
        y0=s['origin'][1]-s['size']*.80; y1=s['origin'][1]+s['size']*.24
        refmask=np.max(np.asarray(ref.crop((int(x0*scale),int(y0*scale),int(np.ceil(x1*scale)),int(np.ceil(y1*scale))))),axis=2)<150
        width=pdfmetrics.stringWidth(s['text'],names[s['role']],s['size'])
        cy=(35+i*38)*scale
        candmask=np.max(np.asarray(rendered.crop((19*scale,int(cy-s['size']*scale*1.2),int((21+width)*scale),int(cy+s['size']*scale*.35)))),axis=2)<150
        def trim(a):
            ys,xs=np.where(a)
            return a[ys.min():ys.max()+1,xs.min():xs.max()+1] if len(xs) else a[:1,:1]
        a,b=trim(refmask),trim(candmask)
        shape=(max(a.shape[0],b.shape[0])+8,max(a.shape[1],b.shape[1])+8)
        aa=np.zeros(shape,dtype=bool);aa[4:4+a.shape[0],4:4+a.shape[1]]=a
        best=0
        for dy in range(-3,4):
            for dx in range(-3,4):
                bb=np.zeros(shape,dtype=bool);bb[4+dy:4+dy+b.shape[0],4+dx:4+dx+b.shape[1]]=b
                best=max(best,float((aa&bb).sum()/max(1,(aa|bb).sum())))
        rows.append(dict(text=s['text'],page=s['page'],role=s['role'],size=s['size'],ink_iou=round(best,5),width_difference_pct=round((b.shape[1]/a.shape[1]-1)*100,3),height_difference_pct=round((b.shape[0]/a.shape[0]-1)*100,3)))
        if s['size']==26 and s['text'] in ['2','5','8','13'] or s['text']=='1x':
            visual.append((family.name,s['text'],a,b))
    results.append(dict(family=family.name,mean_ink_iou=round(float(np.mean([r['ink_iou'] for r in rows])),5),step_ink_iou=round(float(np.mean([r['ink_iou'] for r in rows if r['size']==26])),5),mean_absolute_width_error_pct=round(float(np.mean([abs(r['width_difference_pct']) for r in rows])),3),samples=rows))
results.sort(key=lambda r:r['mean_ink_iou'],reverse=True)
report=dict(reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),renderer=subprocess.run(['pdftoppm','-v'],capture_output=True,text=True).stderr.splitlines()[0],dpi=dpi,method='Threshold RGB<150, crop to visible ink, best translation within 3 pixels, intersection over union; no size scaling or font extraction. Equal sample weights. The mask score is not a page fidelity percentage. Cover bold overlay excluded.',sample_count=len(samples),results=results)
(output/'font-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
# Contact sheet contains reference raster glyphs and candidate glyphs, for comparison only.
selected=['2','5','8','13','1x']
contact=Image.new('RGB',(1200,90+len(results)*150),'white');draw=ImageDraw.Draw(contact)
draw.text((20,15),'Cera Pro reference (black) / free candidate (blue). Native sizes; shown at 288 DPI.',fill='black')
for col,txt in enumerate(selected):draw.text((190+col*195,45),txt,fill='black')
for row,r in enumerate(results):
    y=90+row*150;draw.text((15,y+40),r['family'],fill='black')
    for col,txt in enumerate(selected):
        item=next((v for v in visual if v[0]==r['family'] and v[1]==txt),None)
        if not item:continue
        _,_,a,b=item
        for offset,mask,color in [(0,a,(25,25,25)),(75,b,(0,104,170))]:
            ink=Image.new('RGB',(mask.shape[1],mask.shape[0]),'white');ink.putdata([color if n else (255,255,255) for n in mask.flatten()]);contact.paste(ink,(185+col*195,y+offset))
contact.save(output/'comparison.png')
print(json.dumps([{k:v for k,v in r.items() if k!='samples'} for r in results],indent=2))
