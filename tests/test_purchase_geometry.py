from pathlib import Path
import pytest
from ldraw_tools.purchase_geometry import requirements
from conftest import mpd, ref


def write(tmp_path, body):
    file=tmp_path/'model.mpd';file.write_text(body);return file


def test_nested_repeated_assemblies_and_inherited_colors(parts,tmp_path):
    text=mpd(ref('pair.ldr',4)+'\n'+ref('pair.ldr',14))
    text+=mpd(ref('single.ldr',16)+'\n'+ref('single.ldr',16,position='80 0 0'),'pair.ldr')
    text+=mpd(ref('3001.dat',16),'single.ldr')
    rows=requirements(write(tmp_path,text),library=Path(parts.path).parent)
    assert {(r['part'],r['color'],r['quantity']) for r in rows}=={('3001','4',2),('3001','14',2)}


@pytest.mark.parametrize('body',[
    ref('missing.dat'), ref('s/3001.dat'), ref('3001.dat',16), ref('3001.dat','0x2FF0000'),
    ref('3001.dat',matrix='2 0 0 0 1 0 0 0 1'),
    ref('3001.dat',matrix='-1 0 0 0 1 0 0 0 1'),
    ref('3001.dat',position='nan 0 0'),
    ref()+'\n3 4 0 0 0 10 0 0 0 10 0',
    '0 !COLOUR Red CODE 4 VALUE #000000 EDGE #333333\n'+ref(),
])
def test_unknown_custom_scaled_or_missing_evidence_rejected(parts,tmp_path,body):
    with pytest.raises(ValueError):requirements(write(tmp_path,mpd(body)),library=Path(parts.path).parent)


def test_embedded_official_definition_must_match_library(parts,tmp_path):
    installed=(Path(parts.path).parent/'parts/3001.dat').read_text()
    source=mpd(ref())+'0 FILE 3001.dat\n'+installed+'0 NOFILE\n'
    assert requirements(write(tmp_path,source),library=Path(parts.path).parent)[0]['quantity']==1
    with pytest.raises(ValueError,match='differs from the installed library'):
        requirements(write(tmp_path,source.replace('4 16 -40','4 16 -60')),library=Path(parts.path).parent)


def test_unsupported_composite_is_not_counted_as_one_purchase(parts,tmp_path):
    library=tmp_path/'library';(library/'parts').mkdir(parents=True)
    (library/'parts/3001c01.dat').write_text('0 Assembly\n0 !LDRAW_ORG Shortcut\n'+ref())
    with pytest.raises(ValueError,match='Unsupported composite'):
        requirements(write(tmp_path,mpd(ref('3001c01.dat'))),library=library)


def test_cycle_rejected_and_large_quantities_counted(parts,tmp_path):
    cyclic=mpd(ref('loop.ldr'))+mpd(ref('loop.ldr'),'loop.ldr')
    with pytest.raises(ValueError):requirements(write(tmp_path,cyclic),library=Path(parts.path).parent)
    source=mpd('\n'.join(ref(position=f'{80*i} 0 0') for i in range(2103)))
    assert requirements(write(tmp_path,source),library=Path(parts.path).parent)[0]['quantity']==2103
