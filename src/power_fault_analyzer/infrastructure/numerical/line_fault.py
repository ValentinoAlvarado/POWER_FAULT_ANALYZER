"""Interior-line fault studies using split sequence branches and sparse Ybus solves."""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID, uuid5

import numpy as np

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.line_fault_result import (
    LineFaultStudyResult,
    LineTerminalState,
)
from power_fault_analyzer.domain.value_objects.line_fault_specification import (
    LineFaultSpecification,
)
from power_fault_analyzer.infrastructure.numerical.short_circuit import (
    ShortCircuitCalculationError,
    ShortCircuitSolver,
)
from power_fault_analyzer.infrastructure.numerical.ybus import SparseYBusAssembler
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SystemBaseSet,
)


class LineFaultCalculationError(ShortCircuitCalculationError):
    """Base error for an invalid or unsolvable line-interior fault study."""


class UnknownLineFaultBranchError(LineFaultCalculationError):
    """Raised when the requested branch is absent from a sequence network."""


class NonFaultableBranchError(LineFaultCalculationError):
    """Raised when the branch is not a line/cable with a declared physical length."""


@dataclass(frozen=True, slots=True)
class _SplitLine:
    fault_node_id: UUID
    from_bus_id: UUID
    to_bus_id: UUID
    original_branch: SequenceBranch
    left_branch: SequenceBranch
    right_branch: SequenceBranch
    network: SequenceNetwork


class LineFaultSolver:
    """Solve canonical short circuits at an interior point of a line or cable.

    The physical line's per-unit series impedance is divided in proportion to
    ``fraction_from``. Its existing nominal-pi terminal shunts remain at the
    physical line terminals, preserving the original ND-005 pre-fault branch
    equivalent. The new interior fault node has no added shunt.

    This is an interior split of the existing lumped sequence-line model. It is
    not a distributed-parameter travelling-wave model or an IEC 60909 solver.
    """

    _SEQUENCES = (
        SequenceType.POSITIVE,
        SequenceType.NEGATIVE,
        SequenceType.ZERO,
    )
    _REQUIRED_SEQUENCES: ClassVar[dict[FaultType, tuple[SequenceType, ...]]] = {
        # Keep the same selective sequence-network requirements as ND-006.
        FaultType.THREE_PHASE: (SequenceType.POSITIVE,),
        FaultType.SINGLE_LINE_TO_GROUND: (
            SequenceType.POSITIVE,
            SequenceType.NEGATIVE,
            SequenceType.ZERO,
        ),
        FaultType.LINE_TO_LINE: (SequenceType.POSITIVE, SequenceType.NEGATIVE),
        FaultType.DOUBLE_LINE_TO_GROUND: (
            SequenceType.POSITIVE,
            SequenceType.NEGATIVE,
            SequenceType.ZERO,
        ),
    }
    _TAP_TOLERANCE = 1e-12
    _BASE_TOLERANCE = 1e-8

    def __init__(
        self,
        *,
        short_circuit_solver: ShortCircuitSolver | None = None,
        assembler: SparseYBusAssembler | None = None,
    ) -> None:
        self._short_circuit_solver = short_circuit_solver or ShortCircuitSolver()
        self._assembler = assembler or SparseYBusAssembler()

    def solve(
        self,
        networks: SequenceNetworkSet,
        fault: LineFaultSpecification,
        system_base: SystemBaseSet,
    ) -> LineFaultStudyResult:
        """Calculate the fault and report voltage/current states at both line ends."""
        if not isinstance(networks, SequenceNetworkSet):
            raise TypeError("networks must be a SequenceNetworkSet value.")
        if not isinstance(fault, LineFaultSpecification):
            raise TypeError("fault must be a LineFaultSpecification value.")
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet value.")

        required = self._REQUIRED_SEQUENCES[fault.fault_type]
        split_by_sequence: dict[SequenceType, _SplitLine] = {}
        for sequence in required:
            sequence_network = networks.for_sequence(sequence)
            split_by_sequence[sequence] = self._split_network(sequence_network, fault)

        reference_split = split_by_sequence[SequenceType.POSITIVE]
        from_bus_id = reference_split.from_bus_id
        to_bus_id = reference_split.to_bus_id
        original_branch = reference_split.original_branch
        line_length = float(original_branch.length_km)
        for sequence, split in split_by_sequence.items():
            if (
                split.from_bus_id != from_bus_id
                or split.to_bus_id != to_bus_id
                or not math.isclose(
                    float(split.original_branch.length_km),
                    line_length,
                    rel_tol=self._BASE_TOLERANCE,
                    abs_tol=1e-9,
                )
            ):
                raise LineFaultCalculationError(
                    f"The {sequence.value}-sequence line branch has inconsistent terminal "
                    "topology or physical length."
                )
        self._validate_terminal_bases(system_base, from_bus_id, to_bus_id)

        fault_node_id = reference_split.fault_node_id
        extended_bases = dict(system_base.bus_voltage_bases_kv)
        from_base = system_base.for_bus(from_bus_id)
        extended_bases[fault_node_id] = from_base.base_voltage_kv
        fault_system_base = SystemBaseSet(system_base.base_power_mva, extended_bases)
        split_networks = SequenceNetworkSet(
            positive=split_by_sequence[SequenceType.POSITIVE].network,
            negative=(
                split_by_sequence[SequenceType.NEGATIVE].network
                if SequenceType.NEGATIVE in split_by_sequence
                else networks.negative
            ),
            zero=(
                split_by_sequence[SequenceType.ZERO].network
                if SequenceType.ZERO in split_by_sequence
                else networks.zero
            ),
        )
        bus_fault = FaultSpecification(
            fault_type=fault.fault_type,
            bus_id=fault_node_id,
            fault_impedance_pu=fault.fault_impedance_pu,
        )
        fault_result = self._short_circuit_solver.solve(
            split_networks,
            bus_fault,
            fault_system_base,
        )

        from_voltages: dict[SequenceType, complex] = {}
        to_voltages: dict[SequenceType, complex] = {}
        from_currents: dict[SequenceType, complex] = {}
        to_currents: dict[SequenceType, complex] = {}
        required_sequences = set(fault_result.driving_point_impedances_pu)

        for sequence in self._SEQUENCES:
            if sequence not in required_sequences:
                from_voltages[sequence] = 0.0j
                to_voltages[sequence] = 0.0j
                from_currents[sequence] = 0.0j
                to_currents[sequence] = 0.0j
                continue
            split = split_by_sequence[sequence]
            voltage_vector = self._solve_faulted_node_voltages(
                split.network,
                fault_node_id,
                fault_result.sequence_currents_pu[sequence],
            )
            indexes = {node.id: index for index, node in enumerate(split.network.nodes)}
            from_voltage = complex(voltage_vector[indexes[from_bus_id]])
            to_voltage = complex(voltage_vector[indexes[to_bus_id]])
            fault_voltage = complex(voltage_vector[indexes[fault_node_id]])
            from_voltages[sequence] = from_voltage
            to_voltages[sequence] = to_voltage
            from_currents[sequence] = self._terminal_current(
                from_voltage,
                fault_voltage,
                split.left_branch,
                from_end=True,
            )
            to_currents[sequence] = self._terminal_current(
                to_voltage,
                fault_voltage,
                split.right_branch,
                from_end=False,
            )

        from_state = self._terminal_state(
            from_bus_id,
            from_voltages,
            from_currents,
            system_base,
        )
        to_state = self._terminal_state(
            to_bus_id,
            to_voltages,
            to_currents,
            system_base,
        )
        distance_from = fault.fraction_from * line_length
        return LineFaultStudyResult(
            branch_id=fault.branch_id,
            line_name=original_branch.name,
            from_bus_id=from_bus_id,
            to_bus_id=to_bus_id,
            fault_node_id=fault_node_id,
            fraction_from=fault.fraction_from,
            line_length_km=line_length,
            distance_from_km=distance_from,
            distance_to_km=line_length - distance_from,
            fault_result=fault_result,
            from_terminal=from_state,
            to_terminal=to_state,
        )

    def _split_network(
        self,
        network: SequenceNetwork,
        fault: LineFaultSpecification,
    ) -> _SplitLine:
        matches = [branch for branch in network.branches if branch.id == fault.branch_id]
        if not matches:
            raise UnknownLineFaultBranchError(
                f"Branch '{fault.branch_id}' is not present in the "
                f"{network.sequence.value}-sequence network."
            )
        if len(matches) != 1:
            raise LineFaultCalculationError(
                f"Branch ID '{fault.branch_id}' is not unique in the "
                f"{network.sequence.value}-sequence network."
            )
        branch = matches[0]
        if branch.length_km is None:
            raise NonFaultableBranchError(
                f"Branch '{branch.name}' has no physical line length. Only modeled lines "
                "and cables support interior fault locations."
            )
        if abs(branch.tap_from - (1.0 + 0.0j)) > self._TAP_TOLERANCE:
            raise NonFaultableBranchError(
                f"Branch '{branch.name}' has a non-unity tap and cannot be split as a line."
            )
        token = fault.fraction_from.hex()
        fault_node_id = uuid5(branch.id, f"ND007:fault:{token}")
        left_id = uuid5(branch.id, f"ND007:left:{token}")
        right_id = uuid5(branch.id, f"ND007:right:{token}")
        existing_ids = {node.id for node in network.nodes}
        if fault_node_id in existing_ids:
            raise LineFaultCalculationError(
                "Generated fault-node UUID collides with an existing sequence-network node."
            )

        fraction = fault.fraction_from
        left = SequenceBranch(
            id=left_id,
            name=f"{branch.name} [FROM:{fraction:.6f}]",
            from_node_id=branch.from_node_id,
            to_node_id=fault_node_id,
            series_impedance_pu=branch.series_impedance_pu * fraction,
            shunt_admittance_from_pu=branch.shunt_admittance_from_pu,
            shunt_admittance_to_pu=0.0j,
            tap_from=1.0 + 0.0j,
            length_km=branch.length_km * fraction,
        )
        right = SequenceBranch(
            id=right_id,
            name=f"{branch.name} [TO:{1.0 - fraction:.6f}]",
            from_node_id=fault_node_id,
            to_node_id=branch.to_node_id,
            series_impedance_pu=branch.series_impedance_pu * (1.0 - fraction),
            shunt_admittance_from_pu=0.0j,
            shunt_admittance_to_pu=branch.shunt_admittance_to_pu,
            tap_from=1.0 + 0.0j,
            length_km=branch.length_km * (1.0 - fraction),
        )
        nodes = network.nodes + (
            SequenceNode(
                id=fault_node_id,
                label=f"{branch.name} fault @ {fraction:.6f}",
                is_internal=True,
            ),
        )
        branches: list[SequenceBranch] = []
        for candidate in network.branches:
            if candidate.id == branch.id:
                branches.extend((left, right))
            else:
                branches.append(candidate)
        split_network = SequenceNetwork(
            network_id=network.network_id,
            sequence=network.sequence,
            nodes=nodes,
            branches=tuple(branches),
            shunts=network.shunts,
            diagnostics=network.diagnostics,
            nonlinear_source_ids=network.nonlinear_source_ids,
            reference_node_id=network.reference_node_id,
        )
        return _SplitLine(
            fault_node_id=fault_node_id,
            from_bus_id=branch.from_node_id,
            to_bus_id=branch.to_node_id,
            original_branch=branch,
            left_branch=left,
            right_branch=right,
            network=split_network,
        )

    def _validate_terminal_bases(
        self,
        system_base: SystemBaseSet,
        from_bus_id: UUID,
        to_bus_id: UUID,
    ) -> None:
        try:
            from_voltage = system_base.for_bus(from_bus_id).base_voltage_kv
            to_voltage = system_base.for_bus(to_bus_id).base_voltage_kv
        except KeyError as exc:
            raise LineFaultCalculationError(
                "Both physical line terminal buses must have configured system voltage bases."
            ) from exc
        tolerance = max(from_voltage, to_voltage) * self._BASE_TOLERANCE
        if abs(from_voltage - to_voltage) > tolerance:
            raise LineFaultCalculationError(
                "An interior line fault requires equal voltage bases at both line terminals."
            )

    def _solve_faulted_node_voltages(
        self,
        network: SequenceNetwork,
        fault_node_id: UUID,
        fault_current_pu: complex,
    ) -> np.ndarray:
        ybus = self._assembler.assemble(network)
        indexes = ybus.node_index
        try:
            fault_index = indexes[fault_node_id]
        except KeyError as exc:
            raise LineFaultCalculationError(
                "Generated fault node is absent from the assembled sequence Ybus."
            ) from exc
        right_hand_side = np.array(ybus.current_injection_pu, dtype=np.complex128, copy=True)
        right_hand_side[fault_index] -= fault_current_pu
        try:
            return ybus.factorize().solve(right_hand_side)
        except (RuntimeError, ValueError) as exc:
            raise LineFaultCalculationError(
                f"Could not recover the {network.sequence.value}-sequence line voltages: {exc}"
            ) from exc

    @staticmethod
    def _terminal_current(
        terminal_voltage_pu: complex,
        fault_voltage_pu: complex,
        branch: SequenceBranch,
        *,
        from_end: bool,
    ) -> complex:
        """Return terminal current directed from the physical bus into the line."""
        series_current = (terminal_voltage_pu - fault_voltage_pu) / branch.series_impedance_pu
        shunt = branch.shunt_admittance_from_pu if from_end else branch.shunt_admittance_to_pu
        return complex(series_current + shunt * terminal_voltage_pu)

    @staticmethod
    def _sequence_to_phase(
        zero: complex,
        positive: complex,
        negative: complex,
    ) -> tuple[complex, complex, complex]:
        rotation = cmath.exp(2.0j * math.pi / 3.0)
        phase_a = zero + positive + negative
        phase_b = zero + rotation.conjugate() * positive + rotation * negative
        phase_c = zero + rotation * positive + rotation.conjugate() * negative
        return phase_a, phase_b, phase_c

    def _terminal_state(
        self,
        bus_id: UUID,
        sequence_voltages: dict[SequenceType, complex],
        sequence_currents: dict[SequenceType, complex],
        system_base: SystemBaseSet,
    ) -> LineTerminalState:
        base = system_base.for_bus(bus_id)
        phase_voltages_pu = self._sequence_to_phase(
            sequence_voltages[SequenceType.ZERO],
            sequence_voltages[SequenceType.POSITIVE],
            sequence_voltages[SequenceType.NEGATIVE],
        )
        phase_currents_pu = self._sequence_to_phase(
            sequence_currents[SequenceType.ZERO],
            sequence_currents[SequenceType.POSITIVE],
            sequence_currents[SequenceType.NEGATIVE],
        )
        return LineTerminalState(
            bus_id=bus_id,
            base_voltage_kv=base.base_voltage_kv,
            base_current_ka=base.base_current_ka,
            sequence_voltages_pu=sequence_voltages,
            sequence_currents_into_line_pu=sequence_currents,
            phase_voltages_pu=phase_voltages_pu,
            phase_voltages_kv=tuple(
                value * base.base_voltage_kv / math.sqrt(3.0) for value in phase_voltages_pu
            ),
            phase_currents_into_line_pu=phase_currents_pu,
            phase_currents_into_line_ka=tuple(
                value * base.base_current_ka for value in phase_currents_pu
            ),
        )
