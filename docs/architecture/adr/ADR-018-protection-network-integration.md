# ADR-018 — Protection network integration

- **Status:** Accepted
- **Increment:** ND-010

## Context

ND-009 implemented protection-device response and duty evaluators independently of physical network topology. To assess a protection scheme, device CT locations must be tied to actual branch terminals, faults must be generated from the network, and the resulting sequence-network branch currents must be supplied to the relay/fuse models.

## Decision

Introduce an immutable protection-network model with explicit device bindings, protection zones and backup relationships. A topology builder validates equipment/terminal ownership, terminal connectivity and zone references. A scenario catalog creates deterministic bus and interior-line locations. A study runner orchestrates ND-008 bus-fault cases and adapts ND-007 line-fault terminal currents. A current extractor reconstructs branch terminal currents from sparse sequence-network nodal states.

For IEC 60909 studies, `IEC60909StudyResult` retains the exact corrected `SequenceNetworkSet` used by the calculation. This prevents protection-current reconstruction from silently using uncorrected networks after a transformer or line correction has been applied.

## Consequences

- Protection device settings and zone boundaries remain explicit engineer-provided inputs.
- A relay CT/fuse element is connected to a specific monitored equipment terminal and the builder resolves it to a physical bus. Interrupting-device rated voltage must not be below the monitored bus nominal voltage; multiple protection relays may reference the same physical breaker.
- The automatic extraction model currently accepts transmission and transformer branch equipment only. Other equipment current models require dedicated sequence-element current contracts before being supported.
- Bus-fault current extraction can evaluate the full branch-current state from the solved sequence networks.
- Interior-line studies map ND-007's two physical line-terminal currents. Remote branch currents are not inferred; supplemental measurements are required for remote backup evaluation.
- Uncovered scenarios, missing current inputs and missing breaker clearing paths remain `FAIL` or `NOT_EVALUATED`, never silently `PASS`.
- The framework does not infer zone boundaries or declare the network protection-compliant.

## Alternatives considered

1. **Infer protection zones from network connectivity.** Rejected because electrical adjacency alone does not define primary/backup boundaries or utility protection philosophy.
2. **Recompute short-circuit equations inside the protection layer.** Rejected because it would duplicate ND-006 through ND-008 and risk inconsistent sequence and IEC corrections.
3. **Require all device currents to be entered manually.** Rejected as the default because bus-fault branch currents can be recovered from the existing sparse Ybus model. Manual supplemental measurements remain available for data not exposed by the current interior-line solver.
