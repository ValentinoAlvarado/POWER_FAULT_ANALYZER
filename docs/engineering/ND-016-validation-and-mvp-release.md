# ND-016 — Engineering Validation & MVP Release

## Objective

ND-016 establishes reproducible engineering evidence for the supported POWER_FAULT_ANALYZER short-circuit calculation domain. It separates software regression from electrical correctness and from third-party tool equivalence.

## Delivered in this increment

### 1. Closed-form analytical references

Dataset: `PFA-ND016-ANALYTICAL-FAULTS-001`  
File: `data/reference_cases/nd016_analytical_fault_cases.json`  
Packaged runtime copy: `src/power_fault_analyzer/validation/data/nd016_analytical_fault_cases.json`

The dataset contains four deterministic one-bus Thevenin-equivalent cases covering the four canonical fault types:

| Case | Fault | Reference relation |
|---|---|---|
| REF-3PH-001 | Three-phase | `I1 = E1 / (Z1 + Zf)`; `I0 = I2 = 0` |
| REF-SLG-001 | A-G | `I0 = I1 = I2 = E1 / (Z0 + Z1 + Z2 + 3 Zf)` |
| REF-LL-001 | B-C | `I1 = E1 / (Z1 + Z2 + Zf)`; `I2 = -I1`; `I0 = 0` |
| REF-DLG-001 | B-C-G | Closed-form solution of the three sequence-network fault boundary equations |

Each case stores its sequence currents, phase currents in p.u. and kA, ground current and base current. There are 44 individual quantity comparisons in the current runner. Complex comparisons use absolute plus relative tolerances; zero and near-zero expected quantities use the absolute tolerance floor for a finite relative-error metric.

**Reference-basis warning:** these are academic closed-form symmetrical-component references. They are not IEC 60909 normative benchmark values, are not manufacturer test cases, and are not measurements from an external application.

### 2. Electrical/unit audits

`audit_short_circuit_result()` checks:

- Three-phase base-current identity: `Ibase = Sbase / (sqrt(3) * VLL,base)`.
- Conversion of phase current from p.u. to kA.
- Conversion of phase-neutral voltage from p.u. to kV using `VLL,base / sqrt(3)`.
- Reconstruction of A-B-C phase currents from zero-, positive- and negative-sequence currents.
- Ground-current identity `Ig = 3 I0` and conversion to kA.
- Fault boundary constraints for three-phase, A-G, B-C and B-C-G cases.

The audit reports residual, tolerance, units and pass/fail status per check. Tests deliberately corrupt base current and phase current conversion to confirm that the audit detects inconsistency.

### 3. Sensitivity and refinement

The ND-016 CLI re-solves the three-phase reference case with a scale factor applied to the positive-sequence Thevenin impedance over `[0.90, 0.95, 1.00, 1.05, 1.10]`. The output magnitude must be monotone for this declared passive single-source case.

A centred finite-difference derivative is evaluated at `h = 1e-3` and `h/2`; the relative difference checks derivative refinement. This is a local, deterministic sensitivity check for the specified case, not a global sensitivity guarantee for arbitrary network models.

### 4. Third-party comparison interchange

`load_external_reference()` and `compare_external_reference_document()` support a provenance-labelled JSON export from ETAP, DIgSILENT PowerFactory, PSS/E or another engineering tool. The document must contain:

- `schema_version` = `1.0.0`
- `tool_name`, `tool_version`, `reference_dataset_id`, `case_id`
- `quantities`, with exact supported quantity identifiers, a value and a unit

Complex phasors use `{ "real": ..., "imag": ... }`. Supported identifiers and units are listed in `data/benchmarks/EXTERNAL_REFERENCE_SCHEMA.md`.

No third-party software result was supplied or run while preparing this increment. Consequently the CLI reports `external_tool_comparison.status = not_performed` unless a real external result file is passed with `--external-reference`. The adapter is an interchange mechanism, not evidence of an executed comparison.

### 5. Numerical convergence scope

The bus-fault sequence-network solver uses direct sparse matrix factorization/solution for the supported cases. It does not use an iterative nonlinear load-flow loop. A traditional iteration-count convergence study is therefore **not applicable** to this calculation path. ND-016 instead records closed-form comparison residuals, electrical identity residuals and finite-difference sensitivity refinement. This does not replace conditioning or large-scale numerical stress tests, which remain a separate future validation item.

## Running the validation suite

From the repository root, after installing the package in editable mode:

```powershell
python -m power_fault_analyzer.validation --json outputs/nd016-validation.json
```

Or:

```powershell
python scripts/run_nd016_validation.py --json outputs/nd016-validation.json
```

The optional third-party comparison is:

```powershell
python -m power_fault_analyzer.validation `
  --external-reference data/benchmarks/your-tool-export.json `
  --json outputs/nd016-external-comparison.json
```

The command exits non-zero if an analytical case, electrical audit, sensitivity refinement, or supplied external comparison fails.

## Release and acceptance status

| ND-016 requirement | Current evidence | Status |
|---|---|---|
| Manual analytical cases | Four closed-form cases, 44 quantities | Implemented |
| Independent engineering-tool comparison | JSON interchange exists; no genuine tool output supplied | Pending |
| Sensitivity | Positive-sequence impedance sweep and derivative refinement | Implemented for declared case |
| Convergence | Direct sparse solver; iterative convergence not applicable | Scoped, stress study pending |
| Regression | Existing 496 tests plus ND-016 suite | To be confirmed on Windows |
| Unit/base audit | Per-result unit and boundary audits | Implemented for audited bus-fault results |
| Limitations | Explicit in this document and runtime report | Implemented |
| Installer/executable | Python editable/package CLI entry point only | Pending native executable packaging |

## Explicit non-claims

- Passing Pytest does not certify IEC 60909 compliance.
- The analytical dataset does not validate machine decrement, converter controls, meshed peak-current procedures, or every ND-014 case.
- No ETAP, DIgSILENT PowerFactory or PSS/E benchmark is claimed until a versioned export from an independently configured case is imported and compared.
- This increment does not create network-wide branch currents or transformer winding currents absent from the numerical result contracts.
- It does not create a Windows installer or signed executable.

ND-016 is therefore an executable validation framework with a bounded analytical evidence set. MVP release remains conditional on external-tool comparison, expanded reference coverage and packaging work.
