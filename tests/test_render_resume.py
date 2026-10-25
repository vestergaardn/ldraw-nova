import json
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from ldraw_tools.external import render_steps


def test_selected_views_reuse_existing_images_and_report_each_chunk(tmp_path, monkeypatch):
    from types import SimpleNamespace
    model=tmp_path/'model.mpd';model.write_text('0 Model\n')
    library=tmp_path/'library';library.mkdir()
    target=tmp_path/'images';calls=[];progress=[]
    monkeypatch.setattr('ldraw_tools.external.cad_source',lambda p,l,t:(p,l,{}))
    def run(command, **kwargs):
        view=Path(command[command.index('-i')+1])
        first=int(command[command.index('--from')+1]);last=int(command[command.index('--to')+1])
        calls.append((view.stem,first,last))
        for number in range(first,last+1):view.with_name(f'{view.stem}{number:02}.png').write_bytes(b'image')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr('ldraw_tools.external.subprocess.run',run)
    steps=list(range(1,12))
    render_steps(model,library,target,steps=steps,views=('home','back','top'))
    calls.clear()
    selected={n:('home','back') for n in steps}
    rows=render_steps(model,library,target,steps=steps,views=('home','back','top'),
                      step_views=selected,progress=lambda done,total:progress.append((done,total)))
    assert calls==[], 'Selecting fewer views must reuse the existing geometry cache'
    assert len(rows)==22 and all(row['view']!='top' for row in rows)
    assert progress[-1]==(22,22)
    (target/'step-004-home.png').unlink()
    progress.clear()
    render_steps(model,library,target,steps=steps,views=('home','back','top'),
                 step_views=selected,progress=lambda done,total:progress.append((done,total)))
    assert calls==[('home',4,4)]
    assert progress[-1]==(22,22) and progress[0][0]<22


def test_thumbnail_render_can_skip_the_unused_csv_process(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from ldraw_tools.external import render
    model=tmp_path/'model.mpd';model.write_text('0 Model\n');calls=[]
    monkeypatch.setattr('ldraw_tools.external.cad_source',lambda p,l,t:(p,l,{}))
    def run(command, **kwargs):
        calls.append(command)
        flag='-i' if '-i' in command else '-csv'
        Path(command[command.index(flag)+1]).write_bytes(b'output')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr('ldraw_tools.external.subprocess.run',run)
    result=render(model,tmp_path,tmp_path/'images',views=('home',),export_bom=False)
    assert len(calls)==1 and result['bom'] is None
    calls.clear()
    result=render(model,tmp_path,tmp_path/'verified',views=('home',))
    assert len(calls)==2 and result['bom'].endswith('leocad-bom.csv')


def test_resume_reuses_only_verified_completed_images(tmp_path,monkeypatch):
    model=tmp_path/'model.ldr';model.write_text('0 Test\n')
    library=tmp_path/'lib';library.mkdir()
    calls=[]
    monkeypatch.setattr('ldraw_tools.external.cad_source',lambda p,l,t:(p,l,{}))
    def run(command,**kwargs):
        start=int(command[command.index('--from')+1]);end=int(command[command.index('--to')+1]);calls.append((start,end))
        target=Path(command[command.index('-i')+1])
        for n in range(start,end+1):Image.new('RGBA',(10,10),(0,0,0,0)).save(target.with_name(target.stem+f'{n:02}'+'.png'))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('ldraw_tools.external.subprocess.run',run)
    target=tmp_path/'renders'
    args=dict(steps=list(range(1,12)),views=('home',))
    render_steps(model,library,target,**args)
    assert calls==[(1,8),(9,11)]
    render_steps(model,library,target,**args);assert len(calls)==2
    (target/'step-004-home.png').write_bytes(b'corrupt')
    render_steps(model,library,target,**args);assert calls[-1]==(4,4)
    model.write_text('0 Changed\n')
    render_steps(model,library,target,**args);assert calls[-2:]==[(1,8),(9,11)]
