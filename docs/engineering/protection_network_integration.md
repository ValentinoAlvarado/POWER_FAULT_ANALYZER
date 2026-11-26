# ND-010 — Protection network integration

## Purpose

ND-009 introduced relay, fuse, circuit-breaker and conductor-duty evaluators. ND-010 binds those protection devices to the physical network topology, defines protection zones, generates fault-location scenarios and evaluates primary coverage and explicitly declared backup relationships.

ND-010 does not infer protection zones from connectivity. Zone boundaries, primary devices, backup devices and coordination intervals are engineering inputs.

## Domain contracts

- `ProtectionDeviceBinding` places an overcurrent relay CT or fuse element at one physical terminal of a transmission branch or transformer. A relay may reference the physical `CircuitBreaker` it trips; multiple relay functions may legitimately reference the same breaker. A fuse is itself the interrupting device and cannot be bound to a breaker.
- The builder rejects an associated breaker or fuse whose rated voltage is below the monitored bus nominal voltage.
- `ProtectionZone` identifies protected bus/equipment UUIDs, primary device UUIDs and backup device UUIDs. Every backup must have an explicit `ProtectionBackupRelationship` to a primary and a minimum coordination interval.
- `ProtectionNetworkBuilder` resolves terminal ownership and physical bus connectivity, checks that primary devices monitor an element inside their declared zone, and rejects device types whose branch-current models are not yet available.
- `ProtectionScenarioCatalog` creates reproducible bus scenarios for IEC 60909 maximum/minimum cases and interior-line locations. Interior-line scenarios intentionally carry no IEC 60909 current-case label.
- `ProtectionScenarioMeasurements` contains primary RMS phase-current and residual/earth-current magnitudes at each bound device.

## Bus-fault current extraction

For each faulted sequence network, `ProtectionCurrentExtractor` assembles and factorizes sparse Ybus, then recovers the complete nodal voltage vector:

\[
V^{fault}=V^{pre}-Y^{-1}e_k I_k
\]

The prefault vector is scaled to the equivalent prefault voltage returned at the fault bus. When an IEC 60909 study returns corrected sequence networks, those exact networks are used for current extraction so the branch current calculation shares the same transformer and line corrections as the reported fault current.

The branch terminal current is recovered from the complex off-nominal tap stamp. Positive, negative and zero-sequence terminal currents are transformed to phase values. The phase element receives the largest phase RMS magnitude; the earth element receives the magnitude of the residual sum `Ia + Ib + Ic`.

## Interior-line scenarios

For an ND-007 `LineFaultStudyResult`, the extractor assigns the physical terminal current reported at each end of the faulted line to protection devices bound at that terminal. Those currents are directed into the line by the ND-007 contract.

The ND-007 result currently exposes current states at the two ends of the faulted line only. It does not expose a complete post-fault current vector for every remote branch in the network. Therefore, currents for remote backup devices on other equipment must be provided as `supplemental_measurements`; ND-010 will not manufacture them.

Interior-line locations are not IEC 60909 maximum/minimum scenarios. They use the existing ND-007 symmetrical-component solver and must not be presented as IEC 60909 line-fault results.

## Protection evaluation

For each scenario, the analyser:

1. Applies the relevant phase or earth current to each relay or fuse.
2. Adds associated breaker opening and arcing time to a picked-up relay's operating time.
3. Marks a relay without an associated breaker as response-only; complete clearing is not evaluated.
4. Uses manufacturer-entered fuse total-clearing data and does not extrapolate outside the curve points.
5. Evaluates a zone's primary coverage using its explicitly assigned primary devices.
6. Evaluates each declared backup relationship using `t_backup,clear - t_primary,clear` against the required interval.
7. Fails a scenario that lies outside all configured protection zones, revealing unassigned network locations.

Overall statuses have three values: `PASS`, `FAIL`, and `NOT_EVALUATED`. Missing current or clearing-path data is not interpreted as a pass.

## Current implementation boundaries

- Automatic current extraction is currently supported for transmission lines/cables and transformer branches. Source, load, switching, converter, shunt and motor current models are not inferred.
- Bus scenarios use the ND-008 restricted IEC 60909 network-feeder calculator. That calculator still supports one external-grid feeder and a limited equipment model class.
- Interior-line scenarios use ND-007, not IEC 60909.
- Remote current contributions for backup devices outside the faulted line must be supplied explicitly for an interior-line scenario.
- CT saturation, transient remanence, burden, secondary wiring, relay firmware tolerances, directional elements, distance/differential protection and automatic setting optimization are not implemented.
- Zone membership and backup coordination intervals are explicit engineering configuration, not inferred from topology or manufacturer data.

ND-010 is an integration and assessment framework. It does not certify a protection design or replace a utility-approved protection-coordination study.
