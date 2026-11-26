# PFA Standards Implementation Register

This register separates publication metadata from implementation claims. It is not a substitute for authorized normative documents or clause-level engineering review.

| Standard | Edition baseline | PFA status | Required next evidence |
|---|---|---|---|
| IEC 60909-0 | 2026, Edition 3.0 (published 2026-07-23) | Research | Clause-level delta review; factors; supported equipment cases; benchmark matrix; independent validation |
| IEC 60617 | Verify current catalogue and symbol-family editions | Research | Symbol-family mapping, geometry/connectivity tests, provenance and licensing record |
| IEC 61082-1 | Verify current edition | Not assessed | Document/diagram clause matrix and export acceptance tests |

## Claim policy

- Research: source and scope identified; implementation not claimed.
- Specified: requirements and equations documented; no implementation claim.
- Implemented: code exists; not necessarily independently verified.
- Verified: implementation passes defined mathematical and software tests.
- Validated: results compared with independent reference evidence over a documented domain.

A generic symmetrical-components fault solver is not automatically an IEC 60909 implementation.

## IEC 60909-0:2026 work package

1. Obtain the applicable normative edition through an authorized source.
2. Produce a clause-level delta against the previous edition; record changed definitions, factors, methods and applicability conditions.
3. Map each requirement to a domain input, algorithm, output quantity, diagnostic and test identifier.
4. Implement applicable correction-factor and equivalent-voltage procedures without hiding assumptions in UI code.
5. Build independent analytical cases and third-party reference cases covering supported equipment and network configurations.
6. Add regression, property-based, sensitivity and numerical-conditioning tests.
7. Publish a support matrix stating implemented, unsupported and partially supported cases.

Normative equations must be transcribed and reviewed from the authorized standard during the work package.
