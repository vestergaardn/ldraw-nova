"""Versioned instruction planning. Geometry changes are forbidden, including metadata.

The planner only inserts STEP records. It preserves source order, dependency
boundaries, transformations, colours, quantities, BFC directives and part aliases.
Camera selection is a visibility heuristic, not physical construction certification.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib, json, math
from ..common import atomic_write, normalized
from ..document import dependency_closure, is_part, parse_source

VERSION = 4
VIEWS = {'home': (1,-1,-1), 'back': (0,0,1), 'top': (0,-1,0)}


def geometry_signature(text: str) -> str:
    # Keep every non-STEP record, including definitions and stateful meta commands.
    records = [line.rstrip('\r') for line in text.splitlines() if line.split() != ['0','STEP']]
    return hashlib.sha256('\n'.join(records).encode()).hexdigest()


def improve_source(text: str, *, max_placements=8, max_distinct=6):
    if max_placements < 1 or max_distinct < 1:
        raise ValueError('Instruction step limits must be positive')
    output, pending, changes = [], [], []
    active, count, distinct = '', 0, set()
    for number,line in enumerate(text.splitlines(),1):
        f=line.split()
        if f[:2] in (['0','FILE'], ['0','NOFILE']) or f[:2] in (['0','STEP'],['0','ROTSTEP']):
            output.extend(pending); pending=[]; output.append(line)
            count,distinct=0,set()
            if f[:2]==['0','FILE']: active=' '.join(f[2:]).lower()
            continue
        if f[:1]==['1'] and len(f)>=15 and not active.endswith('.dat'):
            identity=(f[1],' '.join(f[14:]))
            if count >= max_placements or (identity not in distinct and len(distinct)>=max_distinct):
                # Insert BEFORE buffered BFC INVERTNEXT / other metadata for this piece.
                output.append('0 STEP'); count,distinct=0,set()
                changes.append(dict(kind='split_crowded_step',before_source_line=number,section=active))
            output.extend(pending); pending=[]; output.append(line)
            count+=1; distinct.add(identity)
        elif f[:1] in (['2'],['3'],['4'],['5']):
            output.extend(pending); pending=[]; output.append(line)
        else:
            pending.append(line)
    output.extend(pending)
    revised='\n'.join(output)+'\n'
    if geometry_signature(text)!=geometry_signature(revised):
        raise ValueError('Instruction improvement changed model geometry or metadata')
    return revised,changes


def visibility_view(preview, step_number):
    """Rank three reproducible views by newly placed centre visibility.

    A centre proxy avoids a quadratic all-triangle analysis for large guides.
    Occlusion ties prefer the stable home view. The plan records this limitation.
    """
    from ldraw import Piece
    old,new=[],[]
    for index,step in enumerate(preview.steps,1):
        if index>step_number:break
        target=new if index==step_number else old
        target.extend([tuple(float(getattr(p.position,a)) for a in 'xyz') for p in step if isinstance(p,Piece)])
    if not new:return 'home',{}
    # Bound scoring work without removing any model placements from rendering.
    old=old[::max(1,len(old)//2000)]
    scores={}
    for name,direction in VIEWS.items():
        length=math.sqrt(sum(v*v for v in direction)); d=tuple(v/length for v in direction)
        up=(0,0,1) if name=='top' else (0,-1,0)
        right=(d[1]*up[2]-d[2]*up[1],d[2]*up[0]-d[0]*up[2],d[0]*up[1]-d[1]*up[0])
        n=math.sqrt(sum(v*v for v in right));right=tuple(v/n for v in right)
        vertical=(right[1]*d[2]-right[2]*d[1],right[2]*d[0]-right[0]*d[2],right[0]*d[1]-right[1]*d[0])
        def project(p):return tuple(sum(p[i]*v[i] for i in range(3)) for v in (right,vertical,d))
        previous=[project(p) for p in old]
        visible=0
        for p in new:
            x,y,z=project(p)
            blocked=any(abs(x-a)<12 and abs(y-b)<12 and c>z+4 for a,b,c in previous)
            visible+=not blocked
        scores[name]=visible/len(new)
    return max(scores,key=scores.get),scores


@dataclass
class InstructionPlan:
    version: int
    source_sha256: str
    geometry_sha256: str
    template: dict
    improvement: dict
    sections: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    cameras: dict = field(default_factory=lambda: {k:list(v) for k,v in VIEWS.items()})
    fidelity: dict = field(default_factory=lambda: {'status':'not_exact','font':'Outfit','font_version':2,'reference_font':'Cera Pro','physical_validity':'not_proven'})

    def save(self,path):
        atomic_write(Path(path),json.dumps(asdict(self),indent=2)+'\n')


def make_plan(source, manual, folder, *, template, improve, changes):
    from ..booklet import section_order, assembly_quantities
    source=Path(source)
    plan=InstructionPlan(VERSION,hashlib.sha256(source.read_bytes()).hexdigest(),geometry_signature(source.read_text()),
                         {'id':template['id'],'version':template['version']},
                         {'enabled':improve,'changes':changes,'camera_method':'bounded centre-occlusion heuristic','geometry_preserved':True})
    counts=assembly_quantities(manual)
    for index,section in enumerate(section_order(manual),1):
        preview=parse_source(Path(folder)/section['directory']/'preview.mpd')
        entries=[];previous='home'
        for step in section['steps']:
            view,scores=visibility_view(preview,step['number']) if improve else ('home',{})
            secondary='back' if view!='back' else 'home'
            entries.append({'number':step['number'],'camera':view,'secondary_camera':secondary,
                            'visibility_scores':scores,'rotation_from':previous if view!=previous else None,
                            'arrows':[], 'parts':step['parts'],
                            'insets':[{'assembly':p['source_section'],'quantity':p['quantity']} for p in step['parts'] if p['kind']=='submodel']})
            previous=view
        plan.sections.append({'name':section['name'],'label': 'Main model' if section['name']==manual['source_root'] else f'Assembly {index}',
                              'copies':counts[section['name']],'steps':entries})
    return plan
