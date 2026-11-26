# PFA-ES-002 — Boundary resolution and short-circuit study workflow

**Status:** implemented in source; automated tests and non-Qt smoke scenario pass in the build environment. Windows/Ruff/Qt acceptance must be run with `scripts/verify_pfa_es002.ps1`.

## 1. Scope delivered

PFA-ES-002 connects the PFA-ES-001 double-bus substation template to the existing symmetrical-component short-circuit engine. It replaces the two external placeholders with explicit equipment models, stores entered parameter provenance, executes the four bus-fault types supported by the current solver, and exports a reproducible engineering report.

The delivered workflow is:

1. Build/open a PFA-ES-001 network.
2. Resolve the line boundary into a physical transmission `Line` and a remote `EquivalentSource` (Thevenin equivalent).
3. Resolve the transformer boundary into a `TwoWindingTransformer` and an LV bus.
4. Validate the network and select a physical bus and fault type in the existing study workflow (F5).
5. Execute the current sequence-domain bus-fault solver.
6. Review result quantities/diagnostics and export PDF, XLSX, CSV and JSON report artifacts.
7. Save/reopen the network; line, transformer and source evidence survive JSON schema 1.4 round-trip.

## 2. Resolve an external line boundary

In the Workbench choose **Model → Resolve PFA-ES-001 Boundary Equipment…**, select the transmission-line boundary, and enter:

- Remote bus and line identifiers.
- Line length and reference frequency.
- Positive-, negative- and zero-sequence R+jX per kilometre.
- Remote equivalent identifier, base MVA, prefault positive-sequence voltage, and positive-, negative- and zero-sequence source impedance on that declared base.
- A document/reference string identifying the source of the values (for example a nameplate, test sheet, network model revision, or study document).

The delivered line equivalent is explicitly `SERIES_ONLY`. The use case does not infer line charging, shunt conductance, mutual coupling, transposition, frequency dependence or a distributed-parameter representation. Use a different line model when that data/model is available.

The remote Thevenin equivalent is connected to the newly created remote bus. Its base voltage is the voltage of the original connected boundary; the entered base MVA is retained and converted by the existing base-conversion code as needed.

## 3. Resolve an external transformer boundary

Choose the transformer boundary and enter:

- Transformer identifier, rated MVA, impedance data base MVA and LV line-line rated voltage.
- Frequency, HV and LV winding connections, vector-group clock number.
- Positive-, negative- and zero-sequence leakage R+jX on the explicitly declared base.
- Neutral grounding for each non-delta winding: ungrounded, solidly grounded, or impedance grounded with R+jX.
- A document/reference string for the source of the values.

The existing HV bay voltage is taken from the connected physical bus. The use case creates the LV bus and two winding terminals, then preserves the original boundary equipment ID and HV terminal ID so that existing diagram mappings remain attached to the physical HV connection.

The transformer sequence-network adapter decides the zero-sequence path from the declared winding connections and grounding. It does not assume a path through a delta winding.

## 4. Data provenance and persistence

Every entered parameter is recorded as `USER_CONFIRMED` with the exact source-reference string entered by the engineer. This means the engineer has confirmed the input for the model; it does **not** mean PFA has independently authenticated the document or independently verified the value.

No line, transformer or external-source impedance is pre-populated by the resolution dialogs. The engineer must enter the values explicitly. The automated smoke scenario contains synthetic values labelled `TEST FIXTURE ONLY — NOT REAL ELECTRICAL DATA`; those values are strictly for regression and must never be reused for an actual substation study.

Network document schema 1.4 serializes evidence for line, two-winding transformer and equivalent source equipment. The repository continues to read schemas 1.0, 1.1 and 1.2.

## 5. Topology and solver corrections included

- `SequenceNetwork.bus_node_map` preserves the mapping from physical bus IDs to sequence-node representatives when closed switching equipment merges buses in the sequence graph. A fault can therefore be entered at a physical bus while the numerical network uses the correct merged node; the result retains the original physical bus ID.
- The sparse Thevenin calculator restricts factorization to the electrical connected component containing the fault bus. An unrelated isolated sequence island no longer makes an otherwise solvable fault-point equivalent singular. A singular fault-point component still raises an explicit numerical error.
- Incomplete sequence networks remain blocked before factorization.

## 6. Study method and limitations

This workflow executes the existing generic symmetrical-components bus-fault calculation for the current solver's supported fault types:

- Three-phase.
- Single-line-to-ground.
- Line-to-line.
- Double-line-to-ground.

The solver returns only the quantities implemented by its current result contract, including sequence/phase currents and voltages and the ground current where applicable. Reports include the model assumptions, system base, fault impedance, and recorded equipment input provenance.

**This is not a claim of complete IEC 60909 compliance.** This workflow does not apply IEC 60909 correction factors or its maximum/minimum calculation procedure. It does not calculate line-interior faults, breaker making/breaking duties, thermal/peak withstand quantities, protection coordination, or a validated vendor inverter fault-current control response. It does not claim independently benchmarked equivalence to PowerFactory, ETAP, PowerWorld or PSS®E.

Do not use the synthetic values in tests or smoke scripts to make operational, design, protection-setting, procurement or safety decisions.

## 7. Verification

From the repository root in Windows PowerShell 5.1:

```powershell
& .\scripts\verify_pfa_es002.ps1
```

The verifier runs Ruff lint, Ruff format check, `compileall`, the full repository pytest suite, the PFA-ES-001 Qt offscreen smoke, and the PFA-ES-002 boundary → study → persistence → report-export smoke. It restores the caller's `PYTHONPATH`, `QT_QPA_PLATFORM` and working directory in a `finally` block.

The PFA-ES-002 smoke uses synthetic test fixtures only. Passing automated tests is not a substitute for verifying actual input documents or an independent electrical benchmark.
