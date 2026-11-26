# ADR-017 — Protection coordination and short-circuit duty

- Status: Accepted
- Increment: ND-009

## Context

ND-008 provides supported IEC 60909 short-circuit quantities for a restricted network-feeder model. Engineering studies also need to compare those quantities with protective-device capabilities and check time selectivity. Device characteristics are manufacturer- and project-dependent; inventing generic fuse curves, CT behavior or one universal coordination margin would create false confidence.

## Decision

Introduce immutable domain value objects for current-transformer ratios, IEC inverse-time overcurrent relays with optional instantaneous stage, manufacturer-entered fuse curves, circuit-breaker ratings and adiabatic conductor limits. Circuit-breaker rating fields are separated by standard family: IEC 60947-2 Icu/Ics is restricted to the LV domain up to 1 kV AC, while IEC 62271-100 rated short-circuit breaking current is used above 1 kV AC. The model rejects mixed rating families. Implement numerical services separately for:

1. Relay/fuse time-current evaluation and sampled coordination.
2. Breaker voltage, interrupting, making and short-time withstand checks.
3. Conductor adiabatic Joule-integral checks.
4. Relay minimum-fault sensitivity ratio checks.

Require all fuse curve points, CT settings, breaker ratings, clearing times, conductor k-factor and desired coordination interval as explicit input data. Never extrapolate a fuse curve beyond its supplied range. Return `NOT_EVALUATED` when a required IEC result quantity is unavailable.

## Consequences

- The protection layer depends on domain device contracts and existing IEC 60909 results but does not mutate the electrical `Network` aggregate.
- Overcurrent coordination is a logarithmically sampled comparison, not a continuous proof or automated setting optimizer.
- Manufacturer-specific tolerances, CT saturation, directional elements, protection zones and additional ANSI/IEC functions require subsequent increments.
- The adiabatic conductor check is limited to durations up to 5 s and requires an engineer-supplied k-factor.
- The model is an engineering calculation framework and does not claim complete IEC device-standard compliance.

## References

- IEC 60255-151 inverse-time overcurrent curve family constants, as implemented in manufacturer relay documentation.
- IEC 60947-2:2024 low-voltage circuit-breaker rating framework (Icu/Ics).
- IEC 62271-100:2021+AMD1:2024 three-phase AC circuit-breakers above 1 kV.
- IEC 60364-4-43 adiabatic short-circuit withstand relation \(I^2t\leq k^2S^2\), for the applicable short-duration domain.
