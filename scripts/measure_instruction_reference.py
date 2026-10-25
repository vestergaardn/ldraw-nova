"""Record reference measurements without extracting fonts or copying page images.

Run with: uv run --with pymupdf python scripts/measure_instruction_reference.py PDF OUTPUT
The reference PDF stays outside Git. Coordinates use PDF points from the top left.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
import pymupdf

source, destination = map(Path, sys.argv[1:3])
doc = pymupdf.open(source)
report = {'source_url':'https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6457824.pdf',
          'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'measurement_tool':'PyMuPDF '+pymupdf.VersionBind,
          'page_count':len(doc),'units':'PDF points; origin top left',
          'fonts': sorted({f[3].split('+')[-1] for p in doc for f in p.get_fonts()}),
          'pages':[],'fidelity':{'status':'unproven','required_changed_pixels':0,
                               'blockers':['Licensed fonts unavailable','Geometry rendering calibration incomplete']}}
for number in [1,2,3,14,17,28,34,36]:
 p=doc[number-1]
 texts=[{'text':s['text'],'font':s['font'],'size':s['size'],'color':s['color'],
         'origin':s['origin'],'bounds':s['bbox']} for b in p.get_text('dict')['blocks'] if 'lines'in b
         for line in b['lines'] for s in line['spans']]
 fills=collections.Counter(tuple(d['fill']) for d in p.get_drawings() if d['fill'])
 report['pages'].append({'number':number,'size':[p.rect.width,p.rect.height],
     'text':texts,'fills':[{'rgb':k,'uses':v} for k,v in fills.most_common()],
     'image_bounds':[list(i['bbox']) for i in p.get_image_info()],
     'vector_bounds':[{'bounds':list(d['rect']),'fill':d['fill'],'stroke':d['color'],'width':d['width']}
                      for d in p.get_drawings()]})
destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['sha256','page_count','fonts','fidelity']}))
