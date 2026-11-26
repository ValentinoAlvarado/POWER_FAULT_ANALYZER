"""Correction-factor contracts and provenance validation for IEC 60909."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from power_fault_analyzer.standards.iec60909.models import (
    IEC60909CorrectionFactor,
)
from power_fault_analyzer.standards.iec60909.scenarios import IEC60909StudyScenario


class IEC60909CorrectionFactorPolicy(Protocol):
    """Port implemented by a clause-mapped correction-factor policy."""

    @property
    def factor_name(self) -> str:
        """Stable factor identifier, for example a named equipment correction."""
        ...

    def calculate(
        self,
        scenario: IEC60909StudyScenario,
        *,
        equipment_id: UUID | None = None,
        source_id: UUID | None = None,
    ) -> IEC60909CorrectionFactor:
        """Calculate and return a fully traceable factor for the supplied scenario."""
        ...


@dataclass(frozen=True, slots=True)
class IEC60909CorrectionFactorSet:
    """Immutable factor collection associated with exactly one study scenario."""

    scenario_id: UUID
    factors: tuple[IEC60909CorrectionFactor, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, UUID):
            raise TypeError("scenario_id must be a UUID value.")
        if not isinstance(self.factors, tuple) or any(
            not isinstance(item, IEC60909CorrectionFactor) for item in self.factors
        ):
            raise TypeError("factors must be a tuple of IEC60909CorrectionFactor values.")
        factor_ids = [item.factor_id for item in self.factors]
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("Correction factor IDs must be unique within a factor set.")
        factor_keys = [(item.name, item.equipment_id, item.source_id) for item in self.factors]
        if len(factor_keys) != len(set(factor_keys)):
            raise ValueError("A factor set cannot repeat the same factor scope.")
        if any(
            item.scenario_id is not None and item.scenario_id != self.scenario_id
            for item in self.factors
        ):
            raise ValueError("Every correction factor must belong to the factor-set scenario.")

    def for_source(self, source_id: UUID) -> tuple[IEC60909CorrectionFactor, ...]:
        """Return factors explicitly scoped to one source."""
        if not isinstance(source_id, UUID):
            raise TypeError("source_id must be a UUID value.")
        return tuple(item for item in self.factors if item.source_id == source_id)

    def for_equipment(self, equipment_id: UUID) -> tuple[IEC60909CorrectionFactor, ...]:
        """Return factors explicitly scoped to one equipment item."""
        if not isinstance(equipment_id, UUID):
            raise TypeError("equipment_id must be a UUID value.")
        return tuple(item for item in self.factors if item.equipment_id == equipment_id)


def validate_factor_references(
    factors: Iterable[IEC60909CorrectionFactor],
    *,
    scenario: IEC60909StudyScenario,
) -> None:
    """Reject factor records that reference sources/equipment outside the scenario."""
    if not isinstance(scenario, IEC60909StudyScenario):
        raise TypeError("scenario must be an IEC60909StudyScenario value.")
    source_ids = {item.source_id for item in scenario.sources if item.in_service}
    equipment_ids = set(scenario.active_equipment_ids)
    for factor in factors:
        if not isinstance(factor, IEC60909CorrectionFactor):
            raise TypeError("Every factor must be an IEC60909CorrectionFactor value.")
        if factor.scenario_id is not None and factor.scenario_id != scenario.scenario_id:
            raise ValueError("Correction factor belongs to a different study scenario.")
        if factor.source_id is not None and factor.source_id not in source_ids:
            raise ValueError("Correction factor references a source outside the scenario.")
        if factor.equipment_id is not None and factor.equipment_id not in equipment_ids:
            raise ValueError("Correction factor references equipment outside the scenario.")
