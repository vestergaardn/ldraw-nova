import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from ldraw_tools.instructions.plan import improve_source, geometry_signature
from ldraw_tools.instructions.layout import impose_letter, load_template, Pages
from ldraw_tools.instructions.plan import InstructionPlan


def piece(n=0):return f'1 4 {n*80} 0 0 1 0 0 0 1 0 0 0 1 3001.dat'


def test_split_preserves_every_record_and_bfc_attachment():
    text='0 FILE main.ldr\n0 Model\n'+piece()+'\n0 BFC INVERTNEXT\n'+piece(1)+'\n0 STEP\n'+piece(2)+'\n0 FILE custom.dat\n0 BFC INVERTNEXT\n'+piece(3)+'\n'+piece(4)+'\n'
    improved,changes=improve_source(text,max_placements=1)
    assert geometry_signature(text)==geometry_signature(improved)
    assert '0 STEP\n0 BFC INVERTNEXT\n'+piece(1) in improved
    assert improved.split('0 FILE custom.dat')[1]==text.split('0 FILE custom.dat')[1]
    assert len(changes)==1


def test_more_than_two_thousand_pieces_survive_planning():
    text='0 FILE large.ldr\n0 Large model\n'+'\n'.join(piece(i) for i in range(2101))+'\n'
    improved,changes=improve_source(text)
    assert len(changes)==262
    assert geometry_signature(text)==geometry_signature(improved)
    steps=improved.split('0 STEP\n')
    assert all(sum(line.startswith('1 ') for line in step.splitlines())<=8 for step in steps)
    assert sum(line.startswith('1 ') for line in improved.splitlines())==2101


def test_distinct_piece_limit_does_not_merge_source_steps():
    source='0 FILE main.ldr\n'+'\n'.join(piece(i).replace('3001.dat',f'{3001+i}.dat') for i in range(7))+'\n0 STEP\n'+piece(10)+'\n'
    improved,changes=improve_source(source)
    assert len(changes)==1 and improved.count('0 STEP')==2
    assert geometry_signature(source)==geometry_signature(improved)


def test_letter_imposition_preserves_order_and_all_native_pages(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    from pypdf import PdfReader
    native=tmp_path/'native.pdf';target=tmp_path/'letter.pdf'
    c=Canvas(str(native),pagesize=(382.677,289.134))
    for n in range(1,10):c.drawString(10,200,f'PAGE_{n:02}');c.showPage()
    c.save();result=impose_letter(native,target);pages=PdfReader(target).pages
    assert result['page_order']==[[None,1],[2,None],[None,3],[4,9],[8,5],[6,7]]
    assert len(pages)==6
    assert all((float(p.mediabox.width),float(p.mediabox.height))==(792,612) for p in pages)
    assert sum('PAGE_' in p.extract_text() for p in pages)==6
    text='\n'.join(p.extract_text() for p in pages)
    assert all(text.count(f'PAGE_{n:02}')==1 for n in range(1,10))


def test_template_records_components_without_reference_page_images(tmp_path):
    from PIL import Image
    from pypdf import PdfReader
    plan=InstructionPlan(2,'source','geometry',{'id':'creator-31134','version':1},{})
    template=load_template();book=Pages(tmp_path/'page.pdf',template,plan,'Test')
    image=tmp_path/'geometry.png';Image.new('RGBA',(20,20),(12,13,14,255)).save(image)
    book.begin('step');book.box((14,14,80,50));book.image(image,(90,90,100,100));book.text('13',14,100,size=26);book.end();book.pdf.save()
    assert len(plan.pages[0]['placements'])==2
    assert plan.pages[0]['placements'][1]['asset'].endswith('geometry.png')
    page=PdfReader(tmp_path/'page.pdf').pages[0]
    assert abs(float(page.mediabox.width)-382.677)<.001
    assert '13' in page.extract_text()
    assert load_template('city-clear')['colors']['paper']==[1,1,1]
