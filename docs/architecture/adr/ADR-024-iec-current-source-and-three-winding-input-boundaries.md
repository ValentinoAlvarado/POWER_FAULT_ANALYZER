# ADR-024 — IEC current-source and three-winding transformer input boundaries

- **Status:** Accepted for ND-014.3 data contracts; normative numerical policies remain deferred.
- **Date:** 2026-11-22
- **Standard target:** IEC 60909-0:2026, Edition 3.0

## Context

The IEC study domain distinguishes voltage-source contributions from current-source
installations. The generic academic solver also has a fixed sequence-current command for
converter studies. These representations may carry similar phasors, but they do not have the
same derivation, applicability rules or normative provenance. Three-winding transformer
correction also depends on nameplate and test data plus a defensible zero-sequence connection
model; pairwise leakage impedances alone do not define the complete zero-sequence behavior.

The project is not currently supplied with the licensed final text needed to implement and verify
the exact Edition 3.0 coefficients, applicability limits and exceptions for these procedures.

## Decision

1. **Keep IEC current-source input separate.** `IEC60909CurrentSourceInput` stores explicit
   positive-, negative- and zero-sequence current entries in kA, source family, rated voltage,
   data reference, method reference and standard edition. Each sequence key is mandatory;
   `None` means unspecified, while `0j` means zero was explicitly established. Per-unit
   conversion requires an `ElectricalImpedanceBase` whose voltage base matches the declared
   source voltage. No implicit adapter from `ConverterSequenceCurrentCommand` is provided.
2. **Model induction motors as physical equipment.** `InductionMotor` uses explicitly supplied
   sequence impedances, prefault voltage, stator connection and neutral grounding. It contributes
   only the initial sequence equivalent at this stage. Missing or open zero-sequence return paths
   remain blocked; delta stator connection does not acquire an inferred neutral path.
3. **Gate three-winding transformer correction on completeness.**
   `IEC60909ThreeWindingTransformerCorrectionInput.from_equipment` reports missing pairwise test
   provenance and/or an explicit three-port zero-sequence model. A ready snapshot preserves the
   equipment's nameplate ratings and references, but does not calculate a correction factor.
4. **Do not invent normative numbers.** Current-source phasor derivation and the three-winding
   correction coefficient remain deferred until their exact clauses, equations, inputs,
   applicability and exceptions are mapped from the licensed final standard and independently
   checked.

## Consequences

- The generic fixed-phasor command and the IEC current-source contract remain distinct APIs.
- A current-source input cannot be accepted for the wrong source ID, family, service state,
  source mode or standard edition; fault-required sequence values cannot be left unspecified.
- Induction motors are represented in the sequence-network builder as asynchronous-machine
  voltage sources, but this does not imply completion of all IEC motor current quantities.
- A three-winding transformer can be reported as data-ready for a future policy without implying
  that a correction factor has been computed.
- The existing IEC numerical calculator continues to reject unsupported current-source and
  three-winding correction cases until their numerical policies are implemented and verified.

## Verification boundary

ND-014.3 unit tests verify contracts, input completeness, base conversion, sequence-network
integration and safe rejection. They do not prove electrical-model accuracy, calculate normative
correction factors or establish IEC conformity. Independent engineering benchmarks remain a
separate acceptance gate.
