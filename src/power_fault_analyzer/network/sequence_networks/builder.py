"""Build symmetrical-component networks from registered physical equipment."""

from __future__ import annotations

import cmath
import math
from collections.abc import Mapping
from typing import Protocol, runtime_checkable
from uuid import NAMESPACE_URL, UUID, uuid5

from power_fault_analyzer.domain.enums.sequence_equipment_kind import SequenceEquipmentKind
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.exceptions.source_exceptions import SourceModelError
from power_fault_analyzer.domain.interfaces.branch_model_contracts import (
    SequenceBranchModelProvider,
)
from power_fault_analyzer.domain.interfaces.network_contracts import (
    ElectricalEquipment,
    NetworkAggregate,
    TerminalContract,
)
from power_fault_analyzer.domain.interfaces.source_model_contracts import (
    FaultCurrentCapabilityProvider,
    SourceModelProvider,
)
from power_fault_analyzer.domain.interfaces.transformer_model_contracts import (
    ThreeWindingTransformerModelProvider,
    TwoWindingTransformerModelProvider,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
    SourceSequenceEquivalent,
)
from power_fault_analyzer.domain.value_objects.three_winding_zero_sequence import (
    ThreeWindingZeroSequencePortModel,
)
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.motors.induction_motor import InductionMotor
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.external_grid import ExternalGrid
from power_fault_analyzer.equipment.sources.induction_generator import InductionGenerator
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceMultiportElement,
    SequenceMutualCoupling,
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SequenceShunt,
    SystemBaseSet,
)


@runtime_checkable
class _SequenceBranchEquipment(ElectricalEquipment, SequenceBranchModelProvider, Protocol):
    """Equipment contract used by the generic two-terminal branch adapter."""


@runtime_checkable
class _TwoWindingSequenceEquipment(
    ElectricalEquipment, TwoWindingTransformerModelProvider, Protocol
):
    """Electrical-equipment view of a two-winding transformer."""


@runtime_checkable
class _ThreeWindingSequenceEquipment(
    ElectricalEquipment, ThreeWindingTransformerModelProvider, Protocol
):
    """Electrical-equipment view of a three-winding transformer."""


@runtime_checkable
class _TheveninSourceEquipment(ElectricalEquipment, SourceModelProvider, Protocol):
    """Electrical-equipment view of a Thevenin-type source."""


@runtime_checkable
class _ConverterSourceEquipment(ElectricalEquipment, FaultCurrentCapabilityProvider, Protocol):
    """Electrical-equipment view of a converter current-capability source."""


class SequenceNetworkBuilder:
    """Translate a physical Network aggregate into one or all sequence networks.

    The builder is an adapter between physical equipment entities and immutable
    per-unit sequence-network models. It does not mutate the source equipment.
    """

    def __init__(
        self,
        system_base: SystemBaseSet,
        *,
        regime: SourceOperatingRegime = SourceOperatingRegime.SUBTRANSIENT,
        voltage_base_tolerance: float = 1e-8,
        mutual_couplings: tuple[SequenceMutualCoupling, ...] = (),
    ) -> None:
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet value.")
        if not isinstance(regime, SourceOperatingRegime):
            raise TypeError("regime must be a SourceOperatingRegime value.")
        if (
            isinstance(voltage_base_tolerance, bool)
            or not isinstance(voltage_base_tolerance, (int, float))
            or not math.isfinite(float(voltage_base_tolerance))
            or voltage_base_tolerance < 0.0
        ):
            raise ValueError("voltage_base_tolerance must be finite and non-negative.")
        if not isinstance(mutual_couplings, tuple) or any(
            not isinstance(item, SequenceMutualCoupling) for item in mutual_couplings
        ):
            raise TypeError("mutual_couplings must be a tuple of SequenceMutualCoupling values.")
        self._system_base = system_base
        self._regime = regime
        self._voltage_base_tolerance = float(voltage_base_tolerance)
        self._mutual_couplings = mutual_couplings

    @property
    def system_base(self) -> SystemBaseSet:
        return self._system_base

    def build_all(self, network: NetworkAggregate) -> SequenceNetworkSet:
        return SequenceNetworkSet(
            positive=self.build(network, SequenceType.POSITIVE),
            negative=self.build(network, SequenceType.NEGATIVE),
            zero=self.build(network, SequenceType.ZERO),
        )

    def build(self, network: NetworkAggregate, sequence: SequenceType) -> SequenceNetwork:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        try:
            self.system_base.validate_network(network)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid system base: {exc}") from exc

        diagnostics: list[DomainDiagnostic] = []
        bus_representatives = self._closed_switch_bus_representatives(network, diagnostics)
        bus_by_id = {bus.id: bus for bus in network.buses}
        representative_buses = {
            representative: bus_by_id[representative]
            for representative in set(bus_representatives.values())
        }
        nodes = [
            SequenceNode(bus.id, bus.name)
            for bus in sorted(representative_buses.values(), key=lambda item: str(item.id))
        ]
        node_ids = {node.id for node in nodes}
        branches: list[SequenceBranch] = []
        shunts: list[SequenceShunt] = []
        multiport_elements: list[SequenceMultiportElement] = []
        if not nodes:
            diagnostics.append(
                DomainDiagnostic(
                    code="SEQ-NETWORK-EMPTY",
                    message="A sequence network requires at least one physical bus.",
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=network.id,
                )
            )
        diagnostics.extend(self._validate_equipment_frequency(network))
        nonlinear_sources: list[UUID] = []
        nonlinear_capabilities = {}
        nonlinear_source_bus_ids = {}
        connection_by_terminal = {
            item.terminal_id: bus_representatives[item.bus_id] for item in network.connections
        }

        for equipment in network.equipment:
            if isinstance(equipment, SwitchingDevice):
                # Switchgear is represented by topological node merging above; it is
                # never assigned an artificial numerical impedance.
                continue
            if isinstance(equipment, UnresolvedEquipmentInterface):
                diagnostics.append(
                    DomainDiagnostic(
                        code="SEQ-EQUIPMENT-MODEL-UNRESOLVED",
                        message=(
                            f"'{equipment.name}' is an equipment boundary placeholder, not an "
                            "electrical model. Supply the missing nameplate/network data and "
                            "materialize a supported equipment entity before calculating."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=equipment.id,
                    )
                )
                continue
            try:
                if isinstance(equipment, _SequenceBranchEquipment):
                    self._add_ordinary_branch(
                        equipment,
                        sequence,
                        connection_by_terminal,
                        branches,
                    )
                elif isinstance(equipment, _TwoWindingSequenceEquipment):
                    self._add_two_winding_transformer(
                        equipment,
                        sequence,
                        connection_by_terminal,
                        branches,
                        shunts,
                        diagnostics,
                    )
                elif isinstance(equipment, _ThreeWindingSequenceEquipment):
                    self._add_three_winding_transformer(
                        equipment,
                        network.id,
                        sequence,
                        connection_by_terminal,
                        nodes,
                        node_ids,
                        branches,
                        multiport_elements,
                        diagnostics,
                    )
                elif isinstance(equipment, _TheveninSourceEquipment):
                    self._add_thevenin_source(
                        equipment,
                        sequence,
                        connection_by_terminal,
                        shunts,
                        diagnostics,
                    )
                elif isinstance(equipment, _ConverterSourceEquipment):
                    source_bus_id = self._connected_bus(
                        equipment,
                        equipment.terminals[0],
                        connection_by_terminal,
                    )
                    capability = equipment.fault_current_capability
                    if not isinstance(capability, ConverterFaultCurrentCapability):
                        raise TypeError(
                            "Converter source must expose a ConverterFaultCurrentCapability."
                        )
                    nonlinear_sources.append(equipment.id)
                    nonlinear_capabilities[equipment.id] = capability
                    nonlinear_source_bus_ids[equipment.id] = source_bus_id
                    diagnostics.append(
                        DomainDiagnostic(
                            code="SEQ-NONLINEAR-SOURCE-NOT-STAMPED",
                            message=(
                                f"Source '{equipment.name}' is converter-interfaced. Its declared "
                                "current capability is retained for a dedicated current-injection "
                                "solver and is not converted into a fixed Thevenin admittance."
                            ),
                            severity=DiagnosticSeverity.WARNING,
                            entity_id=equipment.id,
                        )
                    )
                else:
                    diagnostics.append(
                        DomainDiagnostic(
                            code="SEQ-EQUIPMENT-MODEL-UNSUPPORTED",
                            message=(
                                f"Equipment '{equipment.name}' has no sequence-network adapter; "
                                "it was not stamped into this sequence network."
                            ),
                            severity=DiagnosticSeverity.WARNING,
                            entity_id=equipment.id,
                        )
                    )
            except (KeyError, TypeError, ValueError, ZeroDivisionError, SourceModelError) as exc:
                diagnostics.append(
                    DomainDiagnostic(
                        code="SEQ-EQUIPMENT-BUILD-FAILED",
                        message=(
                            f"Could not build {sequence.value}-sequence model for "
                            f"'{equipment.name}': {exc}"
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=equipment.id,
                    )
                )

        reference_id = uuid5(NAMESPACE_URL, f"pfa:{network.id}:sequence-reference")
        diagnostics.extend(
            self._find_unreferenced_components(
                network.id,
                sequence,
                nodes,
                branches,
                shunts,
                multiport_elements,
                reference_id,
            )
        )
        return SequenceNetwork(
            network_id=network.id,
            sequence=sequence,
            nodes=tuple(nodes),
            branches=tuple(branches),
            shunts=tuple(shunts),
            diagnostics=tuple(diagnostics),
            nonlinear_source_ids=tuple(nonlinear_sources),
            converter_capabilities=nonlinear_capabilities,
            converter_bus_ids=nonlinear_source_bus_ids,
            multiport_elements=tuple(multiport_elements),
            mutual_couplings=tuple(
                item for item in self._mutual_couplings if item.sequence is sequence
            ),
            reference_node_id=reference_id,
            bus_node_map=bus_representatives,
        )

    @staticmethod
    def _closed_switch_bus_representatives(
        network: NetworkAggregate,
        diagnostics: list[DomainDiagnostic],
    ) -> dict[UUID, UUID]:
        """Collapse buses joined by closed switchgear without stamping switch impedances."""
        parent = {bus.id: bus.id for bus in network.buses}
        bus_by_id = {bus.id: bus for bus in network.buses}
        connection_by_terminal = {item.terminal_id: item.bus_id for item in network.connections}

        def find(identifier: UUID) -> UUID:
            while parent[identifier] != identifier:
                parent[identifier] = parent[parent[identifier]]
                identifier = parent[identifier]
            return identifier

        def union(first: UUID, second: UUID) -> None:
            left, right = find(first), find(second)
            if left == right:
                return
            keep, merge = sorted((left, right), key=str)
            parent[merge] = keep

        for equipment in network.equipment:
            if not isinstance(equipment, SwitchingDevice) or not equipment.is_closed:
                continue
            try:
                first_bus = connection_by_terminal[equipment.terminals[0].id]
                second_bus = connection_by_terminal[equipment.terminals[1].id]
            except KeyError:
                diagnostics.append(
                    DomainDiagnostic(
                        code="SEQ-SWITCH-UNCONNECTED-TERMINAL",
                        message=(
                            f"Closed switch '{equipment.name}' has an unconnected terminal; "
                            "its topology cannot be reduced."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=equipment.id,
                    )
                )
                continue
            if bus_by_id[first_bus].nominal_voltage != bus_by_id[second_bus].nominal_voltage:
                diagnostics.append(
                    DomainDiagnostic(
                        code="SEQ-SWITCH-VOLTAGE-MISMATCH",
                        message=(
                            f"Closed switch '{equipment.name}' connects different nominal "
                            "voltage levels."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=equipment.id,
                    )
                )
                continue
            union(first_bus, second_bus)

        return {identifier: find(identifier) for identifier in parent}

    @staticmethod
    def _connected_bus(
        equipment: ElectricalEquipment,
        terminal: TerminalContract,
        connection_by_terminal: Mapping[UUID, UUID],
    ) -> UUID:
        try:
            return connection_by_terminal[terminal.id]
        except KeyError as exc:
            raise ValueError(
                f"Terminal '{terminal.designation}' of '{equipment.name}' is not connected."
            ) from exc

    def _add_ordinary_branch(
        self,
        equipment: _SequenceBranchEquipment,
        sequence: SequenceType,
        connection_by_terminal: Mapping[UUID, UUID],
        branches: list[SequenceBranch],
    ) -> None:
        terminal_from, terminal_to = equipment.terminals
        bus_from = self._connected_bus(equipment, terminal_from, connection_by_terminal)
        bus_to = self._connected_bus(equipment, terminal_to, connection_by_terminal)
        base_from = self.system_base.for_bus(bus_from)
        base_to = self.system_base.for_bus(bus_to)
        if not self._same_voltage_base(base_from.base_voltage_kv, base_to.base_voltage_kv):
            raise ValueError(
                "A two-terminal line/branch requires equal voltage bases at both ends. "
                "Use a transformer model for a voltage-level change."
            )
        model = equipment.build_sequence_equivalent(sequence)
        z_pu = model.series_impedance.value_ohm / base_from.base_impedance_ohm
        y_from_pu = model.shunt_admittance_from.value_siemens * base_from.base_impedance_ohm
        y_to_pu = model.shunt_admittance_to.value_siemens * base_from.base_impedance_ohm
        branches.append(
            SequenceBranch(
                id=equipment.id,
                name=equipment.name,
                from_node_id=bus_from,
                to_node_id=bus_to,
                series_impedance_pu=z_pu,
                shunt_admittance_from_pu=y_from_pu,
                shunt_admittance_to_pu=y_to_pu,
                length_km=(equipment.length_km if isinstance(equipment, Line) else None),
                equipment_kind=(
                    SequenceEquipmentKind.LINE
                    if isinstance(equipment, Line)
                    else SequenceEquipmentKind.OTHER
                ),
            )
        )

    def _add_thevenin_source(
        self,
        equipment: _TheveninSourceEquipment,
        sequence: SequenceType,
        connection_by_terminal: Mapping[UUID, UUID],
        shunts: list[SequenceShunt],
        diagnostics: list[DomainDiagnostic],
    ) -> None:
        bus_id = self._connected_bus(
            equipment,
            equipment.terminals[0],
            connection_by_terminal,
        )
        base = self.system_base.for_bus(bus_id)
        equivalents = equipment.build_source_equivalent(base, self._regime)
        model: SourceSequenceEquivalent = equivalents.for_sequence(sequence)

        if model.status is SourceSequenceStatus.UNSPECIFIED:
            diagnostics.append(
                DomainDiagnostic(
                    code="SEQ-SOURCE-SEQUENCE-UNSPECIFIED",
                    message=(
                        f"Source '{equipment.name}' has no declared {sequence.value}-sequence "
                        "equivalent. It is not assumed to equal the positive-sequence model "
                        "or to be an open circuit."
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=equipment.id,
                )
            )
            return

        if model.status is SourceSequenceStatus.BLOCKED:
            diagnostics.append(
                DomainDiagnostic(
                    code="SEQ-SOURCE-SEQUENCE-BLOCKED",
                    message=(
                        f"Source '{equipment.name}' explicitly blocks external "
                        f"{sequence.value}-sequence current. No Thevenin shunt was stamped."
                    ),
                    severity=DiagnosticSeverity.INFO,
                    entity_id=equipment.id,
                )
            )
            return

        assert model.impedance is not None
        z_pu = model.impedance.value_pu
        if abs(z_pu) <= 1e-15:
            raise ValueError("An ideal zero-impedance source requires a constraint-based solver.")
        if isinstance(equipment, ExternalGrid):
            source_kind = SequenceSourceKind.NETWORK_FEEDER
        elif isinstance(equipment, SynchronousGenerator):
            source_kind = SequenceSourceKind.SYNCHRONOUS_MACHINE
        elif isinstance(equipment, (InductionGenerator, InductionMotor)):
            source_kind = SequenceSourceKind.ASYNCHRONOUS_MACHINE
        elif isinstance(equipment, EquivalentSource):
            source_kind = SequenceSourceKind.EXPLICIT_THEVENIN
        else:
            source_kind = SequenceSourceKind.EXPLICIT_THEVENIN
        shunts.append(
            SequenceShunt(
                id=equipment.id,
                name=equipment.name,
                node_id=bus_id,
                admittance_pu=1.0 / z_pu,
                source_voltage_pu=(
                    0.0j if model.internal_voltage_pu is None else model.internal_voltage_pu
                ),
                source_kind=source_kind,
            )
        )

    def _add_two_winding_transformer(
        self,
        equipment: _TwoWindingSequenceEquipment,
        sequence: SequenceType,
        connection_by_terminal: Mapping[UUID, UUID],
        branches: list[SequenceBranch],
        shunts: list[SequenceShunt],
        diagnostics: list[DomainDiagnostic],
    ) -> None:
        by_designation = {
            winding.designation: (terminal, winding)
            for terminal, winding in zip(equipment.terminals, equipment.windings, strict=True)
        }
        hv_terminal, hv = by_designation[WindingDesignation.HIGH_VOLTAGE]
        lv_terminal, lv = by_designation[WindingDesignation.LOW_VOLTAGE]
        hv_bus = self._connected_bus(equipment, hv_terminal, connection_by_terminal)
        lv_bus = self._connected_bus(equipment, lv_terminal, connection_by_terminal)
        hv_base = self.system_base.for_bus(hv_bus)
        lv_base = self.system_base.for_bus(lv_bus)
        self._validate_winding_base(equipment, hv, hv_base.base_voltage_kv)
        self._validate_winding_base(equipment, lv, lv_base.base_voltage_kv)

        if sequence in (SequenceType.POSITIVE, SequenceType.NEGATIVE):
            impedance = equipment.get_sequence_impedance_pu(sequence).convert_base(
                equipment.sequence_impedances.base,
                hv_base,
            )
            angle = math.radians(equipment.vector_group.phase_displacement_degrees)
            tap = cmath.exp(1j * angle)
            if sequence is SequenceType.NEGATIVE:
                tap = tap.conjugate()
            branches.append(
                SequenceBranch(
                    id=equipment.id,
                    name=equipment.name,
                    from_node_id=hv_bus,
                    to_node_id=lv_bus,
                    series_impedance_pu=impedance.value_pu,
                    tap_from=tap,
                    equipment_kind=SequenceEquipmentKind.TWO_WINDING_TRANSFORMER,
                    transformer_reactance_pu=(
                        equipment.get_sequence_impedance_pu(SequenceType.POSITIVE).value_pu.imag
                    ),
                    transformer_correction_voltage_kv=lv.rated_voltage_kv,
                )
            )
            return

        z0 = (
            equipment.get_sequence_impedance_pu(SequenceType.ZERO)
            .convert_base(
                equipment.sequence_impedances.base,
                hv_base,
            )
            .value_pu
        )
        hv_neutral_pu = self._neutral_impedance_pu(hv, hv_base)
        lv_neutral_pu = self._neutral_impedance_pu(lv, lv_base)
        hv_grounded = hv_neutral_pu is not None
        lv_grounded = lv_neutral_pu is not None
        hv_delta = hv.connection is WindingConnection.DELTA
        lv_delta = lv.connection is WindingConnection.DELTA

        if hv_grounded and lv_grounded:
            branches.append(
                SequenceBranch(
                    id=equipment.id,
                    name=equipment.name,
                    from_node_id=hv_bus,
                    to_node_id=lv_bus,
                    series_impedance_pu=z0 + hv_neutral_pu + lv_neutral_pu,
                    equipment_kind=SequenceEquipmentKind.TWO_WINDING_TRANSFORMER,
                    transformer_reactance_pu=(
                        equipment.get_sequence_impedance_pu(SequenceType.POSITIVE).value_pu.imag
                    ),
                    transformer_correction_voltage_kv=lv.rated_voltage_kv,
                )
            )
        elif hv_grounded and lv_delta:
            self._append_transformer_zero_shunt(
                equipment, hv_bus, z0 + hv_neutral_pu, lv.rated_voltage_kv, shunts
            )
        elif lv_grounded and hv_delta:
            self._append_transformer_zero_shunt(
                equipment, lv_bus, z0 + lv_neutral_pu, lv.rated_voltage_kv, shunts
            )
        else:
            diagnostics.append(
                DomainDiagnostic(
                    code="SEQ-TRANSFORMER-ZERO-BLOCKED",
                    message=(
                        f"Transformer '{equipment.name}' has no modeled closed external "
                        "zero-sequence path for this winding/neutral configuration."
                    ),
                    severity=DiagnosticSeverity.INFO,
                    entity_id=equipment.id,
                )
            )

    def _add_three_winding_transformer(
        self,
        equipment: _ThreeWindingSequenceEquipment,
        network_id: UUID,
        sequence: SequenceType,
        connection_by_terminal: Mapping[UUID, UUID],
        nodes: list[SequenceNode],
        node_ids: set[UUID],
        branches: list[SequenceBranch],
        multiport_elements: list[SequenceMultiportElement],
        diagnostics: list[DomainDiagnostic],
    ) -> None:
        connected = []
        for terminal, winding in zip(equipment.terminals, equipment.windings, strict=True):
            bus_id = self._connected_bus(equipment, terminal, connection_by_terminal)
            base = self.system_base.for_bus(bus_id)
            self._validate_winding_base(equipment, winding, base.base_voltage_kv)
            connected.append((bus_id, winding, base))

        if sequence is SequenceType.ZERO:
            port_model = getattr(equipment, "zero_sequence_port_model", None)
            if port_model is None:
                diagnostics.append(
                    DomainDiagnostic(
                        code="SEQ-3W-TRANSFORMER-ZERO-REQUIRES-EXPLICIT-MODEL",
                        message=(
                            f"Three-winding transformer '{equipment.name}' requires an explicit "
                            "manufacturer-, test-, or validated-model zero-sequence three-port "
                            "equivalent. Pairwise leakage impedances and winding connections "
                            "alone do not define delta circulating-current and core-return paths."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=equipment.id,
                    )
                )
                return
            if not isinstance(port_model, ThreeWindingZeroSequencePortModel):
                raise TypeError(
                    "zero_sequence_port_model must be ThreeWindingZeroSequencePortModel."
                )
            self._validate_winding_base(equipment, connected[0][1], port_model.base.base_voltage_kv)
            scale = self.system_base.base_power_mva / port_model.base.base_power_mva
            scaled_matrix = tuple(
                tuple(value * scale for value in row) for row in port_model.impedance_matrix_pu
            )
            multiport_elements.append(
                SequenceMultiportElement(
                    id=equipment.id,
                    name=f"{equipment.name}:ZERO-PORTS",
                    node_ids=tuple(item[0] for item in connected),
                    impedance_matrix_pu=scaled_matrix,
                )
            )
            return

        equivalent = equipment.build_star_equivalent(sequence)
        hv_base = connected[0][2]
        # All three star arms are referred to the transformer's common HV base.
        # System voltage bases follow the winding rated-voltage ratios, so the
        # per-unit arm impedances remain valid at their respective terminals.
        target_base = hv_base
        arm_by_designation = {
            WindingDesignation.HIGH_VOLTAGE: equivalent.high_voltage,
            WindingDesignation.MEDIUM_VOLTAGE: equivalent.medium_voltage,
            WindingDesignation.LOW_VOLTAGE: equivalent.low_voltage,
        }
        auxiliary_id = uuid5(
            NAMESPACE_URL,
            f"pfa:{network_id}:transformer:{equipment.id}:{sequence.value}:star",
        )
        if auxiliary_id in node_ids:
            raise ValueError("Generated three-winding transformer internal-node ID collision.")
        node_ids.add(auxiliary_id)
        nodes.append(
            SequenceNode(
                id=auxiliary_id,
                label=f"{equipment.name}:STAR:{sequence.value}",
                is_internal=True,
            )
        )

        for bus_id, winding, _bus_base in connected:
            arm = (
                arm_by_designation[winding.designation]
                .convert_base(
                    equivalent.base,
                    target_base,
                )
                .value_pu
            )
            tap = self._three_winding_tap(equipment, winding.designation, sequence)
            arm_id = uuid5(
                equipment.id,
                f"pfa:{sequence.value}:{winding.designation.value}:star-arm",
            )
            branches.append(
                SequenceBranch(
                    id=arm_id,
                    name=f"{equipment.name}:{winding.designation.value}",
                    from_node_id=bus_id,
                    to_node_id=auxiliary_id,
                    series_impedance_pu=arm,
                    tap_from=tap,
                    equipment_kind=SequenceEquipmentKind.THREE_WINDING_TRANSFORMER,
                )
            )

    @staticmethod
    def _three_winding_tap(
        equipment: _ThreeWindingSequenceEquipment,
        designation: WindingDesignation,
        sequence: SequenceType,
    ) -> complex:
        if designation is WindingDesignation.HIGH_VOLTAGE:
            return 1.0 + 0.0j
        if designation is WindingDesignation.MEDIUM_VOLTAGE:
            clock = equipment.hv_mv_vector_group.clock_number
        elif designation is WindingDesignation.LOW_VOLTAGE:
            clock = equipment.hv_lv_vector_group.clock_number
        else:
            raise ValueError(f"Unsupported winding designation: {designation!r}.")
        tap = cmath.exp(1j * math.radians(clock * 30.0))
        return tap.conjugate() if sequence is SequenceType.NEGATIVE else tap

    @staticmethod
    def _neutral_impedance_pu(winding, base) -> complex | None:
        grounding = winding.neutral_grounding
        if grounding is None:
            return None
        neutral_ohm = grounding.zero_sequence_neutral_impedance_ohm
        if neutral_ohm is None:
            return None
        return neutral_ohm / base.base_impedance_ohm

    @staticmethod
    def _append_transformer_zero_shunt(
        equipment: ElectricalEquipment,
        bus_id: UUID,
        impedance_pu: complex,
        correction_voltage_kv: float,
        shunts: list[SequenceShunt],
    ) -> None:
        if abs(impedance_pu) <= 1e-15:
            raise ValueError("Transformer zero-sequence shunt impedance cannot be zero.")
        shunts.append(
            SequenceShunt(
                id=equipment.id,
                name=f"{equipment.name}:ZERO-SEQUENCE-GROUND-PATH",
                node_id=bus_id,
                admittance_pu=1.0 / impedance_pu,
                equipment_kind=SequenceEquipmentKind.TWO_WINDING_TRANSFORMER,
                transformer_reactance_pu=(
                    equipment.get_sequence_impedance_pu(SequenceType.POSITIVE).value_pu.imag
                ),
                transformer_correction_voltage_kv=correction_voltage_kv,
            )
        )

    def _validate_winding_base(
        self,
        equipment: ElectricalEquipment,
        winding,
        base_voltage_kv: float,
    ) -> None:
        tolerance = max(
            1e-9,
            abs(winding.rated_voltage_kv) * self._voltage_base_tolerance,
        )
        if abs(base_voltage_kv - winding.rated_voltage_kv) > tolerance:
            raise ValueError(
                f"System voltage base at {winding.designation.value} winding of "
                f"'{equipment.name}' must match its rated voltage."
            )

    def _same_voltage_base(self, left: float, right: float) -> bool:
        tolerance = max(1e-9, max(abs(left), abs(right)) * self._voltage_base_tolerance)
        return abs(left - right) <= tolerance

    @staticmethod
    def _validate_equipment_frequency(
        network: NetworkAggregate,
    ) -> tuple[DomainDiagnostic, ...]:
        """Reject mixed frequency bases instead of silently combining impedances."""
        declared: list[tuple[str, Frequency]] = []
        for equipment in network.equipment:
            frequency = getattr(equipment, "frequency", None)
            if frequency is None:
                parameters = getattr(equipment, "parameters", None)
                frequency = getattr(parameters, "reference_frequency", None)
            if frequency is None:
                continue
            if not isinstance(frequency, Frequency):
                return (
                    DomainDiagnostic(
                        code="SEQ-FREQUENCY-MODEL-INVALID",
                        message=(
                            f"Equipment '{equipment.name}' exposes a frequency value "
                            "that is not a Frequency value object."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=equipment.id,
                    ),
                )
            declared.append((equipment.name, frequency))

        if not declared:
            return ()
        reference_hz = declared[0][1].value_hz
        mismatched = [
            (name, frequency.value_hz)
            for name, frequency in declared[1:]
            if not math.isclose(
                frequency.value_hz,
                reference_hz,
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
        ]
        if not mismatched:
            return ()
        detail = ", ".join(f"{name}={value:g} Hz" for name, value in mismatched)
        return (
            DomainDiagnostic(
                code="SEQ-FREQUENCY-MISMATCH",
                message=(
                    f"Equipment frequency/reference-frequency values do not agree with "
                    f"{declared[0][0]}={reference_hz:g} Hz: {detail}. Sequence models "
                    "must be supplied at one common study frequency; no frequency "
                    "scaling is inferred by this builder."
                ),
                severity=DiagnosticSeverity.ERROR,
                entity_id=network.id,
            ),
        )

    @staticmethod
    def _find_unreferenced_components(
        network_id: UUID,
        sequence: SequenceType,
        nodes: list[SequenceNode],
        branches: list[SequenceBranch],
        shunts: list[SequenceShunt],
        multiport_elements: list[SequenceMultiportElement],
        reference_id: UUID,
    ) -> tuple[DomainDiagnostic, ...]:
        import networkx as nx

        graph = nx.Graph()
        graph.add_nodes_from(node.id for node in nodes)
        graph.add_node(reference_id)
        graph.add_edges_from((branch.from_node_id, branch.to_node_id) for branch in branches)
        graph.add_edges_from((shunt.node_id, reference_id) for shunt in shunts)
        for element in multiport_elements:
            graph.add_edges_from((node_id, reference_id) for node_id in element.node_ids)
        diagnostics = []
        for component in nx.connected_components(graph):
            if reference_id in component:
                continue
            if not component:
                continue
            labels = sorted(node.label for node in nodes if node.id in component)
            diagnostics.append(
                DomainDiagnostic(
                    code="SEQ-COMPONENT-UNREFERENCED",
                    message=(
                        f"{sequence.value.title()}-sequence component {', '.join(labels)} "
                        "has no path to the sequence reference. Its nodal matrix may be singular."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                    entity_id=network_id,
                )
            )
        return tuple(diagnostics)
