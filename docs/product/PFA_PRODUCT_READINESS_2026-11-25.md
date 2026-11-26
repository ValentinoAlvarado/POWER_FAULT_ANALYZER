# POWER_FAULT_ANALYZER — Product Readiness and Scope

**Snapshot date:** 2026-11-25  
**Integrated baseline:** PFA-WORKBENCH-004.2.3.1 + PFA-KEYBOARD-002 + PFA-SYMBOLS-001  
**Status:** Engineering preview / source-run desktop application. Not a complete commercial power-system suite.

## Available now

- Native PySide6 desktop Workbench runnable from the Python 3.13 environment.
- Canonical network aggregate with buses, equipment, terminals, explicit terminal-to-bus connections and structural validation.
- JSON project document (`.pfa`) plus network/diagram sidecar (`.pfa.network.json`).
- Diagram canvas with bus/equipment rendering, explicit terminal identity, perpendicular bays, shortest orthogonal routing and editable label placements.
- Transactional workspace command facade, identity-preserving rollback and event publication.
- Property inspector for the implemented editable object subset; validation occurs before command history mutation.
- Canvas keyboard shortcuts: undo/redo, select all, delete, escape, nudge, rotation for compatible items, zoom, grid/snap, inspector focus, file commands, study and export commands.
- Transformer two-winding symbol uses a shared parametric primitive definition for Qt and SVG. PDF is generated through the SVG exporter. Reference descriptor is IEC 60617 S00841 Form 1; dimensional/normative conformance remains `NOT_VERIFIED`.
- Symmetrical-component short-circuit studies for supported three-phase, line-to-ground, line-to-line and double-line-to-ground cases, including supported line-interior fault cases.
- A restricted IEC 60909-0:2026 network-feeder calculation path. It is explicitly not full IEC 60909 compliance.
- Protection calculation components for supported CT, relay, fuse, breaker-duty and conductor thermal checks, with stated input and coverage limits.
- PDF/Excel/CSV/JSON report/export facilities for supported result objects.

## Not complete / not to be represented as available

1. **No AC or DC load-flow study.** Ybus construction is infrastructure, not a Newton–Raphson, fast-decoupled or DC load-flow solver. No OPF, economic dispatch or N-1/N-k contingency study is present in this snapshot.
2. **No complete equipment workflow.** Domain classes exist for selected lines, cables, two-/three-winding transformers, source types, motors and switching equipment, but the desktop palette, editor, persistence adapter and analysis support do not yet cover every class end-to-end. The `equipment/loads` package contains no implemented load model.
3. **Topology model remains partial.** `BusKind` distinguishes busbars and connection nodes, but an independent connectivity-node model, complete multi-terminal equipment and full switch-disconnector topology semantics are not finished.
4. **IEC 60909 is restricted.** The supported network-feeder method rejects or omits multiple unsupported source, mesh, machine/converter and three-winding correction cases. Do not claim full standard compliance.
5. **Symbol library is partial.** Candidate QET elements and the PFA-authored transformer symbol have provenance, but the entire library has not been checked symbol-by-symbol against the applicable IEC 60617 edition. `NOT_VERIFIED` stays visible.
6. **Interchange is incomplete.** No complete CIM/CGMES, PSS/E RAW/DYR, MATPOWER, PowerWorld project or COMTRADE round-trip is established.
7. **Public binary release is not yet built.** The project license is GPL-3.0-or-later. The repository preparation includes a Windows PyInstaller + NSIS release workflow, but no installer may be advertised until the first tagged GitHub Actions run passes and any `NOASSERTION` dependency-license inventory entries are reviewed. The initial installer will be unsigned; Windows may show SmartScreen/unknown-publisher warnings.
8. **Persistence is split across two files.** Project metadata is `.pfa`; network and diagram document is `.pfa.network.json`. There is no multi-file transactional commit, autosave/recovery history, multi-sheet project model or collaborative revision service.

## Launch (Windows)

Run ``RUN_PFA_WINDOWS.ps1`` from PowerShell after creating `.venv` with Python 3.13 and installing `.[dev,desktop,reports]`.

Equivalent direct command:

```powershell
$env:PYTHONPATH = (Get-Location).Path + '\src'
& '.\.venv\Scripts\python.exe' -m power_fault_analyzer.interfaces.desktop.app
```

## Verification

The integrated source snapshot is tested in the build environment with `pytest` and `compileall`. Qt runtime acceptance must be run on Windows because the build container used for this snapshot does not have PySide6. The Windows release gate runs the transaction, property-editor, route, keyboard and transformer-symbol Qt checks on the GitHub Windows runner.

## Acceptance principle

A feature is `IMPLEMENTED` only when its model, domain validation, editing UI, persistence, rendering and relevant study path exist and are tested. A symbol drawing or a domain class alone does not make an equipment workflow complete.
