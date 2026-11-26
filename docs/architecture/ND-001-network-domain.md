# ND-001 — Network Domain Implementation

**Status:** Implemented baseline  
**Architecture:** DDD + Hexagonal  
**Runtime:** Python 3.13.x  
**Network model:** Balanced three-phase, line-to-line nominal voltage convention

## Scope

This unit implements the physical network aggregate and its first domain entities:

- `Bus`
- `Terminal`
- `ElectricalEquipmentBase`
- `TwoTerminalEquipmentBase`
- `ThreeTerminalEquipmentBase`
- `Connection`
- `Network`
- `DefaultNetworkValidationService`
- `NominalVoltageCompatibilityPolicy`

It does not implement switching-state scenarios, branch admittance models, sequence networks, source models, or short-circuit solvers.

## Design decisions

1. `Bus` and `Terminal` are immutable entities with UUID identity.
2. `Connection` is an immutable value object identified by `(terminal_id, bus_id)`.
3. Equipment exposes an immutable tuple of terminals. The terminal owner ID must equal the equipment ID.
4. `Network` is the aggregate root and owns indexes for buses, equipment, terminals, and terminal-to-bus connections.
5. The aggregate returns tuple snapshots and does not expose its internal dictionaries.
6. A terminal may have at most one connection.
7. A bus cannot be removed while any terminal connection references it.
8. Removing equipment explicitly removes its terminal connections and terminal registrations.
9. Identifiers are unique across the network root, buses, equipment, and terminals.
10. Element names are unique case-insensitively across buses and equipment.
11. The initial balanced model uses line-to-line voltage for bus nominal voltage and terminal rated voltage.
12. Voltage compatibility is an injected policy. The default uses a strict relative tolerance of `1e-6`; this is a project connection rule, not an IEC voltage tolerance.
13. Empty and partially connected networks can be created as drafts. Calculation readiness is checked by `DefaultNetworkValidationService`.
14. Equipment behavior is accepted structurally through `ElectricalEquipment` Protocol; reusable base classes enforce common identity and terminal rules.

## Cardinalities

| Relationship | Cardinality | Rule |
|---|---:|---|
| Network — Bus | 1:N | Zero buses permitted while editing; calculation requires at least one |
| Network — Equipment | 1:N | Zero equipment permitted while editing; calculation requires at least one |
| Equipment — Terminal | 1:N | At least one terminal |
| Two-terminal equipment — Terminal | 1:2 | Exactly two |
| Three-terminal equipment — Terminal | 1:3 | Exactly three |
| Terminal — Connection | 1:0..1 | At most one connection |
| Connection — Bus | N:1 | Multiple terminals may connect to one bus |

## Voltage convention

The balanced domain stores nominal bus and terminal rated voltage as line-to-line quantities. Phase-to-neutral voltage remains represented by the `Voltage` value object for later domains, but it is rejected as the nominal voltage of a balanced-model bus or terminal.

## Calculation-readiness rules in this increment

`DefaultNetworkValidationService.validate_for_calculation()` requires:

- at least one bus;
- at least one equipment item;
- every registered equipment terminal to be connected;
- no equipment-level error diagnostics.

Source sufficiency, graph islanding, grounding paths, sequence-model completeness, and numerical solvability are intentionally deferred to later validation services.

## Non-goals

- No operational switch state is stored in `Network`.
- No NetworkX object is exposed by the domain.
- No NumPy/SciPy matrix is stored in the aggregate.
- No line/cable/transformer electrical impedance model is implemented in this increment.
- No claim of IEC 60909 compliance is made by this network-domain implementation.

## Tests

Unit tests cover entity validation, protocol conformance, cardinality, voltage matching, duplicate IDs and names, connection uniqueness, referential integrity, removal semantics, three-terminal equipment, and calculation-readiness diagnostics.

## Polymorphism and extension points

`Network.add_equipment()` accepts the structural `ElectricalEquipment` Protocol, not only subclasses of `ElectricalEquipmentBase`. A future equipment package can therefore implement the required attributes and `validate_configuration()` method without inheriting from the built-in base class. The aggregate performs runtime boundary checks before registration.

Equipment validation diagnostics with severity `ERROR` reject registration. `WARNING` and `INFO` diagnostics are non-blocking and remain available to higher-level validation/reporting workflows.
