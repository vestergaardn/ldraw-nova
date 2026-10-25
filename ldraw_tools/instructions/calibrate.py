"""Generate representative reference pages exclusively from model geometry.

Run with the installed library/LeoCAD: python -m ldraw_tools.instructions.calibrate OUTPUT.
This produces a candidate, never a passing claim. Use scripts/compare_reference_pages.py next.
"""
from pathlib import Path
import hashlib,json,sys
from ..common import get_parts,library_path,atomic_write
from ..document import parse_source,physical_context
from ..geometry import analyze_geometry
from ..external import render
from ..booklet import print_renderer_config
from .layout import Pages,load_template,ROOT
from .plan import InstructionPlan,VERSION


def calibrate(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    fixtures=json.loads((ROOT/'calibration/fixtures.json').read_text())
    template=load_template()
    plan=InstructionPlan(VERSION,'calibration','geometry fixtures',{'id':template['id'],'version':template['version']},{})
    book=Pages(output/'candidate.pdf',template,plan,'Creator 31134 geometry calibration')
    parts=get_parts()
    for page in fixtures['pages']:
        book.number=page['reference_page']-1;book.begin(page['kind'])
        if page['kind']=='inventory':
            # The fixed reference inventory has no progress bar.
            book.color('paper');book.pdf.rect(0,0,book.width,book.height,fill=1,stroke=0)
        if page.get('parts_box'):book.box(page['parts_box'])
        for span in page['text']:
            if span['text']==str(page['reference_page']) and span['size']==10 and page['kind']!='inventory':continue
            book.text(span['text'],*span['origin'],size=span['size'],role=span['font'].split('-')[-1])
        for item in page['geometry']:
            source=ROOT/'calibration'/item['source']
            destination=output/'renders'/source.stem
            stamp=hashlib.sha256(source.read_bytes()+b'orthographic-edges-v2').hexdigest()
            if not (destination/'sha256').exists() or (destination/'sha256').read_text()!=stamp:
                model,overlay=physical_context(parse_source(source),parts)
                diagnostics=analyze_geometry(model,overlay,detail='summary',contacts='none')['diagnostics']
                if any(d['severity']=='error' for d in diagnostics):raise ValueError(f'Invalid fixture {source.name}: {diagnostics}')
                from ldraw import inspect_model
                bounds=inspect_model(model,overlay).bounds
                with print_renderer_config(output/'render-config'):
                    render(source,library_path(),destination,views=('home',),bounds=bounds,orthographic=True)
                atomic_write(destination/'sha256',stamp)
            book.image(destination/'home.png',item['rect'],component='geometry_fixture')
        book.end()
    book.pdf.save();plan.save(output/'candidate.plan.json')
    atomic_write(output/'provenance.json',json.dumps({'reference':fixtures['reference'],'geometry_status':fixtures['geometry_status'],
        'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'calibration').glob('*') if p.suffix in {'.ldr','.mpd'}},
        'reference_raster_images_used':False,'font':'Outfit','status':'awaiting_pixel_comparison'},indent=2)+'\n')
    return str(output/'candidate.pdf')

if __name__=='__main__':print(calibrate(sys.argv[1]))
