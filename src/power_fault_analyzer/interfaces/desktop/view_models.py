"""Presentation-neutral row formatting for numerical fault results."""

from __future__ import annotations

import cmath
import math

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult

_PHASES = ("A", "B", "C")


def _magnitude(value: complex) -> str:
    return f"{abs(value):.9f}"


def _angle(value: complex) -> str:
    return f"{math.degrees(cmath.phase(value)):.6f}"


def phase_result_rows(result: ShortCircuitResult) -> tuple[tuple[str, ...], ...]:
    """Build display rows from solver outputs; no electrical calculation is repeated."""
    return tuple(
        (
            phase,
            _magnitude(result.phase_currents_pu[index]),
            _angle(result.phase_currents_pu[index]),
            _magnitude(result.phase_currents_ka[index]),
            _magnitude(result.phase_voltages_pu[index]),
            _angle(result.phase_voltages_pu[index]),
            _magnitude(result.phase_voltages_kv[index]),
            f"{result.phase_currents_pu[index].real:.9f}",
            f"{result.phase_currents_pu[index].imag:.9f}",
        )
        for index, phase in enumerate(_PHASES)
    )


def sequence_result_rows(result: ShortCircuitResult) -> tuple[tuple[str, ...], ...]:
    rows = []
    for sequence in (SequenceType.ZERO, SequenceType.POSITIVE, SequenceType.NEGATIVE):
        current = result.sequence_currents_pu.get(sequence)
        voltage = result.sequence_fault_voltages_pu.get(sequence)
        impedance = result.driving_point_impedances_pu.get(sequence)
        rows.append(
            (
                sequence.value,
                _magnitude(current) if current is not None else "Not available",
                _angle(current) if current is not None else "Not available",
                _magnitude(voltage) if voltage is not None else "Not available",
                _angle(voltage) if voltage is not None else "Not available",
                _magnitude(impedance) if impedance is not None else "Not calculated",
                _angle(impedance) if impedance is not None else "Not calculated",
            )
        )
    return tuple(rows)
