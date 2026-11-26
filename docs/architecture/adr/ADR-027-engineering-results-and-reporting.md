# ADR-027: Engineering Results and Reporting Boundary

- Status: Accepted
- Date: 2026-11-22
- Increment: ND-015

## Context

The project directive requires phase currents, faulted-system voltages, per-source
contributions, branch/transformer currents, bus and line-interior locations, PDF/Excel
reports, and CSV/JSON export. The current domain result contracts already carry the bus
fault phase/sequence phasors, IEC quantity availability, source contribution analysis,
and both terminal current states for interior-line faults. They do not carry a complete
network-wide branch-current or transformer-winding-current solution.

## Decision

1. Normalize existing solver outputs into immutable, unit-labelled result records under
   `power_fault_analyzer.results`.
2. Keep PDF, Excel, CSV, and JSON I/O under `power_fault_analyzer.reporting`.
3. Make report generation a projection only: no electrical quantity is recalculated by
   exporters.
4. Preserve complex phasors as real/imaginary values with derived magnitude and angle.
5. Preserve IEC availability and method provenance. Unavailable quantities must not be
   represented by zero.
6. Include source contributions only from an explicit matching source-analysis result.
7. Include terminal-current records only when supplied by `LineFaultStudyResult`.
8. Mark network-wide branch currents and transformer through-currents as unavailable until
   the numerical engine supplies them. Do not infer them from Ybus without branch primitive
   and connection models.
9. Keep PDF and XLSX libraries as an optional `reports` dependency extra. JSON and CSV
   remain standard-library operations.

## Consequences

- Solver, domain, and reporting responsibilities remain separated.
- Reports are reproducible and machine-readable, with explicit units and scope warnings.
- ND-015 provides the documented output pipeline but does not falsely claim completion of
  missing branch/transformer current calculations. Those remain an upstream solver task.
- The standard edition and each quantity's availability are retained in every export.
