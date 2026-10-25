# Reference fidelity: incomplete

The fixed reference is official Creator 31134, PDF SHA-256 `d4de596a11da68a6a92e7b364f1b777ecdb0d062fd47943df5c9470a60985ea6`. It has 36 pages measuring 382.677001953125 by 289.1340026855469 points. The template separates measurements, typography and component definitions from model content.

The calibration renderer rebuilds pages 3 and 34 from LDraw geometry and reusable page components. It records each input, camera and rendered asset hash. It never pastes a reference-page image.

`reference-fidelity.json` records strict comparisons using Poppler 26.10.0 at 72 and 144 DPI. At 144 DPI, page 3 differs in **64,727 pixels**: 6,164 layout pixels and 58,563 geometry pixels. Page 34 differs in **101,828 pixels**: 14,288 layout pixels and 87,540 geometry pixels. Both pages contain 443,514 pixels. The required count is zero, so both tests fail. Background agreement is not a similarity score.

Outfit is an approved free substitute for Cera Pro. Its glyph shapes and widths differ. LeoCAD and the LDraw library also differ from the reference in projection, outlines, lighting, surfaces and transparent-part shading. Some border radii and progress measurements remain provisional. No exact Creator or City claim is supported.

The native generator supports covers, ordinary steps, repeated assemblies, rotation indicators, assembly callouts, inventories and completion pages. The white City option is Creator-derived. Further reference pages and rendering calibration remain unfinished. Physical construction certification is outside this release.

## Reproduce

Download the fixed official PDF from the URL in the template. In the CAD container, run `python -m ldraw_tools.instructions.calibrate OUTPUT_DIRECTORY`. Then run `python scripts/compare_reference_pages.py REFERENCE.pdf OUTPUT_DIRECTORY/candidate.pdf COMPARISON_DIRECTORY` with NumPy, Pillow and Poppler installed. An exit code of 1 is the expected failing fidelity result, not a passing tolerance.

The 48-piece car produced 13 native pages. A 2,103-piece repeated-assembly fixture produced 95 native pages and 48 US Letter sides. Geometry and independent parts-count checks passed. Completed render images use content hashes and survive retry.
