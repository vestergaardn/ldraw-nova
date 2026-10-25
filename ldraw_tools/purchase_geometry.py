"""Conservative physical inventory for purchase approval, using the installed library.

No agent-writable part index, BOM CSV, MPD overlay or derived geometry cache is
evidence of a purchasable part. Only rigid placements of actual library parts
qualify. Unsupported assemblies must be rebuilt from independently mapped parts.
"""
from collections import Counter
from pathlib import Path
import re

import numpy as np

from .common import library_path, normalized
from .document import parse_source, source_blocks


def _records(lines):
    # Comments/attribution may differ; all geometry and rendering directives must match.
    return [" ".join(line.split()).casefold() for line in lines
            if line.strip() and (line.split()[0] in {'1', '2', '3', '4', '5'}
                                or re.match(r'0\s+(?:BFC|!TEXMAP|!COLOUR|!DATA|!LDCAD|!LEOCAD)\b', line, re.I))]


def library_part(library, reference):
    """Return one supported, unmodified physical part; never a shortcut or primitive."""
    name = normalized(reference)
    if not re.fullmatch(r'[a-z0-9_.-]+\.dat', name) or '..' in name:
        raise ValueError(f'Unsupported physical part reference: {reference}')
    file = Path(library) / 'parts' / name
    if not file.is_file():
        raise ValueError(f'No installed physical LEGO part: {reference}')
    text = file.read_text(encoding='utf-8-sig')
    org = re.search(r'^0\s+!LDRAW_ORG\s+(\S+)', text, re.M)
    title = text.splitlines()[0].removeprefix('0 ').strip()
    if not org or org[1] != 'Part' or title.startswith(('~', '=', '_')):
        raise ValueError(f'Unsupported composite, alias or internal part: {reference}. Use mapped physical parts.')
    return title, text


def requirements(path, *, library=None):
    library = library_path(library)
    model = parse_source(path)
    blocks = source_blocks(path)
    blocks = {normalized(name).strip(): [line for _, line in lines] for name, lines in blocks.items()}
    root = normalized(model.name).strip()
    if root not in blocks:
        raise ValueError('Missing root assembly')
    # Every embedded definition must equal its installed counterpart. This also
    # prevents replacing subparts inside an otherwise unchanged official part.
    for name, lines in blocks.items():
        if any(re.match(r'\s*0\s+!(?:COLOUR|TEXMAP|DATA)\b', line, re.I) for line in lines):
            raise ValueError(f'Custom colours or geometry are not purchasable: {name}')
        if name.endswith('.dat'):
            if name.startswith('/') or '..' in Path(name).parts:
                raise ValueError(f'Invalid embedded part: {name}')
            installed = next((library / folder / name for folder in ('parts', 'p')
                              if (library / folder / name).is_file()), None)
            if installed is None or _records(lines) != _records(installed.read_text(encoding='utf-8-sig').splitlines()):
                raise ValueError(f'Embedded part differs from the installed library: {name}')

    counts, names, validated = Counter(), {}, {}
    total = 0

    def visit(section, inherited, stack):
        nonlocal total
        if section in stack:
            raise ValueError('Cyclic model assembly')
        for line in blocks[section]:
            fields = line.split(None, 14)
            if not fields or fields[0] == '0':
                continue
            if fields[0] != '1' or len(fields) != 15:
                raise ValueError(f'Custom geometry in assembly {section}; use physical LEGO parts')
            values = np.array([float(v) for v in fields[2:14]])
            rotation = values[3:].reshape(3, 3)
            if (not np.isfinite(values).all() or
                    not np.allclose(rotation.T @ rotation, np.eye(3), atol=0.002, rtol=0) or
                    not np.isclose(np.linalg.det(rotation), 1, atol=0.002, rtol=0)):
                raise ValueError(f'Scaled, mirrored or distorted part in {section}')
            color = inherited if fields[1] == '16' else fields[1]
            reference = normalized(fields[14]).strip()
            if reference in blocks and not reference.endswith('.dat'):
                visit(reference, color, (*stack, section))
                continue
            if not color.isdecimal() or color in {'16', '24'}:
                raise ValueError(f'Unresolved or custom colour in {section}: {color}')
            if reference not in validated:
                validated[reference] = library_part(library, reference)[0]
            part = reference.removesuffix('.dat')
            counts[part, color] += 1
            names[part, color] = validated[reference]
            total += 1
            if total > 100_000:
                raise ValueError('Purchasing supports at most 100,000 physical pieces')

    visit(root, '16', ())
    if not total:
        raise ValueError('The model contains no physical parts')
    return [dict(part=p, color=c, quantity=q, name=names[p, c]) for (p, c), q in sorted(counts.items())]
