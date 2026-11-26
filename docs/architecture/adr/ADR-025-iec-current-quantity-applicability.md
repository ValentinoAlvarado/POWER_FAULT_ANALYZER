# ADR-025 — IEC 60909 current-quantity applicability and traceability

**Status:** Accepted for the ND-014 partial implementation.
**Date:** 2026-11-22.

## Context

IEC current quantities have different source, fault and topology applicability. The software must not carry a simplified result from one class into another. ND-014 requires maximum/minimum cases, initial, peak, breaking, steady-state and thermal quantities where applicable, source contributions, impedance corrections, and explicit traceability.

## Decision

1. Keep the peak-current implementation limited to maximum, single-fed, radial, three-phase network-feeder faults (existing Clause 8.1 subset). Multiple-fed, meshed and unbalanced peak-current methods are unavailable.
2. For three-phase faults, keep the network-feeder breaking-current result within the single-fed (9.1.5) and multiple-fed (9.2) method classes.
3. For unbalanced faults supplied exclusively by network-feeder voltage sources, report the maximum phase RMS current from the sequence-network solution for the network-feeder subset under Clause 9.3. Machine and converter source contributions remain unavailable.
4. For three-phase faults, keep the network-feeder steady-state result within the single-fed (11.2.5) and multiple-fed (11.2.6) method classes.
5. For unbalanced faults supplied exclusively by network-feeder voltage sources, report the maximum phase RMS current from the sequence-network solution for the network-feeder subset under Clause 11.3. Machine and converter source contributions remain unavailable.
6. Keep optional first-pole contact-separation time as explicit input metadata.
7. Preserve the R/X exponential DC-envelope estimate as a separate **engineering supplement** for one single-fed, radial, three-phase network-feeder case. Do not publish it as a verified IEC 60909-0:2026 Clause 10 quantity until its equation and all applicability requirements have been checked against the final licensed edition.
8. Do not mark IEC `iDC` or `Ibasym` as calculated solely because the supplemental estimate is available. Return the supplemental values in their dedicated fields and keep the normative quantities explicitly unavailable.
9. Keep thermal `Ith` and Joule integral `J` limited to the existing maximum, single-fed, radial, three-phase network-feeder subset. Do not claim the generalized Annex B `m`/`n` procedures.
10. Attach a method reference to each calculated quantity and a reason to each unavailable normative quantity.

## Consequences

A partial IEC study can expose calculated network-feeder quantities and supplementary waveform estimates without conflating the two. The result object can carry a numeric supplement while explicitly stating that the corresponding normative IEC quantity has not been established.

## Normative boundary

Publicly accessible 2026 catalog material identifies the distinct clause families (8.1–8.3, 9.1–9.3, 10, 11.2–11.3 and 14), but does not expose the complete final-edition equations and applicability conditions. The software therefore does not claim full conformity for methods whose final-edition details have not been verified. This decision is deliberately conservative and must be revisited against the licensed final text and independent benchmark cases.
