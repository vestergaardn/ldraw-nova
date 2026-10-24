"""Printable, source-faithful assembly guides. No AI call or invented build order.

The existing manual pipeline owns parsing, geometry checks, step rendering and
independent LeoCAD parts-count verification. This module adds print layout and
orders subassembly instructions before their parents. An automatic booklet is
explicitly not the manually reviewed atlas export in manuals.export_manual.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape
from PIL import Image, ImageChops

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from .common import atomic_write
from .document import dependency_closure, is_part, parse_source
from .manuals import prepare_manual

PAGE = (396, 612)  # Half Letter, 5.5 x 8.5 inches. Two pages fit Letter landscape.
INK = colors.HexColor('#172B35')
MUTED = colors.HexColor('#53656D')
ACCENT = colors.HexColor('#B72D2D')
PALE = colors.HexColor('#F2F5F6')
MARGIN = 28
WIDTH = PAGE[0] - 2 * MARGIN


def clean(value):
    return ' '.join(str(value).replace('_', ' ').replace('\u2011', '-').replace('\u2013', '-')
                    .replace('\u2014', '-').split())


def section_order(manual):
    """Dependency-first order; reject cycles rather than printing unusable steps."""
    sections = {s['name']: s for s in manual['sections']}
    ordered, seen = [], set()

    def visit(name, ancestors=()):
        if name in ancestors:
            raise ValueError('Cyclic subassembly references cannot form an assembly guide')
        if name in seen:
            return
        section = sections[name]
        for step in section['steps']:
            for item in step['parts']:
                if item['kind'] == 'submodel':
                    visit(item['source_section'], (*ancestors, name))
        seen.add(name)
        ordered.append(section)

    visit(manual['source_root'])
    return ordered


def assembly_quantities(manual):
    sections = {s['name']: s for s in manual['sections']}
    counts = Counter()

    def visit(name, quantity):
        counts[name] += quantity
        for step in sections[name]['steps']:
            for item in step['parts']:
                if item['kind'] == 'submodel':
                    visit(item['source_section'], quantity * item['quantity'])

    section_order(manual)  # Validate the graph before recursively counting.
    visit(manual['source_root'], 1)
    return counts


@contextmanager
def print_renderer_config(folder):
    """Isolated LeoCAD preferences: white paper, without changing user settings.

    Called only by the dedicated CLI subprocess, never in the threaded web server.
    """
    target = Path(folder) / 'LeoCAD Software' / 'LeoCAD.conf'
    atomic_write(target, '[Settings]\nBackgroundGradient=false\nBackgroundColor=16777215\n'
                 'DrawAxes=false\nGridStuds=false\nGridLines=false\nViewSphereEnabled=false\n')
    previous = os.environ.get('XDG_CONFIG_HOME')
    os.environ['XDG_CONFIG_HOME'] = str(folder)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('XDG_CONFIG_HOME', None)
        else:
            os.environ['XDG_CONFIG_HOME'] = previous


class Booklet:
    def __init__(self, target, title):
        self.pdf = canvas.Canvas(str(target), pagesize=PAGE, pageCompression=1)
        self.pdf.setTitle(clean(title) + ' - Assembly guide')
        self.pdf.setAuthor('LDraw Nova')
        self.title = clean(title)
        self.pages = 0

    def text(self, text, x, top, width, size=10, leading=None, bold=False, color=INK):
        style = ParagraphStyle('body', fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=size, leading=leading or size * 1.35, textColor=color, splitLongWords=True)
        p = Paragraph(escape(clean(text)), style)
        _, height = p.wrap(width, PAGE[1])
        p.drawOn(self.pdf, x, top - height)
        return height

    def start(self, label, heading, subtitle=''):
        self.pages += 1
        c = self.pdf
        c.setFillColor(ACCENT)
        c.rect(MARGIN, 572, 24, 4, fill=1, stroke=0)
        self.text(label.upper(), MARGIN + 32, 580, WIDTH - 32, 8, bold=True, color=MUTED)
        height = self.text(heading, MARGIN, 554, WIDTH, 21, 25, bold=True)
        top = 554 - height - 10
        if subtitle:
            top -= self.text(subtitle, MARGIN, top, WIDTH, 9, color=MUTED) + 12
        c.setStrokeColor(colors.HexColor('#D8E0E4'))
        c.line(MARGIN, 35, PAGE[0] - MARGIN, 35)
        self.text('LDRAW NOVA / ASSEMBLY GUIDE', MARGIN, 26, WIDTH - 28, 7, color=MUTED)
        c.setFont('Helvetica', 8)
        c.setFillColor(MUTED)
        c.drawRightString(PAGE[0] - MARGIN, 18, str(self.pages))
        return top

    def image(self, path, x, bottom, width, height):
        # Fit the CAD figure, not its empty renderer margins. Keep the original
        # raster untouched; the PDF clips and positions it inside the figure box.
        with Image.open(path) as source:
            rgb = source.convert('RGB')
            bounds = ImageChops.difference(rgb, Image.new('RGB', rgb.size, 'white')).getbbox()
            iw, ih = rgb.size
        left, top, right, low = bounds or (0, 0, iw, ih)
        scale = min((width - 16) / max(1, right - left), (height - 12) / max(1, low - top))
        c = self.pdf
        c.saveState()
        clip = c.beginPath()
        clip.rect(x, bottom, width, height)
        c.clipPath(clip, stroke=0, fill=0)
        draw_x = x + (width - (right - left) * scale) / 2 - left * scale
        draw_y = bottom + (height - (low - top) * scale) / 2 - (ih - low) * scale
        c.drawImage(str(path), draw_x, draw_y, width=iw * scale, height=ih * scale, mask='auto')
        c.restoreState()

    def end(self):
        self.pdf.showPage()

    def row(self, row, top, colour_name, *, part_id=None, description=None):
        """A bounded, wrapping inventory row. Long descriptions cannot overlap."""
        self.pdf.setFillColor(PALE)
        self.pdf.roundRect(MARGIN, top - 47, WIDTH, 45, 4, fill=1, stroke=0)
        self.text(str(row['quantity']) + 'x', MARGIN + 9, top - 9, 28, 13, bold=True)
        self.text(description or row.get('description') or row.get('ref') or row['part'],
                  MARGIN + 43, top - 6, WIDTH - 53, 8.5, 10)
        self.text(f"{part_id or row.get('ref') or row.get('part')}  /  {colour_name}",
                  MARGIN + 43, top - 30, WIDTH - 53, 7.5, 9, color=MUTED)


def write_pdf(folder, manual, parts, target):
    folder = Path(folder)
    sections = section_order(manual)
    quantities = assembly_quantities(manual)
    labels = {s['name']: ('Main model' if s['name'] == manual['source_root'] else
                         f"Assembly {i + 1}") for i, s in enumerate(sections)}
    bom = json.loads((folder / 'bom.json').read_text())
    booklet = Booklet(target, manual['title'])
    total_steps = sum(len(s['steps']) for s in sections)
    booklet.start('Your next build', manual['title'],
                  f"{manual['physical_placements']} pieces / {total_steps} source steps")
    booklet.image(folder / manual['final_images'][0], MARGIN, 194, WIDTH, 265)
    booklet.text('Build it. Keep it. Make it yours.', MARGIN, 170, WIDTH, 17, bold=True)
    booklet.text('Printable instructions with subassemblies, numbered steps and a complete parts list.',
                 MARGIN, 137, WIDTH, 11)
    booklet.text('Independent fan-made guide. Not an official LEGO publication.',
                 MARGIN, 76, WIDTH, 8, color=MUTED)
    booklet.end()

    top = booklet.start('Before you build', 'A small guide to this guide')
    for heading, body in [
        ('01  Sort the pieces', 'Use the complete parts list. Part IDs and colour names come from LDraw.'),
        ('02  Build small assemblies first', 'Make the stated number of each assembly. Their parts lists describe one copy.'),
        ('03  Follow the numbered steps', 'Yellow outlines show pieces added in the current step. Two views show their positions.'),
        ('04  Print as a folded booklet', 'Use a PDF reader with Booklet printing. Choose Letter paper, both sides, and short-edge binding.'),
        ('05  Check the model as you build', 'This guide preserves the saved construction sequence. Digital checks do not prove physical fit or part availability.'),
    ]:
        top -= booklet.text(heading, MARGIN, top, WIDTH, 11, bold=True) + 6
        top -= booklet.text(body, MARGIN, top, WIDTH, 10) + 18
    booklet.end()

    for start in range(0, len(bom), 8):
        top = booklet.start('Parts list', 'Gather your pieces',
                            f"{manual['physical_placements']} pieces total / quantities include every assembly")
        for row in bom[start:start + 8]:
            booklet.row(row, top, clean(row['colour_name']))
            top -= 49
        booklet.end()

    step_index = 0
    for section in sections:
        label = labels[section['name']]
        copies = quantities[section['name']]
        for step in section['steps']:
            step_index += 1
            items = step['parts']
            # A step can have many distinct parts. Continue the parts list on
            # separate pages instead of shrinking its type or omitting items.
            top = booklet.start(label, f"Step {step['number']}",
                (f"Make {copies} copies. Parts below are for one copy." if copies > 1 else
                 f"Build sequence {step_index} of {total_steps} / add the highlighted pieces"))
            for i, view in enumerate(manual['views'][:2]):
                booklet.image(folder / step['images'][view], MARGIN, top - 148 - i * 149, WIDTH, 144)
                booklet.text('ANGLE VIEW' if view == 'home' else 'REAR VIEW', MARGIN, top - 134 - i * 149,
                             WIDTH, 7, color=MUTED)
            row_top = top - 307
            for item in items[:3]:
                colour = parts.colours_by_code.get(item['colour'])
                colour_name = getattr(colour, 'name', str(item['colour']))
                desc = labels[item['source_section']] + ' (built earlier)' if item['kind'] == 'submodel' else item['description']
                booklet.row(item, row_top, clean(colour_name), description=desc,
                            part_id=labels.get(item.get('source_section')))
                row_top -= 49
            booklet.end()
            for start in range(3, len(items), 8):
                top = booklet.start(label, f"Step {step['number']} - parts", 'Continued parts list for the same step')
                for item in items[start:start + 8]:
                    colour = parts.colours_by_code.get(item['colour'])
                    desc = labels[item['source_section']] + ' (built earlier)' if item['kind'] == 'submodel' else item['description']
                    booklet.row(item, top, clean(getattr(colour, 'name', str(item['colour']))), description=desc,
                                part_id=labels.get(item.get('source_section')))
                    top -= 49
                booklet.end()

    top = booklet.start('Made by you', 'Your model is complete')
    booklet.image(folder / manual['final_images'][0], MARGIN, 232, WIDTH, 245)
    top = 205
    for text in [
        'Compare your model with the finished view. Check that every piece is seated securely.',
        'The model source and rendered parts list agree. The assembly sequence and physical connections need your review.',
        'Created with LDraw Nova and LeoCAD. Parts geometry: the LDraw Parts Library. LEGO is a trademark of the LEGO Group.',
        'Source: ' + manual['source']['model'],
    ]:
        top -= booklet.text(text, MARGIN, top, WIDTH, 9) + 13
    booklet.end()
    # Booklet printing needs a multiple of four pages. Clearly label extra pages.
    while booklet.pages % 4:
        booklet.start('Build notes', 'Ideas for your next version')
        booklet.text('Use this page for colour changes, part substitutions or improvements.', MARGIN, 500, WIDTH, 10)
        booklet.end()
    booklet.pdf.save()
    return booklet.pages


def create_booklet(source, output, parts, *, title=None, max_instances=2000):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or output.suffix.lower() != '.pdf':
        raise ValueError('Choose a separate .pdf output file')
    model = parse_source(source)
    assemblies = [s for s in dependency_closure(model) if not is_part(s)]
    if not assemblies or sum(len(s.steps) for s in assemblies) > 250:
        raise ValueError('Choose an assembly with at most 250 saved steps')
    if any(len(s.pieces) > 1 and len([step for step in s.steps if step]) < 2 for s in assemblies):
        # Single-step subassemblies are useful, but a whole unsequenced model is not.
        if len(assemblies) == 1:
            raise ValueError('This model has no assembly sequence. Ask the model agent to add building steps first.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.booklet-', dir=output.parent) as temporary:
        temp = Path(temporary)
        with print_renderer_config(temp / 'render-config'):
            manual = prepare_manual(source, model.name, temp / 'manual', parts,
                title=title or model.description or source.stem, colour=7,
                views=('home', 'back'), kind='construction', max_instances=max_instances)
        if not manual['source_checks_passed'] or manual['bom_matches'] is not True:
            raise ValueError('The model failed source or rendered parts-list checks. Fix it before printing.')
        pdf = temp / 'booklet.pdf'
        pages = write_pdf(temp / 'manual', manual, parts, pdf)
        pdf.replace(output)
    return dict(output=str(output), pages=pages, parts=manual['physical_placements'],
                steps=sum(len(s['steps']) for s in manual['sections']),
                source_checks_passed=True, bom_matches=True, physical_validity='not_proven')
