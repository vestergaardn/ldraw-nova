"""Server-only BOM from a captured source, independent of agent-writable CSV files."""
import json
from pathlib import Path
import sys
from .common import get_parts, jsonable
from .document import parse_source, physical_context


def requirements(path, parts=None):
    model=parse_source(Path(path))
    physical,overlay=physical_context(model,parts or get_parts())
    for index,_ in enumerate(physical.iter_occurrences(),1):
        if index>100_000:raise ValueError('Pricing supports at most 100,000 physical pieces')
    rows=jsonable(physical.bill_of_materials(parts=overlay))
    if not rows or sum(r['quantity'] for r in rows)>100_000:
        raise ValueError('Pricing supports 1 to 100,000 physical pieces')
    return [{'part':str(r['part']).lower().removesuffix('.dat'),'color':str(r['colour_code']),
             'quantity':r['quantity'],'name':r.get('description','')} for r in rows]


if __name__=='__main__':
    print(json.dumps(requirements(sys.argv[1])))
