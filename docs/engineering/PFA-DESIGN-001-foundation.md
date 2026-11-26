# PFA-DESIGN-001 — Geometry foundation and clean SLD presentation

**Status:** Implemented foundation; not a completed publication-layout engine.

## Defect confirmed from the supplied Workbench capture

The canvas rendered QElectroTech drawing-only source candidates as visible overlays by default. Those assets are library references, not approved electrical equipment. Their source text (including generic `Form 1 / Forme 1` fields) was consequently visible in the engineering drawing even though the electrical model reported one bus and one equipment item.

The canvas already had an explicit candidate-visibility switch and the SVG export temporarily excluded candidates and the grid. The defect was the default/persisted UI state, not the absence of an exclusion path.

## Changes in this increment

- Drawing-only QET candidates now start hidden in the canvas.
- Existing UI profiles are migrated once from the previous candidate-visible default to a clean SLD.
- Reset Workspace now restores the clean SLD state; users can still explicitly enable candidate overlays from View.
- Added a presentation-only geometry module with:
  - family-level baseline envelopes and clearances;
  - validated grid snapping;
  - explicit-terminal orthogonal routing;
  - deterministic row layout;
  - group alignment;
  - deterministic label placement around collision rectangles.
- The geometry module has no dependency on Qt or electrical-domain classes. It cannot create or modify buses, terminals, branches, equipment parameters, or solver inputs.

## Geometry-engine selection

This increment deliberately does not add ELK, Graphviz, or libavoid as runtime dependencies.

- **ELK:** attractive for hierarchical layered graph layout and compound nodes; a future adapter must preserve explicit terminal/port identity and return presentation coordinates only.
- **Graphviz:** mature graph layout and export ecosystem; its general-purpose graph abstractions do not by themselves express PFA's equipment terminal semantics or collision policy.
- **libavoid:** specialized orthogonal connector routing; it is a candidate for a later routing adapter, not a complete diagram composition engine.
- **Current decision:** use a small deterministic, dependency-free geometry kernel for baseline dimensions, snapping, Manhattan routes, alignment and label placement. Do not infer electrical connectivity from crossings or geometry. Evaluate the three engines against the same topology fixtures before selecting an adapter.

This is a scope decision, not a claim that a comparative benchmark has already been run. License/version review and performance/quality benchmarking remain release gates before adding any of these dependencies.

## Explicit limitations

- Baseline symbol envelopes are scene-space drawing dimensions, not physical equipment dimensions and not a claim of IEC 60617 conformity.
- Orthogonal routing currently returns a deterministic two-segment Manhattan route; it is not an obstacle-avoiding multi-branch router.
- Label collision handling accepts caller-supplied obstacle rectangles; it does not yet extract all symbol/text/conductor bounds from the Qt scene.
- Automatic row layout is a deterministic starting layout, not a topology-aware substation layout optimizer.
- Snap-to-terminal and junction/crossing semantics remain separate from this geometry foundation.
- Existing SVG export remains Qt scene rendering; physical paper sizing, PDF vector export, typography embedding/outline policy, title blocks and journal-column presets are not completed here.

## Validation

The new pure-Python geometry tests cover grid snapping, orthogonal route endpoint preservation, deterministic layout, group alignment, label collision avoidance and invalid geometry. The complete available test suite is run as a regression gate; Qt runtime tests require PySide6 and a Windows/Qt environment.
