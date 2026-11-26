# PFA-WORKBENCH-004.2.2 — Stable Equipment Label Identity

## Defect

The 004.2.1 Qt acceptance script located a generated equipment label by matching
`EngineeringLabel.text` to `equipment.name`. That assumption is invalid because
the projection intentionally decorates the visible label with `†` or `‡` when
its equipment has unresolved or partial engineering data.

The generated label itself was correctly assigned a deterministic UUID using
`urn:pfa:diagram-label:{equipment_id}:equipment-name`, and the inspector used
that identity. The test therefore failed before exercising the editor's label
transaction, despite the application having a valid label.

## Correction

- The Qt acceptance script resolves the generated label by its deterministic
  `label_id`, then verifies `owner_id` separately.
- Undo is expected to restore the exact projected base label text, including
  the engineering status marker; it no longer assumes the visible text must be
  identical to the canonical equipment name.
- Added a non-Qt integration regression test proving that label identity is
  stable independently of visible status decoration.

## Invariants

- Equipment UUID and canonical equipment name remain unchanged by presentation
  label edits.
- The label UUID remains stable across display-text changes.
- Status decoration remains part of the generated base label and is restored
  exactly when an override is undone.
- Editing and undo/redo continue through the established workspace command bus.

## Verification boundary

The non-Qt pytest regression runs in the build environment. The offscreen Qt
acceptance script still must execute in the target Windows virtual environment.
