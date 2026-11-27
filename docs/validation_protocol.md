# POWER_FAULT_ANALYZER — Electrical and Desktop Validation Protocol

**Protocol status:** Defined; execution and evidence register still to be completed.  
**Applies to:** numerical domain, equipment/topology models, protection calculations, desktop workbench and Windows distribution.  
**Rule:** a passing software test is evidence for the behavior it actually tests. It is not, by itself, independent electrical validation, standards conformity, visual acceptance or release acceptance.

## 1. Validation levels

Record every result under one of these levels; do not merge them into one PASS label.

| Level | Meaning | Minimum evidence |
|---|---|---|
| L1 — Software test | Unit, integration or regression behavior | Test ID, code revision, environment, command and result |
| L2 — Analytical verification | Agreement with a hand-derived or independently derived solution | Equations, declared assumptions, input data, expected values and tolerance |
| L3 — Independent benchmark | Agreement with a separate engineering program, published worked example or independently prepared reference dataset | Original native/export evidence, tool/version, settings, source files, comparison table and discrepancy analysis |
| L4 — Engineering acceptance | End-to-end workflow and engineering interpretation are usable and reproducible | Reviewed project, rendered diagram, input/output report, save/reopen result and signed checklist |
| L5 — Release acceptance | Packaged application operates outside the development environment | Successful CI run, artifact/checksum inspection, clean-machine launch, license notices and release record |

A result at one level must not be presented as completion of a higher level.

## 2. Required record for every benchmark

Each benchmark record must contain:

1. Unique benchmark ID and revision.
2. Purpose and calculation category.
3. Independent source and provenance: standard clause/worked example, textbook, manufacturer data, hand derivation or external software export.
4. Source-file identity and SHA-256 where files are available.
5. Software/tool version, calculation options, system frequency and all assumptions.
6. Complete network/equipment input, bases, topology, sequence parameters, grounding and fault specification.
7. Reference result with units, sign convention, current direction, phase order and precision.
8. PFA result from the exact tested commit.
9. Absolute and relative discrepancy, acceptance tolerance and reason for that tolerance.
10. Status: `PASS`, `FAIL`, `NOT_EVALUATED` or `BLOCKED`; reviewer and date.

Do not derive the expected value from the PFA result being tested. If the source does not provide a quantity, mark it `NOT_EVALUATED`; do not fill it with a guessed value.

## 3. Numerical conventions and comparison

- Use one declared three-phase MVA base and explicit voltage bases per bus.
- Record whether a voltage is line-to-line or line-to-neutral, and whether a current is phase, sequence, residual or ground current.
- Preserve the A-B-C phase order and the project convention for positive/negative/zero sequence.
- Record complex quantities as real and imaginary parts, units and reference direction. Do not compare magnitudes alone where phase angle/sign is material.
- Compare quantities using a predeclared criterion of the form  
  `abs(PFA - reference) <= atol + rtol * abs(reference)`.  
  The numerical values of `atol` and `rtol` must be selected per benchmark before running it; there is no universal tolerance for all models.
- Report unrounded internal values for comparison. Round only for presentation after the acceptance calculation.
- Verify sensitivity to input precision, fault impedance, line length, transformer ratio/tap, frequency and relevant model options.

## 4. Electrical validation matrix

### 4.1 Base quantities and per-unit conversion

Test:
- Three-phase impedance base (Z_{base}=V_{LL,base}^{2}/S_{3phi,base}).
- Current base (I_{base}=S_{3phi,base}/(sqrt{3}V_{LL,base})).
- Conversion between ohms and per unit at multiple voltage levels.
- Consistent conversion of line-to-line and line-to-neutral voltage quantities.
- Rejection of non-finite, zero or physically invalid bases.

Acceptance evidence: hand-calculated reference cases with units and dimensional checks.

### 4.2 Network topology and sequence networks

Test:
- Bus/equipment/terminal identity and unique naming.
- Open terminals, duplicate connections, invalid cardinality and incompatible voltage levels.
- Positive-, negative- and zero-sequence branch/shunt assembly.
- Series-only and nominal-π branch stamping, transformer taps and shunts.
- Transformer vector-group/grounding behavior, including explicit unsupported zero-sequence cases.
- Three-winding zero-sequence equivalents only when a validated manufacturer/test three-port matrix is supplied.
- Sparse Ybus symmetry/reciprocity properties where the modeled element requires them, and expected asymmetry where an explicitly modeled phase-shifting element requires it.
- Singular or disconnected networks must return an explicit diagnostic, never a fabricated finite result.

Acceptance evidence: independently assembled small matrices and hand-computed nodal solutions.

### 4.3 Bus short-circuit solver (ND-006)

For every fault type, create an independent reference case:

| Fault | Required reference checks |
|---|---|
| Three-phase | Positive-sequence current, phase balance, zero/negative sequence equal to zero |
| A-G | (I_0=I_1=I_2), phase currents, residual current (3I_0) |
| B-C | (I_0=0), (I_2=-I_1), unfaulted-phase current and faulted-phase boundary |
| B-C-G | (I_A=0), (V_B=V_C), ground impedance boundary and (3I_0) |

For each category, include:
- Bolted fault and non-zero complex fault impedance.
- At least one single-source analytical case.
- At least one multi-bus sequence-network case.
- Phase/sequence reconstruction and voltage/current base conversions.
- Singular, missing-required-sequence and unsupported converter cases.

Acceptance evidence: closed-form sequence equations and independent phase-domain boundary checks. A test that only compares the solver with itself is not an independent benchmark.

### 4.4 Interior line/cable faults (ND-007)

Test locations at multiple interior fractions, including points near both ends and the midpoint. For each supported fault type:
- Verify that the original sequence network is not mutated.
- Verify left/right impedance scaling and physical distance from the FROM terminal.
- Verify that terminal shunts remain at physical line terminals.
- Check fault-point sequence and phase boundary conditions.
- Check branch terminal currents with the documented direction convention (both directed from the bus into the line).
- Check current balance at the fault node and across the split branch, including modeled shunts.
- Reject endpoints, non-line branches, inconsistent sequence topology, unsupported taps and invalid length.

Acceptance evidence: an independently assembled split-network model and limiting-case comparison against a bus fault as the location approaches an endpoint. Do not extrapolate the lumped model into distributed-parameter cable/transmission-line behavior.

### 4.5 Restricted IEC 60909-0:2026 path (ND-008)

Validate only the implemented network-feeder subset:
- Declared standard edition and supported voltage factors.
- Single ExternalGrid feeder constraints and explicit 50/60 Hz selection.
- Two-winding transformer correction using the declared nameplate inputs.
- Maximum/minimum case assumptions and engineer-entered sequence resistance factors.
- Three-phase initial symmetrical current.
- Radial maximum three-phase peak and thermal quantities only where the implementation declares them available.
- Explicit rejection/unavailability for multi-feed, meshed peak, unsupported machine/converter contribution, three-winding correction and other excluded cases.

Acceptance evidence: licensed/authorized final-edition worked examples or independently verified reference calculations, with clause-by-clause applicability notes. Do not label ND-008 “IEC 60909 compliant” based only on internal tests or the presence of standard equations.

### 4.6 Protection calculations

Use exact manufacturer curves/ratings and preserve their source:
- CT ratio and excitation/burden inputs.
- 50/51 pickup, time dial and inverse-time curve points.
- Fuse pre-arcing and total-clearing curves; verify interpolation and no extrapolation.
- Breaker Icu/Ics/Icm/Icw ratings against the correct voltage and duty quantities.
- Conductor adiabatic withstand using declared (k), area and clearing time.
- Sensitivity and relay-relay/fuse-relay grading with explicit project margins.
- Protection zones, measurement locations and backup paths.
- ND-011/ND-012 advanced/dynamic features only where input data and validation exist.

Acceptance evidence: manufacturer data sheets, hand calculations and test curves. Do not treat a protection framework as automatic relay-setting selection or full device-standard certification.

## 5. Desktop engineering acceptance

Perform on a normal Windows desktop, not only with `QT_QPA_PLATFORM=offscreen`.

1. Launch the workbench; verify visible window, usable viewport, menu/toolbar behavior and no modal startup failure.
2. Create a project with buses, an explicit source and a supported line. Check the physical model and drawing separately.
3. Verify that moving, rotating or deleting a drawing-only symbol cannot alter electrical connectivity.
4. Attempt invalid voltage-level, duplicate-terminal and incomplete-connection operations; verify actionable diagnostics and no partial mutation.
5. Save, close, reopen and compare network IDs, equipment parameters, connections, diagram positions and study settings.
6. Run a supported short-circuit study; compare displayed phase/sequence values with the solver result and a benchmark record.
7. Export PDF/XLSX/CSV/JSON; inspect units, headings, precision, phase order and warnings.
8. Repeat with a project containing unsupported model elements; the UI must show unsupported/not-evaluated states rather than implying the calculation included them.
9. Close the application normally; verify event-loop shutdown and no uncaught Qt/RPC exception.

Visual acceptance requires attached screenshots of representative small, medium and dense networks at their intended zoom levels. Check symbol scale, orthogonal routing, wire-terminal contact, label collisions, clipping, line crossings, z-order, canvas margins, selected-state visibility and print/export layout. A test count is not a visual-quality assessment.

## 6. Windows distribution acceptance

Before publishing a tagged release:

- Run `.github/workflows/windows-release.yml` on the intended branch and retain the successful run URL.
- Confirm Ruff, compileall, full pytest, APP-REBOOT-005 acceptance, PyInstaller packaging and frozen-executable startup all pass on the hosted Windows runner.
- Download the artifact and inspect ZIP contents, executable, required license/notice files, SBOM, dependency-license inventory, build metadata and SHA-256 checksums.
- Extract to a clean Windows x64 environment without the development virtual environment and launch the executable.
- Complete representative create/validate/calculate/save/reopen/export workflows.
- Review each `NOASSERTION` dependency for the exact version and complete `RELEASE_LICENSE_REVIEW.csv`; do not invent license findings.
- Confirm the published release includes the same ZIP and matching checksums. Record whether the binary is unsigned.
- Confirm the website download link activates only after the GitHub Release contains `PFA-Windows-x64.zip`.

## 7. Evidence register template

Create one row per independent case. Keep raw sources/results in a versioned location and link them from the record.

| ID | Area | Independent source | PFA commit | Tolerance | Result | Evidence location | Reviewer/date |
|---|---|---|---|---|---|---|---|
| REF-3PH-001B | Three-phase bus fault | PowerWorld-derived reference; native project/export evidence pending | Record per run | To be declared | NOT_EVALUATED externally until source evidence is archived | Record path/hash | Pending |
| REF-AG-001 | A-G bus fault | Pending independent source | — | — | BLOCKED | — | — |
| REF-BC-001 | B-C bus fault | Pending independent source | — | — | BLOCKED | — | — |
| REF-BCG-001 | B-C-G bus fault | Pending independent source | — | — | BLOCKED | — | — |
| REF-LINE-001 | Interior-line fault | Pending independent source | — | — | BLOCKED | — | — |
| REF-IEC60909-001 | Restricted IEC network-feeder case | Authorized final-edition reference pending | — | — | BLOCKED | — | — |
| REF-PROT-001 | Protection curve/duty | Manufacturer data pending | — | — | BLOCKED | — | — |

The table is a work register, not evidence that these cases have passed. Change a status only when its source, expected result, PFA output and review record are attached.

## 8. Prohibited release and engineering claims

Until the matching evidence exists, do not claim:
- full IEC 60909 or IEC 60617 conformity;
- complete load flow, OPF, contingency, switching or protection-setting workflows;
- universal equipment coverage or interchange compatibility;
- independent validation of every fault category;
- clean-machine Windows compatibility, signed publisher status or installer availability;
- safety-critical suitability as the sole basis for operational switching, protection settings or equipment selection.

This protocol is an engineering quality gate. It does not replace the applicable standards, manufacturer instructions, independent review or the responsible engineer's professional judgment.
