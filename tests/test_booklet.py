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
