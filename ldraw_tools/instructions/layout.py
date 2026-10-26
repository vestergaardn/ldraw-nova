"""Reusable Creator/City-style booklet components, separate from model content.

Measured reference dimensions/colours and open fonts do not constitute a claim
of pixel identity. Every placement is recorded in InstructionPlan.pages.
"""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from xml.sax.saxutils import escape
from ..common import atomic_write
from ..external import render

ROOT=Path(__file__).parent

def load_template(name='creator-31134'):
    if name not in {'creator-31134','city-clear'}:raise ValueError('Unknown instruction template')
    template=json.loads((ROOT/'templates/creator-31134-v1.json').read_text())
    if name=='city-clear':
        template['id']='city-clear'
        template['colors']['paper']=[1.0,1.0,1.0]
        template['reference']['note']='Creator-derived clear layout; no separate City exact-match claim'
    return template


def register_fonts():
    for role in ['Regular','Medium','Bold']:
        name='Outfit-'+role
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,str(ROOT/'fonts'/f'{name}.ttf')))


def part_icons(folder,manual,parts,*,progress=None):
    """Geometry-rendered, content-addressed thumbnails; embedded parts stay intact."""
    folder=Path(folder)
    library=(parts.path.parent/'parts').resolve().parent
    source=(folder/'source.mpd').read_text()
    from ..document import parse_source,physical_context,section_table,is_part
    embedded=any(is_part(section) for section in section_table(parse_source(folder/'source.mpd')).values())
    unique={(p['ref'],p['colour']) for section in manual['sections'] for step in section['steps'] for p in step['parts'] if p['kind']=='part'}
    for row in json.loads((folder/'bom.json').read_text()):
        ref=str(row['part']); unique.add((ref if ref.lower().endswith('.dat') else ref+'.dat',row['colour_code']))
    icons={}
    if progress:progress('parts',0,len(unique))
    for index,(ref,colour) in enumerate(sorted(unique),1):
        # Preserve embedded DAT dependencies from the extracted source.
        prefix=f'0 FILE icon.ldr\n0 Part preview\n1 {colour if colour not in {16,24} else manual["preview_colour"]} 0 0 0 1 0 0 0 1 0 0 0 1 {ref}\n'
        # Keep the existing cache identity so interrupted jobs reuse completed
        # thumbnails. Ordinary library parts do not need the whole assembly.
        digest=hashlib.sha256(('icon-v3|'+prefix+source).encode()).hexdigest()
        content=prefix+(source if embedded else '0 NOFILE\n')
        directory=folder/'icons'/digest
        image=directory/'home.png';manifest=directory/'sha256'
        if not image.is_file() or not manifest.is_file() or manifest.read_text()!=hashlib.sha256(image.read_bytes()).hexdigest():
            atomic_write(directory/'part.mpd',content)
            from ldraw import inspect_model
            physical,overlay=physical_context(parse_source(directory/'part.mpd'),parts)
            bounds=inspect_model(physical,overlay).bounds
            render(directory/'part.mpd',library,directory,views=('home',),bounds=bounds,orthographic=True,export_bom=False)
            atomic_write(manifest,hashlib.sha256(image.read_bytes()).hexdigest())
        icons[f'{ref}|{colour}']=str(image)
        if progress:progress('parts',index,len(unique))
    return icons


class Pages:
    def __init__(self,target,template,plan,title):
        register_fonts()
        self.template,self.plan=template,plan
        self.width,self.height=template['page']['width'],template['page']['height']
        self.pdf=canvas.Canvas(str(target),pagesize=(self.width,self.height),pageCompression=1,invariant=1)
        self.pdf.setTitle(title+' - Assembly instructions')
        self.pdf.setAuthor('LEGO Nova - independent fan-made instructions')
        self.pdf.setSubject('Geometry preserved; physical construction and exact reference fidelity are not certified.')
        self.number=0
        self.records=[]

    def color(self,name,stroke=False):
        method=self.pdf.setStrokeColorRGB if stroke else self.pdf.setFillColorRGB
        method(*self.template['colors'][name])

    def text(self,value,x,y,*,size=8,role='Medium',width=None,max_height=None):
        value=str(value)
        self.color('ink')
        if width is None:
            self.pdf.setFont('Outfit-'+role,size);self.pdf.drawString(x,self.height-y,value)
        else:
            p=Paragraph(escape(value),ParagraphStyle('instruction',fontName='Outfit-'+role,fontSize=size,leading=size*1.18,textColor=tuple(self.template['colors']['ink'])))
            _,h=p.wrap(width,self.height)
            if max_height is not None and h>max_height:
                size*=max_height/h
                p=Paragraph(escape(value),ParagraphStyle('instruction',fontName='Outfit-'+role,fontSize=size,leading=size*1.18,textColor=tuple(self.template['colors']['ink'])))
                _,h=p.wrap(width,self.height)
            p.drawOn(self.pdf,x,self.height-y-h)
            return h

    def begin(self,kind,progress=0,**content):
        self.number+=1
        self.current={'number':self.number,'kind':kind,'placements':[],**content}
        self.color('paper');self.pdf.rect(0,0,self.width,self.height,fill=1,stroke=0)
        self.text(self.number,14.173 if self.number%2==0 else self.width-20,274.961,size=10)
        self.color('progress',stroke=True);self.pdf.setLineCap(1);self.pdf.setLineWidth(2)
        start=36 if self.number%2==0 else 0; end=self.width if self.number%2==0 else self.width-36
        self.pdf.line(start,16,end,16)
        if progress:
            self.pdf.setLineWidth(3.5);self.pdf.line(start,16,start+(end-start)*progress,16)

    def record(self,kind,rect,**data):self.current['placements'].append({'component':kind,'rect':list(rect),**data})

    def box(self,rect,*,kind='parts_box',color='parts'):
        x,y,w,h=rect
        style=self.template['components'].get(kind,self.template['components']['parts_box'])
        self.color(color);self.color('ink',stroke=True);self.pdf.setLineWidth(style.get('border',.75))
        self.pdf.roundRect(x,self.height-y-h,w,h,style.get('radius',7.087),fill=1,stroke=1)
        self.record(kind,rect)

    def image(self,path,rect,*,component='assembly',view=None):
        x,y,w,h=rect
        with Image.open(path) as source:
            source.load()
            if source.mode=='RGBA' and source.getextrema()[3][0]==0:
                bounds=source.getchannel('A').getbbox()
            else:
                from PIL import ImageChops
                bounds=ImageChops.difference(source.convert('RGB'),Image.new('RGB',source.size,source.convert('RGB').getpixel((0,0)))).getbbox()
            if not bounds:bounds=(0,0,*source.size)
            left,top,right,bottom=bounds
            scale=min(w/max(1,right-left),h/max(1,bottom-top))
            # Native alpha remains intact, including transparent bricks. No reference images enter this renderer.
            px=x+(w-(right-left)*scale)/2-left*scale
            py=self.height-y-(h+(bottom-top)*scale)/2-(source.height-bottom)*scale
            self.pdf.drawImage(ImageReader(source),px,py,source.width*scale,source.height*scale,mask='auto')
        self.record(component,rect,asset=str(path),camera=view)

    def arrow(self,start,end):
        x1,y1=start;x2,y2=end
        self.color('arrow',stroke=True);self.color('arrow');self.pdf.setLineWidth(2)
        self.pdf.line(x1,self.height-y1,x2,self.height-y2)
        angle=math.atan2(y2-y1,x2-x1);length=6
        points=[(x2,y2),(x2-length*math.cos(angle-.5),y2-length*math.sin(angle-.5)),(x2-length*math.cos(angle+.5),y2-length*math.sin(angle+.5))]
        path=self.pdf.beginPath();path.moveTo(points[0][0],self.height-points[0][1])
        for x,y in points[1:]:path.lineTo(x,self.height-y)
        path.close();self.pdf.drawPath(path,fill=1,stroke=0)
        self.record('assembly_arrow',[x1,y1,x2-x1,y2-y1])

    def rotation(self,previous,view):
        self.text(f'Turn: {previous} to {view}',235,250,size=7)
        self.color('ink',stroke=True);self.pdf.setLineWidth(1)
        self.pdf.arc(214,self.height-254,230,self.height-242,30,290)
        self.record('rotation',[214,242,140,14],previous=previous,camera=view)

    def end(self):
        self.plan.pages.append(self.current);self.pdf.showPage()


def write_creator(folder,manual,parts,target,plan,template,icons):
    folder=Path(folder);book=Pages(target,template,plan,manual['title'])
    sections={s['name']:s for s in manual['sections']}
    labels={s['name']:s['label'] for s in plan.sections}
    final={s['name']:folder/s['steps'][-1]['images']['home'] for s in manual['sections']}
    def icon(item):
        return final[item['source_section']] if item['kind']=='submodel' else icons[f"{item['ref']}|{item['colour']}"]
    book.begin('cover')
    book.text('LEGO NOVA',18,24,size=10,role='Bold')
    title_height=book.text(manual['title'],18,34,size=18,role='Bold',width=345,max_height=74)
    model_top=max(88,34+title_height+8)
    book.image(folder/manual['final_images'][0],(35,model_top,310,233-model_top),component='cover_model')
    book.text(f"{manual['physical_placements']} pieces",18,253,size=10)
    book.text('Independent fan-made instructions',185,253,size=7,role='Regular')
    book.end()
    book.begin('introduction')
    book.text('Before you build',18,35,size=20,role='Bold')
    messages=[('01','Sort the parts using the inventory. Match each part number and model colour code.'),
              ('02','Build numbered assemblies first. Repeat an assembly only for the stated total number of copies.'),
              ('03','The parts box shows new pieces. The small view shows another angle or a numbered assembly. Arrows link assemblies to their placement step.'),
              ('04','For the Letter booklet PDF, print at actual size, two-sided, flip on the short edge. Fold the sheets together.'),
              ('05','The model geometry is unchanged. Check physical fit and support as you build.')]
    top=58
    for number,message in messages:
        book.text(number,18,top+9,size=13,role='Bold');h=book.text(message,48,top,size=9,width=310);top+=max(30,h+10)
    book.end()
    total=sum(len(s['steps']) for s in plan.sections);index=0
    for section in plan.sections:
        source_section=sections[section['name']]
        for entry,step in zip(section['steps'],source_section['steps']):
            index+=1
            # Source-preserving mode can have arbitrarily many distinct pieces.
            # Continue the parts panel; never shrink text or omit a part.
            chunks=[step['parts'][i:i+6] for i in range(0,len(step['parts']),6)]
            for chunk_index,items in enumerate(chunks):
                book.begin('step',index/total,section=section['name'],step=entry['number'])
                x=34.016 if book.number%2 else 14.173
                width=min(330,max(65,52*len(items)+12))
                book.box((x,14.173,width,54))
                for i,item in enumerate(items):
                    cell=width/len(items);px=x+cell*i
                    book.image(icon(item),(px+6,20,cell-12,31),component='part_thumbnail')
                    book.text(f"{item['quantity']}x",px+7,61,size=8)
                book.text(entry['number'],x,98,size=26)
                if section['name']!=manual['source_root']:
                    book.text(f"{section['label']} / make {section['copies']}x",x+42,92,size=9)
                elif chunk_index:
                    book.text('Parts continued',x+42,92,size=9)
                view=entry['camera']; secondary=entry['secondary_camera']
                book.image(folder/step['images'][view],(87,103,266,126),view=view)
                book.box((18,159,67,75),kind='assembly_inset',color='inset')
                if entry['insets']:
                    inset=entry['insets'][0];assembly_label=labels[inset['assembly']]
                    book.image(final[inset['assembly']],(24,177,55,45),component='assembly_inset_model',view='home')
                    book.text(assembly_label.replace('Assembly ','')+f" / {inset['quantity']}x",24,172,size=9)
                else:
                    book.image(folder/step['images'][secondary],(24,174,55,48),component='alternate_view',view=secondary)
                    book.text('View 2',24,170,size=6)
                if entry['rotation_from']:book.rotation(entry['rotation_from'],view)
                insets=entry['insets']
                if insets:
                    label=', '.join(f"{labels[i['assembly']]} {i['quantity']}x" for i in insets)
                    book.text(label,x,242,size=8,width=200)
                    book.arrow((84,195),(101,175));entry['arrows']=[{'kind':'assembly_callout','from':[84,195],'to':[101,175]}]
                book.end()
    bom=json.loads((folder/'bom.json').read_text())
    for offset in range(0,len(bom),24):
        book.begin('inventory',1)
        book.text('Parts inventory',14.173,28,size=16,role='Bold')
        for i,item in enumerate(bom[offset:offset+24]):
            x=14.173+(i%6)*58.287;y=40+(i//6)*51
            ref=str(item['part']);ref=ref if ref.lower().endswith('.dat') else ref+'.dat'
            key=f"{ref}|{item['colour_code']}"
            path=icons.get(key)
            if path:book.image(path,(x+2,y,49,27),component='inventory_thumbnail')
            else:book.text(item.get('description',ref),x,y,size=6,width=52)
            book.text(f"{item['quantity']}x",x,y+35,size=6.5)
            book.text(f"{ref.removesuffix('.dat')} / {item['colour_code']}",x,y+39,size=6,width=54)
        book.end()
    book.begin('completion',1)
    book.text('Build complete',18,32,size=20,role='Bold')
    book.image(folder/manual['final_images'][0],(40,53,302,152),component='completed_model')
    book.text('Created with LEGO Nova and LeoCAD. Parts geometry: LDraw Parts Library.',18,222,size=7,role='Regular',width=345)
    book.text('LEGO is a trademark of the LEGO Group. This independent guide has no LEGO endorsement.',18,239,size=6.4,role='Regular',width=345)
    book.end();book.pdf.save()
    return book.number


def impose_letter(source,target):
    """Two native-sized pages per Letter landscape side, outer sheets first."""
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.generic import RectangleObject
    import copy
    reader=PdfReader(source);writer=PdfWriter();count=len(reader.pages);padded=(count+3)//4*4
    order=[]
    for sheet in range(padded//4):
        for pair in [(padded-1-sheet*2,sheet*2),(sheet*2+1,padded-2-sheet*2)]:
            side=writer.add_blank_page(width=792,height=612)
            for slot,index in enumerate(pair):
                if index>=count:continue
                page=copy.copy(reader.pages[index]);w=float(page.mediabox.width);h=float(page.mediabox.height)
                scale=min(1,384/w,588/h)
                x=slot*396+(396-w*scale)/2;y=(612-h*scale)/2
                side.merge_transformed_page(page,Transformation().scale(scale).translate(x,y))
            order.append([p+1 if p<count else None for p in pair])
    writer.add_metadata({'/Title':'US Letter folded booklet - print actual size, duplex short edge','/Creator':'LEGO Nova'})
    with open(target,'wb') as stream:writer.write(stream)
    return {'sheet_size':[792,612],'page_order':order,'source_pages':count,'padded_pages':padded,'print':'Actual size; two-sided; flip short edge; fold on the vertical centre'}
