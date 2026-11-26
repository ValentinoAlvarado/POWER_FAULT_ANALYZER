"""Topology-derived short-circuit scenario planning for protection studies."""

from __future__ import annotations

from collections.abc import Sequence
from numbers import Real
from uuid import NAMESPACE_URL, uuid5

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.protection_network import ProtectionFaultLocationKind
from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.domain.value_objects.protection_network import ProtectionFaultScenario
from power_fault_analyzer.equipment.transmission.line import Line


class ProtectionScenarioCatalog:
    """Generate a reproducible fault-location matrix from physical topology.

    Bus scenarios are labeled as IEC 60909 maximum/minimum cases because the
    ND-008 bus calculator supports those cases. Interior-line scenarios are
    uncorrected symmetrical-component locations; they deliberately carry no
    IEC 60909 current-case label until an IEC line-fault method is implemented.
    """

    _DEFAULT_FAULT_TYPES = (
        FaultType.THREE_PHASE,
        FaultType.SINGLE_LINE_TO_GROUND,
        FaultType.LINE_TO_LINE,
        FaultType.DOUBLE_LINE_TO_GROUND,
    )

    def generate(
        self,
        network: NetworkAggregate,
        *,
        fault_types: Sequence[FaultType] | None = None,
        line_fault_fractions: Sequence[float] = (0.1, 0.5, 0.9),
        include_bus_faults: bool = True,
        include_line_faults: bool = True,
    ) -> tuple[ProtectionFaultScenario, ...]:
        if not isinstance(network, NetworkAggregate):
            raise TypeError("network must implement NetworkAggregate.")
        selected_faults = tuple(self._DEFAULT_FAULT_TYPES if fault_types is None else fault_types)
        if not selected_faults or any(not isinstance(item, FaultType) for item in selected_faults):
            raise ValueError("fault_types must contain one or more FaultType values.")
        if len(selected_faults) != len(set(selected_faults)):
            raise ValueError("fault_types cannot contain duplicates.")
        if not isinstance(include_bus_faults, bool) or not isinstance(include_line_faults, bool):
            raise TypeError("include_bus_faults and include_line_faults must be bool values.")
        raw_fractions = tuple(line_fault_fractions)
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in raw_fractions):
            raise TypeError("line_fault_fractions must contain real numeric values, not bool.")
        fractions = tuple(float(value) for value in raw_fractions)
        if any(not 0.0 < value < 1.0 for value in fractions):
            raise ValueError("Every line fault fraction must be strictly between zero and one.")
        if len(fractions) != len(set(fractions)):
            raise ValueError("line_fault_fractions cannot contain duplicates.")

        scenarios: list[ProtectionFaultScenario] = []
        if include_bus_faults:
            for bus in network.buses:
                for fault_type in selected_faults:
                    for current_case in (IEC60909CurrentCase.MAXIMUM, IEC60909CurrentCase.MINIMUM):
                        scenario_key = (
                            f"pfa:{network.id}:bus:{bus.id}:{fault_type.value}:{current_case.value}"
                        )
                        scenario_id = uuid5(NAMESPACE_URL, scenario_key)
                        scenarios.append(
                            ProtectionFaultScenario(
                                id=scenario_id,
                                name=f"{bus.name}:{fault_type.value}:{current_case.value}",
                                location_kind=ProtectionFaultLocationKind.BUS,
                                location_id=bus.id,
                                fault_type=fault_type,
                                current_case=current_case,
                            )
                        )
        if include_line_faults:
            connection_by_terminal = {item.terminal_id: item.bus_id for item in network.connections}
            for equipment in network.equipment:
                if not isinstance(equipment, Line):
                    continue
                if any(
                    terminal.id not in connection_by_terminal for terminal in equipment.terminals
                ):
                    continue
                for fraction in fractions:
                    for fault_type in selected_faults:
                        fraction_text = f"{fraction:.12g}"
                        scenario_key = (
                            f"pfa:{network.id}:line:{equipment.id}:"
                            f"{fraction_text}:{fault_type.value}"
                        )
                        scenario_id = uuid5(NAMESPACE_URL, scenario_key)
                        scenarios.append(
                            ProtectionFaultScenario(
                                id=scenario_id,
                                name=f"{equipment.name}:lambda={fraction_text}:{fault_type.value}",
                                location_kind=ProtectionFaultLocationKind.LINE,
                                location_id=equipment.id,
                                fault_type=fault_type,
                                fraction_from=fraction,
                            )
                        )
        return tuple(scenarios)
