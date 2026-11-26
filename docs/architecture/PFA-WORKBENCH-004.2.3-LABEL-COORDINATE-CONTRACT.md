# PFA-WORKBENCH-004.2.3 — Label Coordinate Contract Repair

## Defect

The property editor selected a projected `EngineeringLabel` when no user override
existed, but attempted to read `.x` and `.y`. `EngineeringLabel` stores its point
in `.position.x` and `.position.y`. After the first edit, the persisted
`DiagramLabelPlacement` override does expose scalar `.x` and `.y`.

## Correction

The inspector now branches on the actual object contract:

- Generated `EngineeringLabel`: `position.x`, `position.y`.
- Persisted `DiagramLabelPlacement`: `x`, `y`.

Rotation and the displacement delta are preserved. The electrical equipment
identity, name, terminal UUIDs and network connections are not modified by a
presentation-label edit.

## Regression acceptance

The Windows Qt property-editor acceptance now exercises both cases:

1. Rename a generated label without moving its equipment and verify that the
   projected label stays at its canonical projected position.
2. Move that equipment after an override exists and verify that the persisted
   label override follows the same X/Y displacement.
3. Undo and redo the move and label edit, verifying the generated marker-bearing
   label text is restored exactly.

This increment retains the full 004.2/004.2.1/004.2.2 cumulative payload and is
based on PFA-DESIGN-003.6 plus PFA-WORKBENCH-004.1.
