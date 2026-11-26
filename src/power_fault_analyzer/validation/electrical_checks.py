"""Unit, base, sequence-transform and fault-boundary audits for solver results."""

from __future__ import annotations

import cmath
import math

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.validation.models import AuditCheck, ElectricalAudit


def audit_short_circuit_result(
    result: ShortCircuitResult,
    *,
    absolute_tolerance: float = 1e-9,
) -> ElectricalAudit:
    if not isinstance(result, ShortCircuitResult):
        raise TypeError("result must be a ShortCircuitResult.")
    if not math.isfinite(absolute_tolerance) or absolute_tolerance < 0.0:
        raise ValueError("absolute_tolerance must be finite and non-negative.")
    checks: list[AuditCheck] = []

    def add(check_id: str, description: str, residual: float, tolerance: float, unit: str) -> None:
        checks.append(
            AuditCheck(
                check_id,
                description,
                residual <= tolerance,
                float(residual),
                float(tolerance),
                unit,
            )
        )

    expected_base_current = result.base_power_mva / (math.sqrt(3.0) * result.base_voltage_kv)
    add(
        "BASE-CURRENT",
        "Ibase = Sbase / (sqrt(3) VLL,base)",
        abs(result.base_current_ka - expected_base_current),
        max(absolute_tolerance, abs(expected_base_current) * 1e-10),
        "kA",
    )
    phase_current_residual = max(
        abs(physical - per_unit * result.base_current_ka)
        for physical, per_unit in zip(
            result.phase_currents_ka, result.phase_currents_pu, strict=True
        )
    )
    add(
        "PHASE-CURRENT-BASE",
        "Phase-current conversion from p.u. to kA",
        phase_current_residual,
        absolute_tolerance,
        "kA",
    )
    phase_voltage_base_kv = result.base_voltage_kv / math.sqrt(3.0)
    phase_voltage_residual = max(
        abs(physical - per_unit * phase_voltage_base_kv)
        for physical, per_unit in zip(
            result.phase_voltages_kv, result.phase_voltages_pu, strict=True
        )
    )
    add(
        "PHASE-VOLTAGE-BASE",
        "Phase-neutral voltage conversion from p.u. to kV",
        phase_voltage_residual,
        absolute_tolerance,
        "kV",
    )

    i0 = result.sequence_currents_pu.get(SequenceType.ZERO, 0.0j)
    i1 = result.sequence_currents_pu.get(SequenceType.POSITIVE, 0.0j)
    i2 = result.sequence_currents_pu.get(SequenceType.NEGATIVE, 0.0j)
    a = cmath.exp(2j * math.pi / 3.0)
    phase_reference = (
        i0 + i1 + i2,
        i0 + a**2 * i1 + a * i2,
        i0 + a * i1 + a**2 * i2,
    )
    sequence_residual = max(
        abs(actual - expected)
        for actual, expected in zip(result.phase_currents_pu, phase_reference, strict=True)
    )
    add(
        "SEQUENCE-PHASE-CONSISTENCY",
        "Symmetrical-component to A-B-C current transform",
        sequence_residual,
        absolute_tolerance,
        "p.u.",
    )
    add(
        "GROUND-CURRENT",
        "Ig = 3 I0",
        abs(result.ground_current_pu - 3.0 * i0),
        absolute_tolerance,
        "p.u.",
    )
    add(
        "GROUND-CURRENT-BASE",
        "Ground-current p.u. to kA conversion",
        abs(result.ground_current_ka - result.ground_current_pu * result.base_current_ka),
        absolute_tolerance,
        "kA",
    )

    ia, ib, ic = result.phase_currents_pu
    _va, vb, vc = result.phase_voltages_pu
    if result.fault_type is FaultType.THREE_PHASE:
        residual = max(abs(i0), abs(i2), abs(ia + a**2 * ib + a * ic))
        add(
            "BC-THREE-PHASE",
            "Balanced three-phase current and zero I0/I2",
            residual,
            absolute_tolerance,
            "p.u.",
        )
    elif result.fault_type is FaultType.SINGLE_LINE_TO_GROUND:
        add("BC-SLG", "A-G fault: Ib = Ic = 0", max(abs(ib), abs(ic)), absolute_tolerance, "p.u.")
    elif result.fault_type is FaultType.LINE_TO_LINE:
        add(
            "BC-LL",
            "B-C fault: Ia = 0, Ib = -Ic, I0 = 0",
            max(abs(ia), abs(ib + ic), abs(i0)),
            absolute_tolerance,
            "p.u.",
        )
    elif result.fault_type is FaultType.DOUBLE_LINE_TO_GROUND:
        add("BC-DLG-CURRENT", "B-C-G fault: Ia = 0", abs(ia), absolute_tolerance, "p.u.")
        add("BC-DLG-VOLTAGE", "B-C-G fault: Vb = Vc", abs(vb - vc), absolute_tolerance, "p.u.")
        add(
            "BC-DLG-GROUND",
            "B-C-G fault: Ig = Ib + Ic",
            abs(result.ground_current_pu - (ib + ic)),
            absolute_tolerance,
            "p.u.",
        )
    return ElectricalAudit(tuple(checks))
