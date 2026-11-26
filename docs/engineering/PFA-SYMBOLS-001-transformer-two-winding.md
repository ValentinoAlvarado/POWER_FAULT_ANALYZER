# PFA-SYMBOLS-001 — Two-winding transformer symbol

## Scope

This change replaces the previous separated-circle placeholder in the two-winding
transformer symbol with a renderer-neutral, parametric construction shared by Qt
Graphics View and SVG/PDF export. Electrical equipment, terminal UUIDs, network
connections, and transformer numerical models are not changed.

## Reference

The selected reference is IEC 60617 symbol **S00841, Form 1**. The IEC database
snapshot dated 2019-03-05 describes two overlapping circles arranged vertically,
with a short vertical lead extending upward from the upper circle and another
extending downward from the lower circle. The alternative form is S00842.

Official database snapshot:

<https://library.iec.ch/grasymb/grasymb.nsf/5FDC3327D03AD13DC125846A00501C93/$FILE/IEC60617_Snapshot_2019-03-05.pdf>

The implementation is project-authored geometry cross-checked against that
reference description. It does not embed or redistribute IEC artwork. The catalog
continues to use `normative_status = NOT_VERIFIED`: visual reference matching does
not establish dimensional or full normative conformity.

## Parametric construction

The symbol is defined in local horizontal coordinates and rotated 90 degrees by
the two-terminal vertical bay projection:

| Primitive | Local coordinates | Purpose |
|---|---:|---|
| Winding circle 1 | centre (-10, 0), radius 16 | First winding |
| Winding circle 2 | centre (+10, 0), radius 16 | Second winding |
| Terminal lead 1 | (-34, 0) to (-26, 0) | External terminal to circle |
| Terminal lead 2 | (+26, 0) to (+34, 0) | Circle to external terminal |

The center distance is 20 and the sum of the radii is 32, so the circles
intersect with a 12-unit overlap along their center line. Both circles are rendered
without fill so neither circumference is painted over by the other.

Terminal identities remain mapped from the canonical equipment's ordered
terminals. Display designations are read from the equipment model (for example,
HV/LV or FROM/TO where the equipment is still an unresolved placeholder); the
symbol does not invent or rewrite terminal names.

## Renderer contract

- Qt and SVG consume the same `SymbolPrimitive` sequence from `symbol_catalog.py`.
- The Qt item bounds include the rotated symbol envelope and external leads.
- The SVG keeps both circle outlines unfilled and writes terminal UUID metadata on
  the corresponding lead primitive.
- PDF is rendered from the same SVG document; no independent PDF glyph exists.
- The terminal conductor must meet the external lead endpoint, not pass through
  either winding circle.

## Acceptance tests

1. Two circles exist and have strictly positive geometric intersection.
2. Both external lead segments terminate at the outer circle boundaries.
3. Each lead carries the matching canonical terminal UUID in SVG metadata.
4. The two winding outlines are unfilled and both remain visible in the overlap.
5. Qt raster smoke checks the two intersection zones, an arc lying inside the
   other circle's interior (to catch opaque overpainting), and both external leads.
6. Existing topology, route, Workbench, and transformer electrical-model tests pass.
