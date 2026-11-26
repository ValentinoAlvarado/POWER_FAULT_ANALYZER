"""Explicit measured or vendor-derived zero-sequence three-port transformer model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)


def _determinant_3x3(matrix: tuple[tuple[complex, ...], ...]) -> complex:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


@dataclass(frozen=True, slots=True)
class ThreeWindingZeroSequencePortModel:
    """Reciprocal three-port zero-sequence impedance matrix in per unit.

    Port order is exactly (HV, MV, LV). The per-unit bases use one common
    three-phase MVA base and the rated line-to-line voltage of each winding.
    The matrix must come from a manufacturer, test, or validated electromagnetic
    model and must include the actual neutral, delta-circulating and core-return
    behavior. It is never inferred from pairwise leakage impedances alone.
    """

    base: ElectricalImpedanceBase
    impedance_matrix_pu: tuple[tuple[complex, complex, complex], ...]
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.base, ElectricalImpedanceBase):
            raise TypeError("base must be an ElectricalImpedanceBase value.")
        if not isinstance(self.impedance_matrix_pu, tuple) or len(self.impedance_matrix_pu) != 3:
            raise TypeError("impedance_matrix_pu must be a 3x3 immutable tuple.")
        rows: list[tuple[complex, complex, complex]] = []
        for row in self.impedance_matrix_pu:
            if not isinstance(row, tuple) or len(row) != 3:
                raise TypeError("Every impedance-matrix row must contain three values.")
            converted: list[complex] = []
            for value in row:
                if isinstance(value, bool) or not isinstance(value, (int, float, complex, Real)):
                    raise TypeError("Impedance-matrix entries must be numeric, not bool.")
                item = complex(value)
                if not math.isfinite(item.real) or not math.isfinite(item.imag):
                    raise ValueError("Impedance-matrix entries must be finite.")
                converted.append(item)
            rows.append(tuple(converted))
        matrix = tuple(rows)
        scale = max(abs(value) for row in matrix for value in row)
        if scale == 0.0:
            raise ValueError("Zero-sequence port impedance matrix cannot be zero.")
        tolerance = 1e-10 * scale
        for i in range(3):
            for j in range(3):
                if abs(matrix[i][j] - matrix[j][i]) > tolerance:
                    raise ValueError(
                        "Zero-sequence port impedance matrix must be reciprocal/symmetric."
                    )
        real_matrix = tuple(tuple(matrix[i][j].real for j in range(3)) for i in range(3))
        resistance_scale = max(abs(value) for row in real_matrix for value in row)
        first_order_tolerance = 1e-10 * max(resistance_scale, 1e-30)
        second_order_tolerance = 1e-10 * max(resistance_scale**2, 1e-30)
        third_order_tolerance = 1e-10 * max(resistance_scale**3, 1e-30)
        diagonal = (real_matrix[0][0], real_matrix[1][1], real_matrix[2][2])
        principal_2 = (
            real_matrix[0][0] * real_matrix[1][1] - real_matrix[0][1] ** 2,
            real_matrix[0][0] * real_matrix[2][2] - real_matrix[0][2] ** 2,
            real_matrix[1][1] * real_matrix[2][2] - real_matrix[1][2] ** 2,
        )
        det_real = (
            real_matrix[0][0] * (real_matrix[1][1] * real_matrix[2][2] - real_matrix[1][2] ** 2)
            - real_matrix[0][1]
            * (real_matrix[0][1] * real_matrix[2][2] - real_matrix[1][2] * real_matrix[0][2])
            + real_matrix[0][2]
            * (real_matrix[0][1] * real_matrix[1][2] - real_matrix[1][1] * real_matrix[0][2])
        )
        if any(value < -first_order_tolerance for value in diagonal):
            raise ValueError("Real part of the port impedance matrix must be passive (PSD).")
        if any(value < -second_order_tolerance for value in principal_2):
            raise ValueError("Real part of the port impedance matrix must be passive (PSD).")
        if det_real < -third_order_tolerance:
            raise ValueError(
                "Real part of the port impedance matrix must be positive semidefinite."
            )
        if abs(_determinant_3x3(matrix)) <= 1e-14 * scale**3:
            raise ValueError("Zero-sequence port impedance matrix must be nonsingular.")
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError("reference must identify the manufacturer, test, or validated model.")
        object.__setattr__(self, "impedance_matrix_pu", matrix)
        object.__setattr__(self, "reference", self.reference.strip())
