import json
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from ldraw_tools.external import render_steps


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
