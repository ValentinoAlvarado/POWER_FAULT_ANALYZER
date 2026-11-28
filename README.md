# POWER_FAULT_ANALYZER

[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)

An extensible platform for balanced three-phase power-system short-circuit studies. The project uses Python 3.13.x, object-oriented domain modeling, DDD, and hexagonal architecture. The Windows desktop workbench is built on the application and electrical-domain core intended to support future clients.

## Get the Windows application

For first-time installation, use the **Windows x64 setup executable** from the project's [GitHub Releases](https://github.com/ValentinoAlvarado/POWER_FAULT_ANALYZER/releases). The planned `PFA-Setup-x64.exe` is a per-user installer: it installs the desktop application under the current Windows user's profile and creates Start Menu and Desktop shortcuts. End users do not need PyCharm, Python or a source checkout.

After installation, the application can check GitHub Releases at startup and through **Help → Check for Updates…**. When a newer complete release is available, PFA asks before downloading, verifies the update payload, preserves projects and preferences outside the application directory, replaces the installed application in place and restarts. The previous application folder is retained as a rollback copy.

The `PFA-Windows-x64.zip` is the portable onedir package and the payload used for in-app updates. It is also available to users who prefer a portable folder instead of a setup wizard.

A public download is activated only after a tagged release passes the Windows build, test, license-review and artifact-verification gates. Until then, the Releases page may contain no verified installer.

## Source code and contributions

The source repository is public under GPL-3.0-or-later. Anyone can inspect it, fork it, modify a feature, build a development version and submit improvements through a pull request. Installing the Windows application does not include the development toolchain; contributors who want to change PFA itself should follow the source environment and test instructions below.

## Current implementation

Implemented foundations:

- Immutable value objects: `Voltage`, `Connection`, and `DomainDiagnostic`.
- Per-unit base quantities and impedance conversions.
- Structural contracts (`Protocol`) for electrical elements, buses, equipment, and validation services.
- Immutable `Bus` and `Terminal` entities.
- Equipment base classes enforcing two- and three-terminal cardinality.
- `Network` aggregate root with UUID indexes, unique naming, connection integrity, voltage-compatibility policy, and controlled deletion.
- `DefaultNetworkValidationService` for structural and initial calculation-readiness checks.
- Branch domain abstraction with exact two-terminal cardinality.
- Immutable complex impedance/admittance values and per-kilometre sequence parameter sets.
- Generic `Line`, specialized `OverheadLine` and `UndergroundCable`, and lumped `SeriesReactance`.
- Series-only and nominal-pi branch equivalents for positive, negative, and zero sequence.
- Explicit reference frequency and conductor/cable construction metadata.
- Single-terminal source equipment: external grid, explicit equivalent source, synchronous generator, induction generator, and converter-based generator.
- Sequence-aware source-equivalent contracts with explicit AVAILABLE / BLOCKED / UNSPECIFIED statuses.
- Synchronous-machine subtransient, transient, and synchronous positive-sequence impedance regimes.
- Grounding-aware generator zero-sequence equivalents, including the physical 3Zn contribution.
- Converter current-limit capabilities with an explicit per-unit current base; converter sources are not misrepresented as fixed Thevenin impedances.
- Per-bus voltage bases under one common three-phase MVA system base.
- Positive-, negative- and zero-sequence network construction from lines, sources and supported transformer connection configurations.
- Two-winding transformer phase-shifting taps with conjugate positive/negative sequence orientation.
- Three-winding positive/negative sequence star equivalents with deterministic auxiliary nodes, plus an explicit reciprocal zero-sequence three-port matrix when manufacturer/test/validated data is available; no zero-sequence equivalent is inferred from pairwise leakage data.
- Sparse CSR Ybus assembly with branch π stamps, transformer taps, shunts and Thevenin Norton injections.
- Sparse-LU driving-point Thevenin reduction at a selected bus.
- Bus-fault calculations for three-phase, A-G, B-C and B-C-G faults, including complex fault impedance.
- Interior transmission-line and underground-cable fault locations through immutable sequence-branch splitting.
- Sequence voltage recovery and phase current/voltage results at both physical line terminals.
- Sequence and phase-domain fault currents and voltages in p.u., kA and line-to-neutral kV.
- IEC 60909-0:2026 restricted network-feeder study path for bolted bus faults, voltage factors, two-winding transformer corrections, radial peak current and thermal equivalents.
- Immutable current-transformer ratios and phase/earth overcurrent relays with IEC standard, very, extremely and long-time inverse 51 curves and an optional instantaneous 50 stage.
- Manufacturer-entered fuse pre-arcing and total-clearing time-current characteristics with log-log interpolation and no extrapolation outside the supplied range.
- Circuit-breaker voltage, Icu, Ics, Icm and Icw duty checks against available IEC 60909 study quantities.
- Conductor adiabatic thermal-withstand checks using explicit engineer-supplied k-factors and cross-sectional areas.
- Relay minimum-fault sensitivity and sampled relay-relay / fuse-relay time coordination using explicit project margins.
- Topology-bound relay/fuse CT locations on transmission and transformer terminals, explicit protection zones, primary devices and directional backup relationships.
- Reproducible bus maximum/minimum and interior-line fault scenario catalogs, with sequence-network branch-current recovery for bus faults and ND-007 terminal-current mapping for interior-line faults.
- Primary-zone coverage, backup coordination-margin assessment and explicit uncovered-location diagnostics with PASS / FAIL / NOT_EVALUATED outcomes.
- Sequence-topology diagnostics, explicit unsupported-model diagnostics and sparse LU factorization with singularity errors.

ND-006 adds bus-level short-circuit calculations using sparse Thevenin reduction and sequence-network fault interconnections. ND-007 extends these calculations to interior points of transmission lines and underground cables. The line is identified by equipment UUID, the location is a fraction measured from its FROM terminal, and the solver reports sequence and phase currents/voltages at the fault point and both line terminals. ND-008 adds a separate, restricted IEC 60909-0:2026 path for bolted bus faults supplied by exactly one ExternalGrid network feeder. It includes supported voltage factors, two-winding transformer correction, explicit 50/60 Hz selection, separate engineer-supplied positive/negative and zero-sequence minimum-case line resistance factors, initial symmetrical currents for the four sequence fault types, and radial maximum three-phase peak/thermal quantities. ND-008 is not a full IEC 60909 implementation or a compliance declaration: machine/converter contributions, multiple feeds, meshed peak-current methods, three-winding corrections, line-interior IEC studies and several other standard cases remain unsupported and are rejected or omitted explicitly. ND-009 adds a separate protection layer for 50/51 overcurrent relays, CT ratios, fuse curves, breaker ratings, adiabatic conductor withstand, sensitivity and sampled selectivity checks. It requires manufacturer and project-specific inputs and does not claim full IEC device-standard compliance. ND-013 adds an optional measured/vendor-derived zero-sequence three-port model for three-winding transformers; without it, the zero-sequence network remains explicitly incomplete. Converter sources remain current-capability models rather than fixed Thevenin impedances; a bus-fault study can include one only when an explicit fixed sequence-current command is supplied and validated.


## Environment

Requires Python 3.13.x.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Optional components:

```powershell
pip install -e ".[notebook]"
pip install -e ".[desktop,reports]"
pip install -e ".[desktop,reports,cad]"          # DXF interchange dependency
pip install -e ".[desktop,reports,visualization3d]" # optional 3D stack
pip install -e ".[api]"
```

## Tests

```powershell
python -m pytest tests/unit -v
```

## Network domain example

```python
from uuid import uuid4

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.electrical_equipment import (
    TwoTerminalEquipmentBase,
)
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.voltage import Voltage


class DemonstrationBranch(TwoTerminalEquipmentBase):
    def __init__(self) -> None:
        equipment_id = uuid4()
        voltage = Voltage.from_kv(13.8)
        super().__init__(
            id=equipment_id,
            name="LINE-01",
            terminals=(
                Terminal(equipment_id, "FROM", voltage),
                Terminal(equipment_id, "TO", voltage),
            ),
            family=EquipmentFamily.TRANSMISSION,
        )


network = Network("Three-bus study")
bus_a = Bus("BUS-01", Voltage.from_kv(13.8))
bus_b = Bus("BUS-02", Voltage.from_kv(13.8))
line = DemonstrationBranch()

network.add_bus(bus_a)
network.add_bus(bus_b)
network.add_equipment(line)
network.connect(line.terminal_from.id, bus_a.id)
network.connect(line.terminal_to.id, bus_b.id)
```

## Technical documentation

See `docs/architecture/ND-001-network-domain.md` for the network-domain contract, `docs/engineering/sequence_network_model.md` for ND-005 sequence-network and sparse-Ybus behavior, `docs/engineering/short_circuit_bus_faults.md` for ND-006 bus-fault equations, and `docs/engineering/short_circuit_line_faults.md` for ND-007 interior-line fault modeling, and `docs/engineering/iec_60909_network_feeder.md` for the ND-008 standards-oriented subset.


## ND-006 — Bus short-circuit solver

See [`docs/engineering/short_circuit_bus_faults.md`](docs/engineering/short_circuit_bus_faults.md) for equations, fault-impedance conventions, result units, numerical safeguards and limitations. The architectural decision is recorded in [`ADR-014`](docs/architecture/adr/ADR-014-bus-short-circuit-solver.md).

## ND-007 — Interior-line fault solver

See [`docs/engineering/short_circuit_line_faults.md`](docs/engineering/short_circuit_line_faults.md) for fault-location conventions, immutable topology splitting, terminal current equations, result fields and limitations. The architectural decision is recorded in [`ADR-015`](docs/architecture/adr/ADR-015-line-interior-fault-location.md).


## ND-008 — IEC 60909 network-feeder method

See [`docs/engineering/iec_60909_network_feeder.md`](docs/engineering/iec_60909_network_feeder.md) for the standard edition, supported calculation class, voltage factors, transformer corrections, peak/thermal limitations and usage. The architectural decision is recorded in [`ADR-016`](docs/architecture/adr/ADR-016-iec-60909-network-feeder-method.md). ND-008 is deliberately a restricted IEC 60909-0:2026 network-feeder method, not a full compliance implementation.

## ND-009 — Protection coordination and short-circuit duty

See [`docs/engineering/protection_coordination.md`](docs/engineering/protection_coordination.md) for CT/relay equations, fuse-curve interpolation, standard-separated circuit-breaker ratings (IEC 60947-2 Icu/Ics for LV and IEC 62271-100 rated breaking current for systems above 1 kV), Icm/Icw checks, conductor thermal withstand, coordination margins, required manufacturer data and limitations. The architectural decision is recorded in [`ADR-017`](docs/architecture/adr/ADR-017-protection-coordination-and-duty.md). ND-009 is a protection calculation framework; it does not claim automated setting selection or full IEC protection-standard compliance.


## ND-010 — Protection network integration

See [`docs/engineering/protection_network_integration.md`](docs/engineering/protection_network_integration.md) for device-to-terminal bindings, explicit zone boundaries, scenario generation, sequence-network branch-current reconstruction, interior-line measurement limits and protection-coverage assessment. The architectural decision is recorded in [`ADR-018`](docs/architecture/adr/ADR-018-protection-network-integration.md). ND-010 supports automatic current extraction for transmission and transformer branches, but not source/load/switching current models; interior-line scenarios use ND-007 rather than IEC 60909, and remote backup currents require supplemental measurements until a network-wide post-fault branch-current result is available.

## ND-011 — Advanced protection functions

ND-011 adds a separate phasor-based protection layer for two-terminal biased differential 87L/87T, directional supervision 67/67N around an existing 50/51 relay, MHO/quadrilateral distance 21, and a steady-state AC CT excitation/burden screen. Advanced functions bind to an existing ND-010 protection zone and physical element; CT performance models bind to a known 50/51 CT with a matching ratio. The engineer supplies vector compensation, polarizing phasors, distance loops/zones and CT test data explicitly. Missing inputs return NOT_EVALUATED. Transient CT saturation, automatic vector-group compensation, full line differential standard conformance, memory polarization, load encroachment, power-swing blocking and teleprotection remain outside this increment.

See [`docs/engineering/advanced_protection_functions.md`](docs/engineering/advanced_protection_functions.md) for equations, phasor conventions, required data, standards context and explicit exclusions. The architectural decision is recorded in [`ADR-019`](docs/architecture/adr/ADR-019-advanced-protection-functions.md).


## ND-012 — Transient CT and protection dynamics

ND-012 adds a time-domain CT flux-linkage ODE driven by the existing manufacturer excitation curve, explicit remanent-flux initial condition, engineer-supplied exponential DC offset and burden impedance. The sampled 50/51 evaluator uses a sliding RMS window and accumulates the existing IEC inverse-time characteristic, with explicit dropout ratio, reset time constant and output delay. The breaker evaluator estimates per-pole contact separation and first natural current-zero interruption from supplied three-phase current waveforms. The CT magnetization curve is single-valued (no hysteresis/eddy-current model), curve-domain overrun is NOT_EVALUATED, relay sampling is an ideal numerical approximation rather than vendor firmware emulation, and breaker interruption omits arc conductance/TRV/restrike.

See [`docs/engineering/transient_protection_dynamics.md`](docs/engineering/transient_protection_dynamics.md) for the ODE, assumptions, inputs, statuses and limitations. The architectural decision is recorded in [`ADR-020`](docs/architecture/adr/ADR-020-transient-protection-dynamics.md).


## ND-013 — Advanced power-system sequence models

ND-013 adds an explicit manufacturer/test/validated-model three-port zero-sequence impedance equivalent for three-winding transformers; mutual sequence impedance between two parallel line branches; independent Norton-source voltage contribution reporting; and fixed sequence-current commands for converter-interfaced sources, validated against their registered physical bus and current capability. The three-winding zero-sequence equivalent is never inferred from pairwise leakage data. Mutual coupling is provided in per unit and is not derived from conductor geometry. Converter commands are explicit fixed phasors, not a PLL/grid-forming control or IEC 60909 converter model. The bus-fault solver applies these fixed injections through the sequence-network nodal equations; it does not calculate the converter's command from its control system or simulate its dynamic current response.

See [`docs/engineering/advanced_sequence_models.md`](docs/engineering/advanced_sequence_models.md) for the matrix formulations, base conversions, required manufacturer/line-constant data, API examples and exclusions. The architectural decision is recorded in [`ADR-021`](docs/architecture/adr/ADR-021-advanced-power-system-sequence-models.md).

## Desktop Engineering Workbench (APP-REBOOT-001)

The PySide6 client is being rebuilt as a dockable engineering workbench. The current increment provides a physical network editor for AC buses, explicit Thevenin equivalent sources, synchronous generators and series transmission lines; a separate drawing-layout model; project/network JSON persistence; topology validation; asynchronous network short-circuit execution through the existing `ShortCircuitSolver`; phase/sequence result tables; a scientifically plotted phase-current phasor diagram; and engineering report export. Unsupported equipment and studies are identified in the UI rather than represented as implemented.

Install and verify the desktop application on Windows with:

```powershell
python -m pip install -e ".[dev,desktop,reports]"
.\scripts\verify_app_reboot_001.ps1 -SkipInstall
python -m power_fault_analyzer.interfaces.desktop.app
```

See `docs/engineering/APP-REBOOT-001-engineering-workbench.md` for implemented scope, limitations and validation evidence.

## Desktop application and releases

POWER_FAULT_ANALYZER is distributed as a native Windows desktop engineering application. The website in `website/` is the public download and release front door; it does not replace the native editor. The configured Windows release workflow builds a portable PyInstaller ZIP bundle and its SBOM, dependency-license inventory, third-party notices, build metadata and SHA-256 checksums; it does not produce an MSI/NSIS installer. The project source license is GPL-3.0-or-later, while third-party components retain their own terms. A successful clean-run GitHub Actions build and downloadable Windows artifact have not yet been accepted, so the public download page remains inactive until a GitHub Release contains `PFA-Windows-x64.zip`. See [Desktop distribution and releases](docs/product/DISTRIBUTION_AND_RELEASES.md) for the release contract and gates.


## Desktop iconography and engineering asset libraries

The desktop profile includes QtAwesome for a consistent icon system, PyQtGraph for interactive engineering plots, and QtSvg for vector rendering. QElectroTech source elements are managed through the pinned, hash-verified acquisition workflow in `scripts/Acquire-QElectroTechSymbolSeed.ps1`; they remain provenance-bearing candidates until normative and terminal mappings are verified. Optional `cad` and `visualization3d` extras provide DXF and 3D visualization dependencies. Their presence does not claim those workflows are already implemented. See `docs/engineering/OPEN_SOURCE_UI_AND_ENGINEERING_LIBRARIES.md` and `docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md`.

## Desktop Workbench — consolidated controls and symbols

The current engineering preview also includes a transactional property inspector, canvas-scoped keyboard shortcuts and the shared PFA transformer symbol catalogue. See:

- [`PFA-KEYBOARD-001`](docs/architecture/PFA-KEYBOARD-001-WORKBENCH-SHORTCUTS.md)
- [`PFA-SYMBOLS-001`](docs/engineering/PFA-SYMBOLS-001-transformer-two-winding.md)
- [Product readiness, scope and known limitations](docs/product/PFA_PRODUCT_READINESS_2026-11-25.md)

On Windows, run `RUN_PFA_WINDOWS.ps1` from the repository root after installing the `dev`, `desktop` and `reports` extras into `.venv`.
