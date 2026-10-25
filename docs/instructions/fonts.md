# Free booklet font research

Decision: bundle **Outfit Regular, Medium and Bold**, with the SIL Open Font License 1.1. No Cera Pro files are extracted, bundled or purchased.

Primary sources:
- [Outfit authors and sources](https://github.com/Outfitio/Outfit-Fonts)
- [Licensed Google Fonts distribution](https://github.com/google/fonts/tree/main/ofl/outfit)
- [Jost authors](https://github.com/indestructible-type/Jost)
- [Poppins authors](https://github.com/itfoundry/Poppins)
- [Urbanist author](https://github.com/coreyhu/Urbanist)
- [Plus Jakarta Sans authors](https://github.com/tokotype/PlusJakartaSans)
- [SIL Open Font License FAQ](https://openfontlicense.org/ofl-faq/)

All five families provide geometric sans-serif forms and an open font license. Source URLs and SHA-256 checksums are saved beside the bundled fonts. Static 400/500/700 instances are generated from the licensed Outfit variable font using fontTools. The license declares no Reserved Font Names. The original license accompanies all distributions.

## Reproducible measurements

`scripts/compare_instruction_fonts.py` compares 40 text samples from official Creator 31134 instructions. Poppler 26.10.0 renders reference and candidates at 288 DPI. Samples cover step numbers, part quantities, inventory IDs, page numbers and regular legal text. The cover's raster overlay is excluded. No Cera font binary is extracted.

Visible-ink intersection over union measures overlapping dark pixels, after bounded translation of at most three pixels. It is **not a percentage of whole-page fidelity**. Blank page pixels never inflate the score. Equal sample weights, native font sizes and no image resizing are used. Width error measures visible ink width, not typographic advance.

| Family | Mean ink overlap | Step-number overlap | Mean absolute ink-width error |
| --- | ---: | ---: | ---: |
| Outfit | 0.67750 | 0.75407 | 3.063% |
| Jost | 0.61536 | 0.65197 | 7.335% |
| Urbanist | 0.54254 | 0.55867 | 8.487% |
| Poppins | 0.51371 | 0.51370 | 6.489% |
| Plus Jakarta Sans | 0.51006 | 0.56276 | 5.308% |

The accompanying JSON contains every sample. Visual review agrees that Outfit best preserves the circular bowls, broad numerals and compact spacing in this shortlist. Its numeral 1, stroke weights and some terminals differ visibly. This is a researched substitute, **not an exact match**. Whole-page reference comparisons must still report every difference; the zero-pixel-difference requirement does not pass because this font was selected.

Each static instance has a distinct PostScript face name. `instances.json` records its weight, source checksum and output checksum. This prevents ReportLab from collapsing Regular, Medium and Bold into one embedded face.
