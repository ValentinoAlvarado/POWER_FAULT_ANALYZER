"""Finite-difference sensitivity and derivative-refinement checks."""

from __future__ import annotations

import math
from collections.abc import Callable
from itertools import pairwise

from power_fault_analyzer.validation.models import SensitivityAssessment, SensitivityPoint


def assess_scalar_parameter_sensitivity(
    evaluator: Callable[[float], complex],
    *,
    parameter_name: str,
    scales: tuple[float, ...] = (0.9, 0.95, 1.0, 1.05, 1.1),
    derivative_step: float = 1e-3,
    convergence_tolerance: float = 5e-4,
) -> SensitivityAssessment:
    """Sample a response over a positive parameter scale and check derivative refinement.

    This is a deterministic finite-difference diagnostic, not a claim about all network
    topologies. The evaluator must rebuild/re-solve the physical case for each scale.
    """
    if not callable(evaluator):
        raise TypeError("evaluator must be callable.")
    if not parameter_name or not isinstance(parameter_name, str):
        raise ValueError("parameter_name must be a non-empty string.")
    if (
        len(scales) < 3
        or tuple(sorted(scales)) != scales
        or len(set(scales)) != len(scales)
        or 1.0 not in scales
    ):
        raise ValueError(
            "scales must be unique and sorted, contain at least three values and include 1.0."
        )
    if any(not math.isfinite(value) or value <= 0.0 for value in scales):
        raise ValueError("all parameter scales must be finite and positive.")
    if derivative_step <= 0.0 or not math.isfinite(derivative_step):
        raise ValueError("derivative_step must be finite and positive.")
    if convergence_tolerance < 0.0 or not math.isfinite(convergence_tolerance):
        raise ValueError("convergence_tolerance must be finite and non-negative.")
    responses = {scale: complex(evaluator(scale)) for scale in scales}
    if any(not math.isfinite(v.real) or not math.isfinite(v.imag) for v in responses.values()):
        raise ValueError("evaluator returned a non-finite response.")
    baseline = responses[1.0]
    points = tuple(
        SensitivityPoint(
            parameter_scale=scale,
            response=responses[scale],
            response_magnitude=abs(responses[scale]),
            relative_change=(abs(responses[scale]) - abs(baseline)) / abs(baseline)
            if abs(baseline) > 1e-15
            else 0.0,
        )
        for scale in scales
    )
    coarse = (
        complex(evaluator(1.0 + derivative_step)) - complex(evaluator(1.0 - derivative_step))
    ) / (2.0 * derivative_step)
    half = derivative_step / 2.0
    fine = (complex(evaluator(1.0 + half)) - complex(evaluator(1.0 - half))) / (2.0 * half)
    denominator = max(abs(fine), 1e-15)
    difference = abs(coarse - fine) / denominator
    magnitude_values = [item.response_magnitude for item in points]
    monotonic = all(
        right <= left + max(1e-12, left * 1e-10) for left, right in pairwise(magnitude_values)
    )
    return SensitivityAssessment(
        parameter_name=parameter_name,
        points=points,
        derivative_coarse=coarse,
        derivative_fine=fine,
        derivative_relative_difference=float(difference),
        monotonic_magnitude=monotonic,
        converged=difference <= convergence_tolerance,
    )
