# POWER_FAULT_ANALYZER — Product Readiness and Scope

**Snapshot date:** 2026-11-26  
**Integrated baseline:** PFA-WORKBENCH-004.2.3.1 + PFA-KEYBOARD-001 + PFA-SYMBOLS-001 + documented APP-REBOOT desktop increments  
**Status:** Engineering preview / source-run Windows desktop workbench. The portable Windows release pipeline is configured, but its clean-run CI artifact has not yet been accepted. This is not a complete commercial power-system suite.

## Available now

- Native PySide6 desktop workbench runnable from the Python 3.13 environment.
- Canonical network aggregate with buses, equipment, terminals, explicit terminal-to-bus connections and structural validation.
- JSON project metadata (`.pfa`) plus a companion network/diagram document (`.pfa.network.json`).
- Diagram canvas with physical equipment rendering, explicit terminal identity, orthogonal routing, editable label placements, grid/snap, zoom and symbol placement.
- Separate physical topology and diagram layout: moving a drawing item does not alter electrical connectivity.
- Transactional workspace operations and diagram-placement undo/redo; physical topology undo/redo is not complete.
- Current desktop insertion workflows for AC buses, explicit Thevenin equivalent sources, synchronous generators and series-only transmission lines.
- Topology validation and voltage-level checks for the supported line insertion workflow.
- Background short-circuit execution through the application use case and existing production solver.
- Phase- and sequence-domain result tables, phase-current phasor plotting, and PDF/XLSX/CSV/JSON export for supported result objects.
- Symmetrical-component short-circuit calculations for supported three-phase, A-G, B-C and B-C-G faults, including supported interior-line/cable locations.
- A restricted IEC 60909-0:2026 network-feeder path. It is not a full IEC 60909 implementation or conformity declaration.
- Protection calculation components for supported CT, 50/51 relay, fuse, breaker-duty and conductor thermal checks, subject to the documented input and coverage limits.
- Pinned QElectroTech source-asset catalogue with 18 candidate symbols in the current APP-REBOOT-005 acceptance smoke. Source-symbol placement is a drawing operation; it does not silently create or modify electrical equipment.
- Root project license and third-party redistribution notices are present. PFA original code is declared GPL-3.0-or-later; external dependencies and assets retain their own licenses.

## Current verification evidence

- The maintainer's Windows environment reported Ruff checks passing, `compileall` passing and **756 pytest tests passing** for the published `product-reboot` repair baseline (`ac721d907fa2d3f805995c40075450b58dc95e9a`).
- The release workflow is configured for Windows x64 / Python 3.13. It runs Ruff lint, compilation, the complete pytest suite, APP-REBOOT-005 offscreen Qt/QElectroTech acceptance, PyInstaller packaging, a frozen-executable startup smoke, SBOM/license inventory generation and SHA-256 verification. Repository-wide Ruff formatting is not a release gate yet: the current formatter audit reports 56 pre-existing files requiring a separate style-only migration.
- APP-REBOOT-005 offscreen acceptance exercises the resizable workbench layout, inspector tabs, empty-canvas guidance, source-symbol preview, insertion/rotation/drag, undo/redo and JSON persistence. It does not establish full IEC symbol conformity or validate electrical topology for every equipment family.
- The frozen-executable smoke starts the packaged executable with Qt offscreen and checks that its process remains alive for six seconds. It is a startup smoke, not a complete interactive GUI acceptance test.
- **No successful clean-run GitHub Actions artifact is recorded as accepted in this snapshot.** A configured workflow is not evidence that the produced ZIP works on a clean Windows machine.
- The external numerical benchmark programme remains incomplete. The existing REF-3PH-001B evidence is a limited case; native PowerWorld project/export/message-log evidence and independent references for the other fault types remain pending.

## Not complete / not to be represented as available

1. **No AC or DC load-flow study.** Ybus construction is infrastructure, not a Newton–Raphson, fast-decoupled or DC load-flow solver. No OPF, economic dispatch or N-1/N-k contingency study is available.
2. **No complete equipment workflow.** The domain contains more equipment models than the desktop can create, edit, persist and analyze end-to-end. The desktop insertion workflow is currently limited to the equipment listed above; loads, shunts, transformers, motors and switching/protection apparatus are not complete desktop workflows.
3. **Topology model remains partial.** A complete connectivity-node model, multi-terminal equipment workflow and full switch-disconnector topology semantics are not finished.
4. **IEC 60909 is restricted.** The supported network-feeder path accepts only documented cases and rejects or omits unsupported source, mesh, machine/converter and three-winding correction cases. Do not claim full-standard compliance.
5. **Symbol library is partial.** The 18 pinned QElectroTech candidates and the PFA transformer symbol do not constitute a symbol-by-symbol review of the applicable IEC 60617 catalogue. Normative mapping/conformance remains `NOT_VERIFIED` unless a specific symbol has its own evidence.
6. **Interchange is incomplete.** No complete CIM/CGMES, PSS/E RAW/DYR, MATPOWER, PowerWorld project or COMTRADE round-trip is established.
7. **Windows binary release is not yet accepted.** The configured pipeline targets a portable ZIP, not an installer. A successful clean-run Actions build, artifact inspection and clean-machine launch have not been recorded. The binary is not code-signed. The website must not imply that a downloadable release exists before the GitHub Release asset is published.
8. **Third-party license review is build-specific.** The release generates an exact Python dependency inventory. Any package reported with unknown/NOASSERTION metadata must be reviewed for that exact version and entered in `RELEASE_LICENSE_REVIEW.csv` before a tagged release can pass the license gate. Do not infer or invent review records.
9. **Persistence remains split across two files.** There is no multi-file transactional commit, autosave/recovery history, multi-sheet project model or collaborative revision service.
10. **Interactive Windows acceptance remains open.** The offscreen Qt tests do not replace manual use of the real window, full event-loop operation, close/shutdown verification and inspection of rendered engineering diagrams on a normal Windows desktop.

## Launch (Windows)

Run `RUN_PFA_WINDOWS.ps1` from PowerShell after creating `.venv` with Python 3.13 and installing `.[dev,desktop,reports]`.

Equivalent direct command:

```powershell
$env:PYTHONPATH = (Get-Location).Path + '\src'
& '.\.venv\Scripts\python.exe' -m power_fault_analyzer.interfaces.desktop.app
```

For the repository's consolidated workbench checks:

```powershell
.\scripts\verify_app_reboot_001.ps1
```

The Windows release workflow performs the separate APP-REBOOT-005/QElectroTech acceptance path and frozen-executable startup smoke.

## Acceptance principle

A feature is `IMPLEMENTED` only when its model, domain validation, editing UI, persistence, rendering and relevant study path exist and are tested. A symbol drawing, domain class, passing unit test or offscreen smoke alone does not make an equipment workflow complete.

A release is `ACCEPTED` only after the Windows workflow succeeds, all artifacts and checksums are inspected, the ZIP is extracted and launched on a clean Windows environment, and the interactive application can complete representative create–validate–calculate–save–reopen–export flows without misleading results.
