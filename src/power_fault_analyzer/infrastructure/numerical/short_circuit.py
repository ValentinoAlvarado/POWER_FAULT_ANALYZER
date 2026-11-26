"""Bus short-circuit calculations using sparse sequence-network equivalents."""

from __future__ import annotations

import cmath
import math
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from scipy.sparse.linalg import splu

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.converter_current_command import (
    ConverterSequenceCurrentCommand,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.fault_specification import (
    FaultSpecification,
)
from power_fault_analyzer.domain.value_objects.short_circuit_result import (
    ShortCircuitResult,
)
from power_fault_analyzer.infrastructure.numerical.ybus import (
    IncompleteSequenceNetworkError,
    SingularAdmittanceMatrixError,
    SparseYBusAssembler,
    YBusMatrix,
)
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetworkSet,
    SystemBaseSet,
)


class ShortCircuitCalculationError(RuntimeError):
    """Base error for an invalid or unsolvable short-circuit study."""


class UnknownFaultBusError(ShortCircuitCalculationError):
    """Raised when the requested fault bus is absent from a sequence network."""


class NonlinearSourceCalculationRequiredError(ShortCircuitCalculationError):
    """Raised when a converter source needs a nonlinear current-limit solution."""


class SingularFaultEquivalentError(ShortCircuitCalculationError):
    """Raised when the fault-boundary equations have no unique finite solution."""


@dataclass(frozen=True, slots=True)
class SequenceTheveninEquivalent:
    """Driving-point Thevenin equivalent of one sequence network at one bus."""

    sequence: SequenceType
    bus_id: UUID
    prefault_voltage_pu: complex
    driving_point_impedance_pu: complex

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        if not isinstance(self.bus_id, UUID):
            raise TypeError("bus_id must be a UUID value.")
        for name in ("prefault_voltage_pu", "driving_point_impedance_pu"):
            value = complex(getattr(self, name))
            if not math.isfinite(value.real) or not math.isfinite(value.imag):
                raise ValueError(f"{name} must be finite.")
            object.__setattr__(self, name, value)


class SparseTheveninCalculator:
    """Reduce a sparse Ybus matrix to a bus driving-point Thevenin equivalent."""

    def calculate(
        self,
        ybus: YBusMatrix,
        bus_id: UUID,
        *,
        additional_current_injection_pu: np.ndarray | None = None,
    ) -> SequenceTheveninEquivalent:
        if not isinstance(ybus, YBusMatrix):
            raise TypeError("ybus must be a YBusMatrix value.")
        if not isinstance(bus_id, UUID):
            raise TypeError("bus_id must be a UUID value.")
        if not ybus.is_complete:
            error_codes = [
                item.code for item in ybus.diagnostics if item.severity is DiagnosticSeverity.ERROR
            ]
            raise IncompleteSequenceNetworkError(
                "Cannot calculate a Thevenin equivalent from an incomplete sequence network; "
                "resolve diagnostics: " + ", ".join(error_codes)
            )
        try:
            index = ybus.node_index[bus_id]
        except KeyError as exc:
            raise UnknownFaultBusError(
                f"Fault bus '{bus_id}' is not present in the {ybus.sequence.value}-sequence Ybus."
            ) from exc

        component = self._connected_component_indices(ybus, index)
        reduced_matrix = ybus.matrix[component, :][:, component].tocsc()
        try:
            factorization = splu(reduced_matrix)
        except RuntimeError as exc:
            raise SingularAdmittanceMatrixError(
                f"{ybus.sequence.value}-sequence fault component is singular or unsolvable: {exc}"
            ) from exc

        total_injection = ybus.current_injection_pu[component].copy()
        if additional_current_injection_pu is not None:
            additional = np.asarray(additional_current_injection_pu, dtype=np.complex128)
            if additional.shape != (len(ybus.node_ids),):
                raise ValueError("Additional current injection must have one value per Ybus node.")
            if not np.isfinite(additional.real).all() or not np.isfinite(additional.imag).all():
                raise ValueError("Additional current injection must contain finite values.")
            total_injection += additional[component]
        prefault_voltages = factorization.solve(total_injection)
        local_index = int(np.flatnonzero(component == index)[0])
        unit_current = np.zeros(len(component), dtype=np.complex128)
        unit_current[local_index] = 1.0 + 0.0j
        impedance_column = factorization.solve(unit_current)
        return SequenceTheveninEquivalent(
            sequence=ybus.sequence,
            bus_id=bus_id,
            prefault_voltage_pu=complex(prefault_voltages[local_index]),
            driving_point_impedance_pu=complex(impedance_column[local_index]),
        )

    @staticmethod
    def _connected_component_indices(ybus: YBusMatrix, start_index: int) -> np.ndarray:
        """Return the undirected graph component containing one Ybus node.

        Open switchgear and sequence-dependent grounding can leave other buses
        electrically isolated in a particular sequence. Such unrelated rows
        must not make the fault-point Thevenin equivalent singular.
        """
        matrix = ybus.matrix.tocsr()
        adjacency: list[set[int]] = [set() for _ in ybus.node_ids]
        for row in range(matrix.shape[0]):
            start, stop = matrix.indptr[row], matrix.indptr[row + 1]
            for column, value in zip(matrix.indices[start:stop], matrix.data[start:stop]):
                if row != column and value != 0.0j:
                    adjacency[row].add(int(column))
                    adjacency[int(column)].add(row)

        visited = {start_index}
        pending = [start_index]
        while pending:
            current = pending.pop()
            for neighbor in adjacency[current] - visited:
                visited.add(neighbor)
                pending.append(neighbor)
        return np.asarray(sorted(visited), dtype=np.intp)


class ShortCircuitSolver:
    """Solve canonical bus faults through the sequence-domain Thevenin equivalents.

    Faults are located at physical buses. Converter sources may contribute only
    through explicit, engineer/vendor-supplied steady-state sequence-current
    phasors checked against the registered capability. PLL, current-priority,
    voltage-dependent limiter and dynamic control laws are not inferred.
    Line-interior faults and IEC 60909 correction factors use separate solvers.
    """

    _REQUIRED_SEQUENCES: Mapping[FaultType, tuple[SequenceType, ...]] = {
        FaultType.THREE_PHASE: (SequenceType.POSITIVE,),
        FaultType.SINGLE_LINE_TO_GROUND: (
            SequenceType.ZERO,
            SequenceType.POSITIVE,
            SequenceType.NEGATIVE,
        ),
        FaultType.LINE_TO_LINE: (SequenceType.POSITIVE, SequenceType.NEGATIVE),
        FaultType.DOUBLE_LINE_TO_GROUND: (
            SequenceType.ZERO,
            SequenceType.POSITIVE,
            SequenceType.NEGATIVE,
        ),
    }
    _DENOMINATOR_TOLERANCE = 1e-12

    def __init__(
        self,
        *,
        assembler: SparseYBusAssembler | None = None,
        thevenin_calculator: SparseTheveninCalculator | None = None,
    ) -> None:
        self._assembler = assembler or SparseYBusAssembler()
        self._thevenin_calculator = thevenin_calculator or SparseTheveninCalculator()

    def solve(
        self,
        networks: SequenceNetworkSet,
        fault: FaultSpecification,
        system_base: SystemBaseSet,
        *,
        prefault_sequence_voltage_override: Mapping[SequenceType, complex] | None = None,
        converter_current_commands: tuple[ConverterSequenceCurrentCommand, ...] = (),
    ) -> ShortCircuitResult:
        """Calculate sequence and phase currents/voltages for a bus fault."""
        if not isinstance(networks, SequenceNetworkSet):
            raise TypeError("networks must be a SequenceNetworkSet value.")
        if not isinstance(fault, FaultSpecification):
            raise TypeError("fault must be a FaultSpecification value.")
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet value.")
        if not isinstance(converter_current_commands, tuple) or any(
            not isinstance(item, ConverterSequenceCurrentCommand)
            for item in converter_current_commands
        ):
            raise TypeError(
                "converter_current_commands must be a tuple of "
                "ConverterSequenceCurrentCommand values."
            )
        converter_ids = tuple(item.source_id for item in converter_current_commands)
        if len(converter_ids) != len(set(converter_ids)):
            raise ValueError("Converter current commands must have unique source IDs.")
        command_by_source = {item.source_id: item for item in converter_current_commands}
        required_sequences = set(self._REQUIRED_SEQUENCES[fault.fault_type])
        for command in converter_current_commands:
            command.validate_limits(system_base)
            for sequence in set(SequenceType) - required_sequences:
                if abs(command.sequence_currents_pu[sequence]) > 1e-12:
                    raise NonlinearSourceCalculationRequiredError(
                        f"{sequence.value}-sequence current command for source "
                        f"'{command.source_id}' is incompatible with a "
                        f"{fault.fault_type.value} fault and would otherwise be ignored."
                    )
        try:
            bus_base = system_base.for_bus(fault.bus_id)
        except KeyError as exc:
            raise UnknownFaultBusError(str(exc)) from exc
        if prefault_sequence_voltage_override is not None:
            if not isinstance(prefault_sequence_voltage_override, Mapping):
                raise TypeError("prefault_sequence_voltage_override must be a mapping or None.")
            for sequence, voltage in prefault_sequence_voltage_override.items():
                if not isinstance(sequence, SequenceType):
                    raise TypeError("Prefault voltage override keys must be SequenceType values.")
                if isinstance(voltage, bool) or not isinstance(voltage, (int, float, complex)):
                    raise TypeError("Prefault voltage overrides must be real or complex numbers.")
                number = complex(voltage)
                if not math.isfinite(number.real) or not math.isfinite(number.imag):
                    raise ValueError("Prefault voltage overrides must be finite.")

        equivalents: dict[SequenceType, SequenceTheveninEquivalent] = {}
        diagnostics = []
        for sequence in self._REQUIRED_SEQUENCES[fault.fault_type]:
            sequence_network = networks.for_sequence(sequence)
            ybus = self._assembler.assemble(sequence_network)
            if set(sequence_network.nonlinear_source_ids) != set(command_by_source):
                source_ids = (
                    ", ".join(str(item) for item in sequence_network.nonlinear_source_ids) or "none"
                )
                command_ids = ", ".join(str(item) for item in command_by_source) or "none"
                raise NonlinearSourceCalculationRequiredError(
                    f"The {sequence.value}-sequence converter source IDs ({source_ids}) "
                    f"do not match the supplied current commands ({command_ids})."
                )
            if sequence_network.nonlinear_source_ids:
                if set(sequence_network.converter_bus_ids) != set(command_by_source):
                    raise NonlinearSourceCalculationRequiredError(
                        f"The {sequence.value}-sequence network lacks registered "
                        "converter bus mappings."
                    )
                if set(sequence_network.converter_capabilities) != set(command_by_source):
                    raise NonlinearSourceCalculationRequiredError(
                        f"The {sequence.value}-sequence network lacks registered "
                        "converter capability data."
                    )
            converter_injection = np.zeros(len(ybus.node_ids), dtype=np.complex128)
            for source_id, command in command_by_source.items():
                if command.bus_id != sequence_network.converter_bus_ids[source_id]:
                    raise NonlinearSourceCalculationRequiredError(
                        f"Converter command bus does not match registered connection "
                        f"for source '{source_id}'."
                    )
                if command.capability != sequence_network.converter_capabilities[source_id]:
                    raise NonlinearSourceCalculationRequiredError(
                        f"Converter command capability differs from registered equipment "
                        f"data for source '{source_id}'."
                    )
                converter_injection[ybus.node_index[command.bus_id]] += (
                    command.sequence_currents_pu[sequence]
                )
            sequence_fault_bus_id = sequence_network.bus_node_map.get(fault.bus_id, fault.bus_id)
            equivalent = self._thevenin_calculator.calculate(
                ybus,
                sequence_fault_bus_id,
                additional_current_injection_pu=converter_injection,
            )
            equivalents[sequence] = equivalent
            diagnostics.extend(ybus.diagnostics)

        diagnostics.extend(
            DomainDiagnostic(
                code="SC-CONVERTER-FIXED-PHASOR-ASSUMPTION",
                message=(
                    f"Converter '{command.source_id}' is represented by fixed "
                    "engineer/vendor-supplied sequence-current phasors. No control-law "
                    "or voltage-dependent fault-current response is simulated."
                ),
                severity=DiagnosticSeverity.WARNING,
                entity_id=command.source_id,
            )
            for command in converter_current_commands
        )

        prefault = {
            sequence: equivalent.prefault_voltage_pu for sequence, equivalent in equivalents.items()
        }
        if prefault_sequence_voltage_override is not None:
            prefault.update(
                {
                    sequence: complex(voltage)
                    for sequence, voltage in prefault_sequence_voltage_override.items()
                }
            )
        impedances = {
            sequence: equivalent.driving_point_impedance_pu
            for sequence, equivalent in equivalents.items()
        }
        sequence_currents = self._solve_sequence_currents(
            fault.fault_type,
            fault.fault_impedance_pu,
            prefault,
            impedances,
        )
        sequence_voltages = {
            sequence: prefault.get(sequence, 0.0j) - impedances.get(sequence, 0.0j) * current
            for sequence, current in sequence_currents.items()
        }

        i0 = sequence_currents.get(SequenceType.ZERO, 0.0j)
        i1 = sequence_currents.get(SequenceType.POSITIVE, 0.0j)
        i2 = sequence_currents.get(SequenceType.NEGATIVE, 0.0j)
        v0 = sequence_voltages.get(SequenceType.ZERO, 0.0j)
        v1 = sequence_voltages.get(SequenceType.POSITIVE, 0.0j)
        v2 = sequence_voltages.get(SequenceType.NEGATIVE, 0.0j)
        phase_currents_pu = self._sequence_to_phase(i0, i1, i2)
        phase_voltages_pu = self._sequence_to_phase(v0, v1, v2)
        phase_currents_ka = tuple(value * bus_base.base_current_ka for value in phase_currents_pu)
        phase_voltages_kv = tuple(
            value * bus_base.base_voltage_kv / math.sqrt(3.0) for value in phase_voltages_pu
        )
        ground_current_pu = (
            3.0 * i0
            if fault.fault_type
            in (FaultType.SINGLE_LINE_TO_GROUND, FaultType.DOUBLE_LINE_TO_GROUND)
            else 0.0j
        )

        return ShortCircuitResult(
            fault_type=fault.fault_type,
            bus_id=fault.bus_id,
            fault_impedance_pu=fault.fault_impedance_pu,
            base_power_mva=bus_base.base_power_mva,
            base_voltage_kv=bus_base.base_voltage_kv,
            base_current_ka=bus_base.base_current_ka,
            prefault_sequence_voltages_pu=prefault,
            driving_point_impedances_pu=impedances,
            sequence_currents_pu=sequence_currents,
            sequence_fault_voltages_pu=sequence_voltages,
            phase_currents_pu=phase_currents_pu,
            phase_voltages_pu=phase_voltages_pu,
            phase_currents_ka=phase_currents_ka,
            phase_voltages_kv=phase_voltages_kv,
            ground_current_pu=ground_current_pu,
            ground_current_ka=ground_current_pu * bus_base.base_current_ka,
            diagnostics=tuple(diagnostics),
        )

    def _solve_sequence_currents(
        self,
        fault_type: FaultType,
        fault_impedance: complex,
        prefault: Mapping[SequenceType, complex],
        impedances: Mapping[SequenceType, complex],
    ) -> dict[SequenceType, complex]:
        e0 = prefault.get(SequenceType.ZERO, 0.0j)
        e1 = prefault.get(SequenceType.POSITIVE, 0.0j)
        e2 = prefault.get(SequenceType.NEGATIVE, 0.0j)
        z0 = impedances.get(SequenceType.ZERO, 0.0j)
        z1 = impedances.get(SequenceType.POSITIVE, 0.0j)
        z2 = impedances.get(SequenceType.NEGATIVE, 0.0j)

        if fault_type is FaultType.THREE_PHASE:
            denominator = z1 + fault_impedance
            current = self._safe_divide(e1, denominator, "three-phase fault")
            return {
                SequenceType.ZERO: 0.0j,
                SequenceType.POSITIVE: current,
                SequenceType.NEGATIVE: 0.0j,
            }

        if fault_type is FaultType.SINGLE_LINE_TO_GROUND:
            denominator = z0 + z1 + z2 + 3.0 * fault_impedance
            current = self._safe_divide(e0 + e1 + e2, denominator, "single-line-to-ground fault")
            return {
                SequenceType.ZERO: current,
                SequenceType.POSITIVE: current,
                SequenceType.NEGATIVE: current,
            }

        if fault_type is FaultType.LINE_TO_LINE:
            denominator = z1 + z2 + fault_impedance
            current = self._safe_divide(e1 - e2, denominator, "line-to-line fault")
            return {
                SequenceType.ZERO: 0.0j,
                SequenceType.POSITIVE: current,
                SequenceType.NEGATIVE: -current,
            }

        if fault_type is FaultType.DOUBLE_LINE_TO_GROUND:
            a = cmath.exp(2.0j * math.pi / 3.0)
            matrix = np.asarray(
                [
                    [1.0, 1.0, 1.0],
                    [0.0j, -z1, z2],
                    [-(z0 + 3.0 * fault_impedance), -(a**2) * z1, -a * z2],
                ],
                dtype=np.complex128,
            )
            right_hand_side = np.asarray(
                [0.0j, -(e1 - e2), -(e0 + (a**2) * e1 + a * e2)],
                dtype=np.complex128,
            )
            try:
                i0, i1, i2 = np.linalg.solve(matrix, right_hand_side)
            except np.linalg.LinAlgError as exc:
                raise SingularFaultEquivalentError(
                    "Double-line-to-ground fault boundary equations are singular."
                ) from exc
            return {
                SequenceType.ZERO: complex(i0),
                SequenceType.POSITIVE: complex(i1),
                SequenceType.NEGATIVE: complex(i2),
            }

        raise TypeError(f"Unsupported fault type: {fault_type!r}.")

    def _safe_divide(self, numerator: complex, denominator: complex, context: str) -> complex:
        if abs(denominator) <= self._DENOMINATOR_TOLERANCE:
            raise SingularFaultEquivalentError(
                f"The sequence Thevenin denominator for {context} is zero or near zero."
            )
        result = numerator / denominator
        if not math.isfinite(result.real) or not math.isfinite(result.imag):
            raise SingularFaultEquivalentError(
                f"The calculated current for {context} is not finite."
            )
        return result

    @staticmethod
    def _sequence_to_phase(
        zero: complex, positive: complex, negative: complex
    ) -> tuple[complex, complex, complex]:
        a = cmath.exp(2.0j * math.pi / 3.0)
        phase_a = zero + positive + negative
        phase_b = zero + (a**2) * positive + a * negative
        phase_c = zero + a * positive + (a**2) * negative
        return (phase_a, phase_b, phase_c)
