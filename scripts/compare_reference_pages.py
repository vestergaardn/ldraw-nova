"""Strict, reproducible PDF pixel tests. A nonzero difference always fails.

Usage: python scripts/compare_reference_pages.py reference.pdf candidate.pdf output
Poppler must render both PDFs in the same process environment. Geometry regions
come from independently measured reference rectangles; all other pixels are layout.
No threshold, blur, alignment or reference-image substitution can turn a failure into a pass.
"""
from pathlib import Path
import hashlib,json,subprocess,sys
import numpy as np
from PIL import Image
reference,candidate,output=map(Path,sys.argv[1:]);output.mkdir(parents=True,exist_ok=True)
fixtures=json.loads((Path(__file__).resolve().parents[1]/'ldraw_tools/instructions/calibration/fixtures.json').read_text())
if hashlib.sha256(reference.read_bytes()).hexdigest()!=fixtures['reference']['sha256']:raise ValueError('Reference PDF hash changed')
report={'reference':fixtures['reference'],'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
        'renderer':subprocess.run(['pdftoppm','-v'],capture_output=True,text=True).stderr.splitlines()[0],
        'required_changed_pixels':0,'tests':[],'status':'pass'}
for dpi in [72,144]:
 for index,page in enumerate(fixtures['pages'],1):
    images=[]
    for name,path,number in [('reference',reference,page['reference_page']),('candidate',candidate,index)]:
        target=output/f'{name}-p{page["reference_page"]}-{dpi}'
        subprocess.run(['pdftoppm','-f',str(number),'-l',str(number),'-singlefile','-r',str(dpi),'-png',str(path),str(target)],check=True,capture_output=True)
        images.append(np.asarray(Image.open(target.with_suffix('.png')).convert('RGB')))
    a,b=images
    if a.shape!=b.shape:raise ValueError('Reference and candidate dimensions differ')
    changed=np.any(a!=b,axis=2);geometry=np.zeros(changed.shape,dtype=bool);scale=dpi/72
    for item in page['geometry']:
        x,y,w,h=item['rect'];geometry[int(y*scale):int(np.ceil((y+h)*scale)),int(x*scale):int(np.ceil((x+w)*scale))]=True
    metrics={'reference_page':page['reference_page'],'candidate_page':index,'dpi':dpi,'size':[a.shape[1],a.shape[0]],
             'changed_pixels':int(changed.sum()),'total_pixels':int(changed.size),
             'layout_changed_pixels':int((changed & ~geometry).sum()),'layout_pixels':int((~geometry).sum()),
             'geometry_changed_pixels':int((changed & geometry).sum()),'geometry_pixels':int(geometry.sum()),
             'max_channel_error':int(np.abs(a.astype(int)-b.astype(int)).max()),'pass':not bool(changed.any())}
    if not metrics['pass']:report['status']='fail'
    report['tests'].append(metrics)
    diff=np.full(a.shape,255,dtype=np.uint8);diff[changed & ~geometry]=[213,40,40];diff[changed & geometry]=[46,80,210]
    Image.fromarray(diff).save(output/f'difference-p{page["reference_page"]}-{dpi}.png')
(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));sys.exit(0 if report['status']=='pass' else 1)
