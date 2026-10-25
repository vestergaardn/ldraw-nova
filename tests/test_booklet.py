import pytest

from ldraw_tools.booklet import assembly_quantities, section_order, write_pdf


def sample():
    def section(name, children):
        return dict(name=name, steps=[dict(parts=[dict(kind='submodel', source_section=c, quantity=n)
                                                for c, n in children])])
    return dict(source_root='main', sections=[section('main', [('axle', 2), ('body', 1)]),
        section('axle', [('wheel', 2)]), section('body', []), section('wheel', [])])


def test_nested_callouts_are_counted_and_printed_before_parent():
    manual = sample()
    assert [s['name'] for s in section_order(manual)] == ['wheel', 'axle', 'body', 'main']
    assert assembly_quantities(manual) == dict(main=1, axle=2, wheel=4, body=1)


def test_cycles_fail_instead_of_recursing_forever():
    manual = sample()
    manual['sections'][-1]['steps'][0]['parts'].append(dict(kind='submodel', source_section='main', quantity=1))
    with pytest.raises(ValueError, match='Cyclic'):
        assembly_quantities(manual)


def test_pdf_contains_all_step_parts_and_booklet_page_count(tmp_path, parts):
    import json
    from PIL import Image
    from pypdf import PdfReader

    Image.new('RGB', (100, 80), 'white').save(tmp_path / 'view.png')
    items = [dict(ref=f'{3001+i}.dat', colour=4, quantity=i+1, kind='part', description=f'Test piece {i}')
             for i in range(13)]
    (tmp_path / 'bom.json').write_text(json.dumps([dict(part=i['ref'], description=i['description'],
        colour_name='Red', colour_code=4, quantity=i['quantity']) for i in items]))
    manual = dict(title='Test car', source_root='main', physical_placements=91, views=['home', 'back'],
        source=dict(model='test.mpd'), final_images=['view.png'], sections=[dict(name='main', steps=[
            dict(number=1, parts=items, images=dict(home='view.png', back='view.png'))])])
    target = tmp_path / 'guide.pdf'
    count = write_pdf(tmp_path, manual, parts, target)
    pdf = PdfReader(target)
    text = '\n'.join(p.extract_text() for p in pdf.pages)
    assert count == len(pdf.pages) and count % 4 == 0
    assert all(i['ref'] in text and i['description'] in text for i in items)
    assert all(tuple(map(float, p.mediabox[2:])) == (396, 612) for p in pdf.pages)


def test_booklet_pipeline_preserves_every_used_view_and_reports_completion(tmp_path, parts, monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    from PIL import Image
    from ldraw_tools.booklet import create_booklet
    from ldraw_tools.manuals import current_manual
    from ldraw_tools.instructions.plan import make_plan
    from ldraw_tools.instructions.layout import load_template
    from conftest import mpd,ref
    source=tmp_path/'assembly.mpd'
    source.write_text(mpd(ref('child.ldr')+'\n0 STEP\n'+ref('3003.dat',position='200 0 0'))+
                      mpd(ref()+'\n0 STEP\n'+ref(position='100 0 0'),name='child.ldr'))
    calls=[]
    def cad(command,**kwargs):
        calls.append(command)
        if '-csv' in command:
            Path(command[command.index('-csv')+1]).write_text('Part ID,Color Code,Quantity\n3001.dat,4,2\n3003.dat,4,1\n')
        else:
            image=Path(command[command.index('-i')+1])
            numbers=range(int(command[command.index('--from')+1]),int(command[command.index('--to')+1])+1) if '--from' in command else [None]
            for number in numbers:
                target=image.with_name(image.stem+f'{number:02}.png') if number else image
                Image.new('RGB',(80,60),'white').save(target)
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr('ldraw_tools.external.subprocess.run',cad)
    work=tmp_path/'cache';output=tmp_path/'guide.pdf'
    result=create_booklet(source,output,parts,workdir=work)
    assert result['geometry_preserved'] and result['bom_matches'] and result['parts']==3
    manual_path=next(work.glob('*/manual/manual.json'));folder,manual=current_manual(manual_path.parent)
    plan=make_plan(source,manual,folder,template=load_template(),improve=True,changes=[])
    by_name={section['name']:section for section in manual['sections']}
    for section in plan.sections:
        original=by_name[section['name']]
        assert 'home' in original['steps'][-1]['images']
        for step,entry in zip(original['steps'],section['steps']):
            assert entry['camera'] in step['images']
            if not entry['insets']:assert entry['secondary_camera'] in step['images']
    assert sum(len(step['images']) for section in manual['sections'] for step in section['steps'])<12
    assert len([call for call in calls if '-csv' in call])==1, 'Only the complete model needs a CSV cross-check'
    icon_sources=list(folder.glob('icons/*/part.mpd'))
    assert icon_sources and all(p.read_text().count('0 FILE ')==1 for p in icon_sources), 'Standard thumbnails must not reload the whole assembly'
    progress=json.loads((work/'progress.json').read_text())
    assert progress['stage']=='complete' and progress['completed']==progress['total']==1
    calls.clear()
    create_booklet(source,tmp_path/'letter.pdf',parts,workdir=work,print_format='letter')
    assert calls==[], 'Print-format changes reuse verified render work'


def test_embedded_part_thumbnails_keep_their_local_definitions(tmp_path,parts,monkeypatch):
    import json
    from PIL import Image
    from ldraw_tools.instructions.layout import part_icons
    from conftest import mpd,ref
    source=mpd(ref('custom.dat'))+mpd('0 !LDRAW_ORG Unofficial_Part\n'+ref(),name='custom.dat')
    (tmp_path/'source.mpd').write_text(source)
    (tmp_path/'bom.json').write_text(json.dumps([{'part':'custom.dat','colour_code':4}]))
    manual={'preview_colour':7,'sections':[{'steps':[{'parts':[{'ref':'custom.dat','colour':4,'kind':'part'}]}]}]}
    def render(path,library,directory,**kwargs):
        assert '0 FILE custom.dat' in path.read_text() and '3001.dat' in path.read_text()
        Image.new('RGB',(20,20),'white').save(directory/'home.png')
    monkeypatch.setattr('ldraw_tools.instructions.layout.render',render)
    icons=part_icons(tmp_path,manual,parts)
    assert 'custom.dat|4' in icons
