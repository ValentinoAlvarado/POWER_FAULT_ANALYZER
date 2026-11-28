# PFA-DIAGRAM-006 — Straight bus taps and drag-scoped snap

## Problem

The previous implementation quantized every `ItemPositionChange`, including programmatic `setPos()` calls. This broke Qt signal contracts and changed coordinates during workspace projection. A single terminal-to-bus connection could also retain a stale reserved tap offset, creating an avoidable Manhattan jog even when a perpendicular straight drop was available.

## Contract

- Programmatic positioning is exact and never implicitly snapped.
- Grid snapping is applied only while a movable symbol is being dragged with the pointer.
- The drag state is entered in `mousePressEvent` and always cleared in `mouseReleaseEvent`.
- Bus, source, canonical equipment, branch and interactive QET symbols use the workspace grid spacing.
- A terminal may use its orthogonal projection onto the bus axis when its tap does not collide with another terminal projection on that bus.
- When direct projections would collide, the previously assigned bay offsets are retained and the route remains orthogonal.
- Electrical connectivity remains canonical-model data; routing changes only presentation geometry.

## Validation

The unit suite covers exact programmatic positioning, drag-only snapping, configurable spacing, continuous movement with Snap disabled, collision-aware direct tap selection and straight perpendicular drops. Qt integration signal tests remain unchanged and must continue to pass on a PySide6 environment.
