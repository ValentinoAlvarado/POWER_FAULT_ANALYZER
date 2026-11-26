"""Loader and executable adapter for the independent analytical fault cases."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from importlib.resources import files
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.infrastructure.numerical.short_circuit import ShortCircuitSolver
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SequenceShunt,
    SystemBaseSet,
)


@dataclass(frozen=True, slots=True)
class AnalyticalReferenceCase:
    case_id: str
    title: str
    fault_type: FaultType
    fault_impedance_pu: complex
    network: dict[str, Any]
    expected: dict[str, Any]
    tolerances: dict[str, float]
    reference_method: str
    reference_equation: str

    def __post_init__(self) -> None:
        if not self.case_id or not self.title:
            raise ValueError("Reference case identifiers and titles cannot be empty.")
        if self.fault_impedance_pu.real < 0.0:
            raise ValueError("Reference fault resistance cannot be negative.")


def load_reference_dataset() -> tuple[str, str, tuple[AnalyticalReferenceCase, ...]]:
    resource = files("power_fault_analyzer.validation").joinpath(
        "data/nd016_analytical_fault_cases.json"
    )
    payload = json.loads(resource.read_text(encoding="utf-8"))
    cases = tuple(
        AnalyticalReferenceCase(
            case_id=item["case_id"],
            title=item["title"],
            fault_type=FaultType(item["fault_type"]),
            fault_impedance_pu=complex(*item["fault_impedance_pu"]),
            network=item["network"],
            expected=item["expected"],
            tolerances=item["tolerances"],
            reference_method=item["reference_method"],
            reference_equation=item["reference_equation"],
        )
        for item in payload["reference_cases"]
    )
    if len({item.case_id for item in cases}) != len(cases):
        raise ValueError("Analytical reference case identifiers must be unique.")
    return payload["dataset_id"], payload["basis"], cases


def solve_reference_case(case: AnalyticalReferenceCase, *, positive_sequence_scale: float = 1.0):
    """Run a fixed reference case through the production bus-fault solver.

    ``positive_sequence_scale`` is a sensitivity-study perturbation applied to the
    positive-sequence Thevenin impedance; the reference result uses exactly 1.0.
    """
    if not isinstance(case, AnalyticalReferenceCase):
        raise TypeError("case must be an AnalyticalReferenceCase.")
    if (
        isinstance(positive_sequence_scale, bool)
        or not isinstance(positive_sequence_scale, (int, float))
        or not math.isfinite(float(positive_sequence_scale))
        or positive_sequence_scale <= 0.0
    ):
        raise ValueError("positive_sequence_scale must be finite and positive.")
    bus_id = uuid5(NAMESPACE_URL, f"pfa-nd016:{case.case_id}:bus")
    network_id = uuid5(NAMESPACE_URL, f"pfa-nd016:{case.case_id}:network")
    node = SequenceNode(bus_id, f"{case.case_id}-BUS")
    source_voltage = complex(*case.network["prefault_positive_voltage_pu"])
    sequence_networks = {}
    for sequence in (SequenceType.ZERO, SequenceType.POSITIVE, SequenceType.NEGATIVE):
        impedance = complex(*case.network["sequence_impedances_pu"][sequence.value])
        if sequence is SequenceType.POSITIVE:
            impedance *= float(positive_sequence_scale)
        emf = source_voltage if sequence is SequenceType.POSITIVE else 0.0j
        sequence_networks[sequence] = SequenceNetwork(
            network_id=network_id,
            sequence=sequence,
            nodes=(node,),
            branches=(),
            shunts=(
                SequenceShunt(
                    id=uuid5(NAMESPACE_URL, f"pfa-nd016:{case.case_id}:{sequence.value}:source"),
                    name=f"{case.case_id}-{sequence.value.upper()}-THEVENIN",
                    node_id=bus_id,
                    admittance_pu=1.0 / impedance,
                    source_voltage_pu=emf,
                    source_kind=SequenceSourceKind.EXPLICIT_THEVENIN,
                ),
            ),
        )
    networks = SequenceNetworkSet(
        positive=sequence_networks[SequenceType.POSITIVE],
        negative=sequence_networks[SequenceType.NEGATIVE],
        zero=sequence_networks[SequenceType.ZERO],
    )
    system_base = SystemBaseSet(
        base_power_mva=float(case.network["base_power_mva"]),
        bus_voltage_bases_kv={bus_id: float(case.network["base_voltage_ll_kv"])},
    )
    result = ShortCircuitSolver().solve(
        networks,
        FaultSpecification(case.fault_type, bus_id, case.fault_impedance_pu),
        system_base,
    )
    return result
