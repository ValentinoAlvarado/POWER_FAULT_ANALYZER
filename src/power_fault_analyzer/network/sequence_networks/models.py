"""Immutable models for positive-, negative- and zero-sequence networks."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from numbers import Real
from types import MappingProxyType
from uuid import UUID, uuid4

from power_fault_analyzer.domain.enums.sequence_equipment_kind import SequenceEquipmentKind
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.source_models import ConverterFaultCurrentCapability


def _determinant_3x3(matrix: tuple[tuple[complex, ...], ...]) -> complex:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def _finite_complex(value: complex, name: str) -> complex:
    if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
        raise TypeError(f"{name} must be a real or complex numeric value, not bool.")
    result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} must have finite real and imaginary components.")
    return result


@dataclass(frozen=True, slots=True)
class SystemBaseSet:
    """Common three-phase MVA base and line-to-line kV base for every physical bus.

    Voltage bases are bus-specific. This is essential for multi-voltage networks:
    the three-phase power base is common, while voltage and impedance bases change
    across transformer voltage levels.
    """

    base_power_mva: float
    bus_voltage_bases_kv: Mapping[UUID, float]

    def __post_init__(self) -> None:
        if isinstance(self.base_power_mva, bool) or not isinstance(self.base_power_mva, Real):
            raise TypeError("base_power_mva must be a real numeric value, not bool.")
        power = float(self.base_power_mva)
        if not math.isfinite(power) or power <= 0.0:
            raise ValueError("base_power_mva must be finite and greater than zero.")
        if not isinstance(self.bus_voltage_bases_kv, Mapping):
            raise TypeError("bus_voltage_bases_kv must be a mapping of bus UUID to kV.")
        copied: dict[UUID, float] = {}
        for bus_id, voltage in self.bus_voltage_bases_kv.items():
            if not isinstance(bus_id, UUID):
                raise TypeError("Every bus base key must be a UUID.")
            if isinstance(voltage, bool) or not isinstance(voltage, Real):
                raise TypeError("Every bus voltage base must be a real numeric value.")
            numeric = float(voltage)
            if not math.isfinite(numeric) or numeric <= 0.0:
                raise ValueError("Every bus voltage base must be finite and positive.")
            copied[bus_id] = numeric
        object.__setattr__(self, "base_power_mva", power)
        object.__setattr__(self, "bus_voltage_bases_kv", MappingProxyType(copied))

    @classmethod
    def from_network(cls, network: NetworkAggregate, base_power_mva: float) -> SystemBaseSet:
        """Create nominal-voltage bases directly from the registered bus objects."""
        return cls(
            base_power_mva=base_power_mva,
            bus_voltage_bases_kv={bus.id: bus.nominal_voltage.value_kv for bus in network.buses},
        )

    def for_bus(self, bus_id: UUID) -> ElectricalImpedanceBase:
        try:
            voltage = self.bus_voltage_bases_kv[bus_id]
        except KeyError as exc:
            raise KeyError(f"No voltage base was configured for bus '{bus_id}'.") from exc
        return ElectricalImpedanceBase(self.base_power_mva, voltage)

    def validate_network(
        self, network: NetworkAggregate, *, relative_tolerance: float = 1e-9
    ) -> None:
        if (
            isinstance(relative_tolerance, bool)
            or not isinstance(relative_tolerance, Real)
            or not math.isfinite(float(relative_tolerance))
            or relative_tolerance < 0.0
        ):
            raise ValueError("relative_tolerance must be finite and non-negative.")
        for bus in network.buses:
            base = self.for_bus(bus.id)
            nominal = bus.nominal_voltage.value_kv
            tolerance = max(1e-9, abs(nominal) * relative_tolerance)
            if abs(base.base_voltage_kv - nominal) > tolerance:
                raise ValueError(
                    f"Voltage base for bus '{bus.name}' ({base.base_voltage_kv:g} kV) "
                    f"does not match its nominal voltage ({nominal:g} kV)."
                )


@dataclass(frozen=True, slots=True)
class SequenceNode:
    """A physical bus or an internal mathematical node in a sequence network."""

    id: UUID
    label: str
    is_internal: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("SequenceNode.id must be a UUID.")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("SequenceNode.label cannot be empty.")
        if not isinstance(self.is_internal, bool):
            raise TypeError("SequenceNode.is_internal must be bool.")


@dataclass(frozen=True, slots=True)
class SequenceBranch:
    """Two-terminal series branch with optional terminal shunts and complex tap.

    ``tap_from`` follows the convention V_from = tap_from * V_to for the ideal
    transformer at zero leakage. A positive-sequence clock displacement uses
    exp(+j*clock*30°) when oriented from the HV winding; negative sequence uses
    its complex conjugate. Ordinary lines use a unit tap.
    """

    id: UUID
    name: str
    from_node_id: UUID
    to_node_id: UUID
    series_impedance_pu: complex
    shunt_admittance_from_pu: complex = 0.0j
    shunt_admittance_to_pu: complex = 0.0j
    tap_from: complex = 1.0 + 0.0j
    length_km: float | None = None
    equipment_kind: SequenceEquipmentKind = SequenceEquipmentKind.OTHER
    transformer_reactance_pu: float | None = None
    transformer_correction_voltage_kv: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("SequenceBranch.id must be a UUID.")
        if self.from_node_id == self.to_node_id:
            raise ValueError("A sequence branch must connect two distinct nodes.")
        if not isinstance(self.from_node_id, UUID) or not isinstance(self.to_node_id, UUID):
            raise TypeError("Sequence branch node identifiers must be UUID values.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("SequenceBranch.name cannot be empty.")
        impedance = _finite_complex(self.series_impedance_pu, "series_impedance_pu")
        if abs(impedance) <= 1e-15:
            raise ValueError("Series impedance cannot be zero in a nodal branch model.")
        tap = _finite_complex(self.tap_from, "tap_from")
        if abs(tap) <= 1e-15:
            raise ValueError("Transformer tap magnitude must be greater than zero.")
        object.__setattr__(self, "series_impedance_pu", impedance)
        object.__setattr__(
            self,
            "shunt_admittance_from_pu",
            _finite_complex(self.shunt_admittance_from_pu, "shunt_admittance_from_pu"),
        )
        object.__setattr__(
            self,
            "shunt_admittance_to_pu",
            _finite_complex(self.shunt_admittance_to_pu, "shunt_admittance_to_pu"),
        )
        object.__setattr__(self, "tap_from", tap)
        if self.length_km is not None:
            if isinstance(self.length_km, bool) or not isinstance(self.length_km, Real):
                raise TypeError("length_km must be a real numeric value or None, not bool.")
            length = float(self.length_km)
            if not math.isfinite(length) or length <= 0.0:
                raise ValueError("length_km must be finite and greater than zero.")
            object.__setattr__(self, "length_km", length)
        if not isinstance(self.equipment_kind, SequenceEquipmentKind):
            raise TypeError("equipment_kind must be a SequenceEquipmentKind value.")
        if self.transformer_reactance_pu is not None:
            if isinstance(self.transformer_reactance_pu, bool) or not isinstance(
                self.transformer_reactance_pu, Real
            ):
                raise TypeError("transformer_reactance_pu must be real or None.")
            reactance = float(self.transformer_reactance_pu)
            if not math.isfinite(reactance) or reactance <= 0.0:
                raise ValueError("transformer_reactance_pu must be finite and positive.")
            object.__setattr__(self, "transformer_reactance_pu", reactance)
        if self.transformer_correction_voltage_kv is not None:
            if isinstance(self.transformer_correction_voltage_kv, bool) or not isinstance(
                self.transformer_correction_voltage_kv, Real
            ):
                raise TypeError("transformer_correction_voltage_kv must be real or None.")
            correction_voltage = float(self.transformer_correction_voltage_kv)
            if not math.isfinite(correction_voltage) or correction_voltage <= 0.0:
                raise ValueError("transformer_correction_voltage_kv must be finite and positive.")
            object.__setattr__(self, "transformer_correction_voltage_kv", correction_voltage)
        if self.equipment_kind is SequenceEquipmentKind.TWO_WINDING_TRANSFORMER:
            if self.transformer_reactance_pu is None:
                raise ValueError(
                    "Two-winding transformer branches require rated reactance metadata."
                )
            if self.transformer_correction_voltage_kv is None:
                raise ValueError(
                    "Two-winding transformer branches require LV rated-voltage metadata."
                )


@dataclass(frozen=True, slots=True)
class SequenceShunt:
    """Shunt to the sequence reference; optionally represents a Thevenin source.

    For a Thevenin source, Y=1/Z is stamped on the diagonal and the Norton
    injection Y*E is added to the right-hand side. Grounding branches have E=0.
    """

    id: UUID
    name: str
    node_id: UUID
    admittance_pu: complex
    source_voltage_pu: complex = 0.0j
    source_kind: SequenceSourceKind = SequenceSourceKind.PASSIVE
    equipment_kind: SequenceEquipmentKind = SequenceEquipmentKind.OTHER
    transformer_reactance_pu: float | None = None
    transformer_correction_voltage_kv: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.node_id, UUID):
            raise TypeError("SequenceShunt identifiers must be UUID values.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("SequenceShunt.name cannot be empty.")
        admittance = _finite_complex(self.admittance_pu, "admittance_pu")
        if abs(admittance) <= 1e-15:
            raise ValueError("A sequence shunt admittance cannot be zero.")
        object.__setattr__(self, "admittance_pu", admittance)
        object.__setattr__(
            self, "source_voltage_pu", _finite_complex(self.source_voltage_pu, "source_voltage_pu")
        )
        if not isinstance(self.source_kind, SequenceSourceKind):
            raise TypeError("source_kind must be a SequenceSourceKind value.")
        if not isinstance(self.equipment_kind, SequenceEquipmentKind):
            raise TypeError("equipment_kind must be a SequenceEquipmentKind value.")
        if self.transformer_reactance_pu is not None:
            if isinstance(self.transformer_reactance_pu, bool) or not isinstance(
                self.transformer_reactance_pu, Real
            ):
                raise TypeError("transformer_reactance_pu must be real or None.")
            reactance = float(self.transformer_reactance_pu)
            if not math.isfinite(reactance) or reactance <= 0.0:
                raise ValueError("transformer_reactance_pu must be finite and positive.")
            object.__setattr__(self, "transformer_reactance_pu", reactance)
        if self.transformer_correction_voltage_kv is not None:
            if isinstance(self.transformer_correction_voltage_kv, bool) or not isinstance(
                self.transformer_correction_voltage_kv, Real
            ):
                raise TypeError("transformer_correction_voltage_kv must be real or None.")
            correction_voltage = float(self.transformer_correction_voltage_kv)
            if not math.isfinite(correction_voltage) or correction_voltage <= 0.0:
                raise ValueError("transformer_correction_voltage_kv must be finite and positive.")
            object.__setattr__(self, "transformer_correction_voltage_kv", correction_voltage)
        if self.equipment_kind is SequenceEquipmentKind.TWO_WINDING_TRANSFORMER:
            if self.transformer_reactance_pu is None:
                raise ValueError("Two-winding transformer shunts require rated reactance metadata.")
            if self.transformer_correction_voltage_kv is None:
                raise ValueError(
                    "Two-winding transformer shunts require LV rated-voltage metadata."
                )


@dataclass(frozen=True, slots=True)
class SequenceMultiportElement:
    """Reciprocal multiport impedance element in one sequence network."""

    id: UUID
    name: str
    node_ids: tuple[UUID, UUID, UUID]
    impedance_matrix_pu: tuple[tuple[complex, complex, complex], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("SequenceMultiportElement.id must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("SequenceMultiportElement.name cannot be empty.")
        if not isinstance(self.node_ids, tuple) or len(self.node_ids) != 3:
            raise TypeError("node_ids must contain three port-node UUIDs.")
        if any(not isinstance(item, UUID) for item in self.node_ids):
            raise TypeError("Every multiport node identifier must be a UUID.")
        if len(set(self.node_ids)) != 3:
            raise ValueError("Multiport ports must reference three distinct nodes.")
        if not isinstance(self.impedance_matrix_pu, tuple) or len(self.impedance_matrix_pu) != 3:
            raise TypeError("impedance_matrix_pu must be a 3x3 immutable tuple.")
        converted = []
        for row in self.impedance_matrix_pu:
            if not isinstance(row, tuple) or len(row) != 3:
                raise TypeError("Every multiport impedance row must contain three values.")
            values = tuple(_finite_complex(value, "impedance_matrix_pu entry") for value in row)
            converted.append(values)
        matrix = tuple(converted)
        scale = max(abs(value) for row in matrix for value in row)
        if scale == 0.0:
            raise ValueError("Multiport impedance matrix cannot be zero.")
        tolerance = 1e-10 * scale
        for i in range(3):
            for j in range(3):
                if abs(matrix[i][j] - matrix[j][i]) > tolerance:
                    raise ValueError("Multiport impedance matrix must be reciprocal/symmetric.")
        real = tuple(tuple(matrix[i][j].real for j in range(3)) for i in range(3))
        resistance_scale = max(abs(value) for row in real for value in row)
        first_order_tolerance = 1e-10 * max(resistance_scale, 1e-30)
        second_order_tolerance = 1e-10 * max(resistance_scale**2, 1e-30)
        third_order_tolerance = 1e-10 * max(resistance_scale**3, 1e-30)
        diagonal = (real[0][0], real[1][1], real[2][2])
        principal_2 = (
            real[0][0] * real[1][1] - real[0][1] ** 2,
            real[0][0] * real[2][2] - real[0][2] ** 2,
            real[1][1] * real[2][2] - real[1][2] ** 2,
        )
        determinant_real = (
            real[0][0] * (real[1][1] * real[2][2] - real[1][2] ** 2)
            - real[0][1] * (real[0][1] * real[2][2] - real[1][2] * real[0][2])
            + real[0][2] * (real[0][1] * real[1][2] - real[1][1] * real[0][2])
        )
        if (
            any(value < -first_order_tolerance for value in diagonal)
            or any(value < -second_order_tolerance for value in principal_2)
            or determinant_real < -third_order_tolerance
        ):
            raise ValueError("Real part of the multiport impedance matrix must be passive (PSD).")
        determinant = _determinant_3x3(matrix)
        if abs(determinant) <= 1e-14 * scale**3:
            raise ValueError("Multiport impedance matrix must be nonsingular.")
        object.__setattr__(self, "impedance_matrix_pu", matrix)


@dataclass(frozen=True, slots=True)
class SequenceMutualCoupling:
    """Mutual series impedance between two physical branches in one sequence."""

    sequence: SequenceType
    first_branch_id: UUID
    second_branch_id: UUID
    mutual_impedance_pu: complex

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        if not isinstance(self.first_branch_id, UUID) or not isinstance(
            self.second_branch_id, UUID
        ):
            raise TypeError("Coupled branch identifiers must be UUID values.")
        if self.first_branch_id == self.second_branch_id:
            raise ValueError("A branch cannot be mutually coupled with itself.")
        object.__setattr__(
            self,
            "mutual_impedance_pu",
            _finite_complex(self.mutual_impedance_pu, "mutual_impedance_pu"),
        )


@dataclass(frozen=True, slots=True)
class SequenceNetwork:
    """One assembled topological sequence model before matrix discretization."""

    network_id: UUID
    sequence: SequenceType
    nodes: tuple[SequenceNode, ...]
    branches: tuple[SequenceBranch, ...]
    shunts: tuple[SequenceShunt, ...]
    diagnostics: tuple[DomainDiagnostic, ...] = ()
    nonlinear_source_ids: tuple[UUID, ...] = ()
    reference_node_id: UUID = field(default_factory=uuid4)
    multiport_elements: tuple[SequenceMultiportElement, ...] = ()
    mutual_couplings: tuple[SequenceMutualCoupling, ...] = ()
    converter_capabilities: Mapping[UUID, ConverterFaultCurrentCapability] = field(
        default_factory=dict, repr=False, compare=False
    )
    converter_bus_ids: Mapping[UUID, UUID] = field(default_factory=dict, repr=False, compare=False)
    bus_node_map: Mapping[UUID, UUID] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.network_id, UUID):
            raise TypeError("network_id must be a UUID.")
        if not isinstance(self.sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        if not isinstance(self.nodes, tuple) or any(
            not isinstance(item, SequenceNode) for item in self.nodes
        ):
            raise TypeError("nodes must be a tuple of SequenceNode values.")
        if not isinstance(self.branches, tuple) or any(
            not isinstance(item, SequenceBranch) for item in self.branches
        ):
            raise TypeError("branches must be a tuple of SequenceBranch values.")
        if not isinstance(self.shunts, tuple) or any(
            not isinstance(item, SequenceShunt) for item in self.shunts
        ):
            raise TypeError("shunts must be a tuple of SequenceShunt values.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(x, DomainDiagnostic) for x in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")
        if not isinstance(self.nonlinear_source_ids, tuple) or any(
            not isinstance(x, UUID) for x in self.nonlinear_source_ids
        ):
            raise TypeError("nonlinear_source_ids must be a tuple of UUID values.")
        if len(self.nonlinear_source_ids) != len(set(self.nonlinear_source_ids)):
            raise ValueError("nonlinear_source_ids must be unique.")
        if not isinstance(self.multiport_elements, tuple) or any(
            not isinstance(item, SequenceMultiportElement) for item in self.multiport_elements
        ):
            raise TypeError(
                "multiport_elements must be a tuple of SequenceMultiportElement values."
            )
        if not isinstance(self.mutual_couplings, tuple) or any(
            not isinstance(item, SequenceMutualCoupling) for item in self.mutual_couplings
        ):
            raise TypeError("mutual_couplings must be a tuple of SequenceMutualCoupling values.")
        if not isinstance(self.converter_capabilities, Mapping):
            raise TypeError("converter_capabilities must be a mapping.")
        capabilities = dict(self.converter_capabilities)
        if any(not isinstance(key, UUID) for key in capabilities):
            raise TypeError("Converter capability keys must be UUID values.")
        if any(
            not isinstance(value, ConverterFaultCurrentCapability)
            for value in capabilities.values()
        ):
            raise TypeError("Converter capability values must be ConverterFaultCurrentCapability.")
        if not set(capabilities).issubset(set(self.nonlinear_source_ids)):
            raise ValueError(
                "Converter capabilities may only be supplied for nonlinear source IDs."
            )
        object.__setattr__(self, "converter_capabilities", MappingProxyType(capabilities))
        if not isinstance(self.converter_bus_ids, Mapping):
            raise TypeError("converter_bus_ids must be a mapping.")
        converter_bus_ids = dict(self.converter_bus_ids)
        if any(
            not isinstance(source_id, UUID) or not isinstance(bus_id, UUID)
            for source_id, bus_id in converter_bus_ids.items()
        ):
            raise TypeError("Converter bus mappings must contain UUID source and bus IDs.")
        if not set(converter_bus_ids).issubset(set(self.nonlinear_source_ids)):
            raise ValueError(
                "Converter bus mappings may only be supplied for nonlinear source IDs."
            )
        if set(converter_bus_ids) != set(capabilities):
            raise ValueError("Converter bus and capability mappings must use the same source IDs.")
        if any(
            bus_id not in {node.id for node in self.nodes} for bus_id in converter_bus_ids.values()
        ):
            raise ValueError("Converter bus mappings must reference nodes in the sequence network.")
        object.__setattr__(self, "converter_bus_ids", MappingProxyType(converter_bus_ids))
        if not isinstance(self.bus_node_map, Mapping):
            raise TypeError("bus_node_map must map physical bus UUIDs to sequence node UUIDs.")
        bus_node_map = dict(self.bus_node_map)
        if any(
            not isinstance(bus_id, UUID) or not isinstance(node_id, UUID)
            for bus_id, node_id in bus_node_map.items()
        ):
            raise TypeError("Every bus_node_map key and value must be a UUID.")
        if any(
            node_id not in {node.id for node in self.nodes} for node_id in bus_node_map.values()
        ):
            raise ValueError("bus_node_map values must reference nodes in the sequence network.")
        object.__setattr__(self, "bus_node_map", MappingProxyType(bus_node_map))
        if not isinstance(self.reference_node_id, UUID):
            raise TypeError("reference_node_id must be a UUID.")
        ids = tuple(node.id for node in self.nodes)
        if len(ids) != len(set(ids)):
            raise ValueError("Sequence network node identifiers must be unique.")
        node_ids = set(ids)
        if self.reference_node_id in node_ids:
            raise ValueError("The sequence reference node ID cannot collide with a network node.")
        for branch in self.branches:
            if branch.from_node_id not in node_ids or branch.to_node_id not in node_ids:
                raise ValueError(f"Branch '{branch.name}' references an unknown node.")
        for shunt in self.shunts:
            if shunt.node_id not in node_ids:
                raise ValueError(f"Shunt '{shunt.name}' references an unknown node.")
        for element in self.multiport_elements:
            if any(node_id not in node_ids for node_id in element.node_ids):
                raise ValueError(f"Multiport '{element.name}' references an unknown node.")
        branch_by_id = {branch.id: branch for branch in self.branches}
        coupling_pairs = set()
        coupled_branch_ids = set()
        for coupling in self.mutual_couplings:
            if coupling.sequence is not self.sequence:
                raise ValueError("Mutual coupling sequence must match its containing network.")
            pair = frozenset((coupling.first_branch_id, coupling.second_branch_id))
            if pair in coupling_pairs:
                raise ValueError("A branch pair cannot have duplicate mutual-coupling entries.")
            coupling_pairs.add(pair)
            if coupled_branch_ids.intersection(pair):
                raise ValueError(
                    "Pairwise mutual-coupling models cannot reuse a branch; "
                    "use a full multi-branch impedance matrix."
                )
            coupled_branch_ids.update(pair)
            try:
                first = branch_by_id[coupling.first_branch_id]
                second = branch_by_id[coupling.second_branch_id]
            except KeyError as exc:
                raise ValueError("Mutual coupling references an unknown sequence branch.") from exc
            if (
                first.equipment_kind is not SequenceEquipmentKind.LINE
                or second.equipment_kind is not SequenceEquipmentKind.LINE
            ):
                raise ValueError(
                    "Mutual coupling is currently supported only between line branches."
                )
            if (first.from_node_id, first.to_node_id) != (second.from_node_id, second.to_node_id):
                raise ValueError(
                    "Mutually coupled line branches must share the same oriented terminal buses."
                )
            if abs(first.tap_from - 1.0) > 1e-12 or abs(second.tap_from - 1.0) > 1e-12:
                raise ValueError("Mutually coupled line branches must use unit taps.")
            for diagonal, name in (
                (first.series_impedance_pu.real, "first branch resistance"),
                (second.series_impedance_pu.real, "second branch resistance"),
            ):
                if diagonal < 0.0:
                    raise ValueError(f"Mutual coupling requires non-negative {name}.")
            for diagonal, name in (
                (first.series_impedance_pu.imag, "first branch reactance"),
                (second.series_impedance_pu.imag, "second branch reactance"),
            ):
                if diagonal < 0.0:
                    raise ValueError(f"Mutual coupling requires non-negative {name}.")
            mutual = coupling.mutual_impedance_pu
            real_determinant = (
                first.series_impedance_pu.real * second.series_impedance_pu.real - mutual.real**2
            )
            imag_determinant = (
                first.series_impedance_pu.imag * second.series_impedance_pu.imag - mutual.imag**2
            )
            scale = max(
                abs(first.series_impedance_pu),
                abs(second.series_impedance_pu),
                abs(mutual),
                1e-15,
            )
            tolerance = 1e-10 * scale**2
            if real_determinant < -tolerance or imag_determinant < -tolerance:
                raise ValueError(
                    "Mutual impedance must preserve passive resistance and inductance matrices."
                )

    @property
    def is_complete(self) -> bool:
        return not any(item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics)

    @property
    def requires_nonlinear_source_solver(self) -> bool:
        return bool(self.nonlinear_source_ids)


@dataclass(frozen=True, slots=True)
class SequenceNetworkSet:
    """The ordered positive, negative and zero sequence networks of one physical network."""

    positive: SequenceNetwork
    negative: SequenceNetwork
    zero: SequenceNetwork

    def __post_init__(self) -> None:
        expected = (
            (self.positive, SequenceType.POSITIVE),
            (self.negative, SequenceType.NEGATIVE),
            (self.zero, SequenceType.ZERO),
        )
        network_ids = set()
        for model, sequence in expected:
            if not isinstance(model, SequenceNetwork):
                raise TypeError("Every member must be a SequenceNetwork.")
            if model.sequence is not sequence:
                raise ValueError(f"Expected {sequence.value}-sequence network.")
            network_ids.add(model.network_id)
        if len(network_ids) != 1:
            raise ValueError("All sequence networks must originate from the same physical network.")

    @property
    def network_id(self) -> UUID:
        """Physical network identity shared by all three sequence networks."""
        return self.positive.network_id

    def for_sequence(self, sequence: SequenceType) -> SequenceNetwork:
        if not isinstance(sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        return {
            SequenceType.POSITIVE: self.positive,
            SequenceType.NEGATIVE: self.negative,
            SequenceType.ZERO: self.zero,
        }[sequence]
