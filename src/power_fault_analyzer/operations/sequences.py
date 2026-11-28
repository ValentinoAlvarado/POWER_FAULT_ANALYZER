"""Immutable switching sequences and deterministic simulation engine."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from uuid import UUID, uuid4

from .adapter import network_to_snapshot
from .interlocks import (
    InterlockContext,
    InterlockFinding,
    InterlockRule,
    OperationPermit,
    default_interlock_rules,
)
from .models import (
    EquipmentRecord,
    NetworkSnapshot,
    OperatingScenario,
    OperatingTopologyResult,
    SwitchPosition,
)
from .service import OperatingTopologyService


class SwitchingSequenceStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"


class SwitchingStepStatus(StrEnum):
    EXECUTED = "executed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SwitchingStep:
    equipment_id: UUID
    expected_position: SwitchPosition
    target_position: SwitchPosition
    step_id: UUID = field(default_factory=uuid4)
    instruction: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.expected_position, SwitchPosition) or not isinstance(
            self.target_position, SwitchPosition
        ):
            raise TypeError("expected_position and target_position must be SwitchPosition values.")
        if self.expected_position is self.target_position:
            raise ValueError("A switching step must change the switch position.")
        if not isinstance(self.equipment_id, UUID) or not isinstance(self.step_id, UUID):
            raise TypeError("Switching step identities must be UUID instances.")
        if not isinstance(self.instruction, str):
            raise TypeError("instruction must be a string.")


@dataclass(frozen=True, slots=True)
class SwitchingSequence:
    name: str
    steps: tuple[SwitchingStep, ...]
    initial_scenario: OperatingScenario | None = None
    permit: OperationPermit = field(default_factory=OperationPermit)
    sequence_id: UUID = field(default_factory=uuid4)
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Sequence name must be a non-empty string.")
        if not isinstance(self.description, str):
            raise TypeError("description must be a string.")
        steps = tuple(self.steps)
        if any(not isinstance(item, SwitchingStep) for item in steps):
            raise TypeError("steps must contain SwitchingStep instances.")
        object.__setattr__(self, "steps", steps)
        if not isinstance(self.permit, OperationPermit):
            raise TypeError("permit must be an OperationPermit instance.")
        if (
            self.initial_scenario is not None
            and not isinstance(self.initial_scenario, OperatingScenario)
        ):
            raise TypeError("initial_scenario must be an OperatingScenario or None.")
        if not isinstance(self.sequence_id, UUID):
            raise TypeError("sequence_id must be a UUID instance.")
        ids = [item.step_id for item in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Switching step identities must be unique.")


@dataclass(frozen=True, slots=True)
class SwitchingStepResult:
    step_id: UUID
    index: int
    equipment_id: UUID
    equipment_name: str
    expected_position: SwitchPosition
    target_position: SwitchPosition
    status: SwitchingStepStatus
    findings: tuple[InterlockFinding, ...] = ()
    topology_after: OperatingTopologyResult | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": str(self.step_id),
            "index": self.index,
            "equipment_id": str(self.equipment_id),
            "equipment_name": self.equipment_name,
            "expected_position": self.expected_position.value,
            "target_position": self.target_position.value,
            "status": self.status.value,
            "findings": [
                {
                    "code": item.code,
                    "message": item.message,
                    "blocking": item.blocking,
                    "equipment_id": str(item.equipment_id) if item.equipment_id else None,
                    "bus_ids": [str(value) for value in item.bus_ids],
                }
                for item in self.findings
            ],
            "topology_after": self.topology_after.to_dict() if self.topology_after else None,
        }


@dataclass(frozen=True, slots=True)
class SwitchingSequenceResult:
    sequence_id: UUID
    sequence_name: str
    sequence_description: str
    status: SwitchingSequenceStatus
    initial_topology: OperatingTopologyResult
    final_topology: OperatingTopologyResult
    final_scenario: OperatingScenario
    permit: OperationPermit
    steps: tuple[SwitchingStepResult, ...]
    simulation_only: bool = True

    @property
    def completed_steps(self) -> int:
        return sum(item.status is SwitchingStepStatus.EXECUTED for item in self.steps)

    @property
    def blocked_step(self) -> SwitchingStepResult | None:
        return next(
            (item for item in self.steps if item.status is SwitchingStepStatus.BLOCKED),
            None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence_id": str(self.sequence_id),
            "sequence_name": self.sequence_name,
            "sequence_description": self.sequence_description,
            "status": self.status.value,
            "simulation_only": self.simulation_only,
            "permit": self.permit.to_dict(),
            "completed_steps": self.completed_steps,
            "step_count": len(self.steps),
            "initial_topology": self.initial_topology.to_dict(),
            "final_topology": self.final_topology.to_dict(),
            "final_scenario": self.final_scenario.to_dict(),
            "steps": [item.to_dict() for item in self.steps],
        }


class SwitchingSequenceError(ValueError):
    """Invalid sequence references or inconsistent expected states."""


class SwitchingSequenceService:
    """Simulate switch operations sequentially over immutable scenario overlays.

    This service never writes to the canonical Network or physical switch state.
    A blocked sequence returns its last valid simulated state for review, but
    status=BLOCKED means that no completed plan should be treated as a commit.
    """

    def __init__(
        self,
        topology_service: OperatingTopologyService | None = None,
        interlock_rules: Iterable[InterlockRule] | None = None,
    ) -> None:
        self._topology = topology_service or OperatingTopologyService()
        self._rules = (
            tuple(interlock_rules)
            if interlock_rules is not None
            else default_interlock_rules()
        )

    def simulate(
        self,
        network: object | NetworkSnapshot,
        sequence: SwitchingSequence,
        *,
        source_equipment_ids: tuple[UUID, ...] | None = None,
    ) -> SwitchingSequenceResult:
        snapshot = (
            network
            if isinstance(network, NetworkSnapshot)
            else network_to_snapshot(network, source_equipment_ids=source_equipment_ids)
        )
        equipment_by_id = {item.equipment_id: item for item in snapshot.equipment}
        scenario = sequence.initial_scenario or OperatingScenario(name=f"{sequence.name} / initial")
        initial = self._topology.analyze_snapshot(snapshot, scenario)
        current = initial
        step_results: list[SwitchingStepResult] = []

        for index, step in enumerate(sequence.steps, start=1):
            equipment = equipment_by_id.get(step.equipment_id)
            if equipment is None:
                raise SwitchingSequenceError(
                    f"Step {index} references unknown equipment {step.equipment_id}."
                )
            if not equipment.is_switch:
                raise SwitchingSequenceError(
                    f"Equipment {equipment.name!r} is not a switching device."
                )
            current_equipment = next(
                item for item in current.equipment if item.equipment_id == step.equipment_id
            )
            actual_position = current_equipment.switch_position
            if actual_position is None:
                raise SwitchingSequenceError(f"Switch {equipment.name!r} has no resolved position.")
            if actual_position is not step.expected_position:
                finding = InterlockFinding(
                    code="EXPECTED_SWITCH_STATE_MISMATCH",
                    message=(
                        f"Step {index} expected {equipment.name!r} to be "
                        f"{step.expected_position.value}, but the current scenario reports "
                        f"{actual_position.value}. "
                        "The sequence is blocked to prevent a stale operation."
                    ),
                    equipment_id=equipment.equipment_id,
                )
                step_results.append(self._blocked_step(step, index, equipment, (finding,)))
                break
            if not current_equipment.in_service:
                finding = InterlockFinding(
                    code="SWITCH_OUT_OF_SERVICE",
                    message=(
                        f"Switch {equipment.name!r} is out of service and cannot be "
                        "operated in this simulation."
                    ),
                    equipment_id=equipment.equipment_id,
                )
                step_results.append(
                    self._blocked_step(step, index, equipment, (finding,))
                )
                break

            context = InterlockContext(
                snapshot=snapshot,
                scenario=scenario,
                topology=current,
                equipment=equipment,
                target_position=step.target_position,
                permit=sequence.permit,
            )
            findings = tuple(
                finding
                for rule in self._rules
                for finding in rule.evaluate(context)
            )
            blockers = tuple(item for item in findings if item.blocking)
            if blockers:
                step_results.append(self._blocked_step(step, index, equipment, blockers))
                break

            overrides = dict(scenario.switch_positions)
            overrides[equipment.equipment_id] = step.target_position
            scenario = replace(
                scenario,
                scenario_id=uuid4(),
                name=(
                    f"{sequence.name} / step {index}: "
                    f"{equipment.name} {step.target_position.value}"
                ),
                switch_positions=overrides,
            )
            current = self._topology.analyze_snapshot(snapshot, scenario)
            step_results.append(
                SwitchingStepResult(
                    step_id=step.step_id,
                    index=index,
                    equipment_id=equipment.equipment_id,
                    equipment_name=equipment.name,
                    expected_position=step.expected_position,
                    target_position=step.target_position,
                    status=SwitchingStepStatus.EXECUTED,
                    findings=findings,
                    topology_after=current,
                )
            )

        status = (
            SwitchingSequenceStatus.COMPLETED
            if len(step_results) == len(sequence.steps)
            and all(item.status is SwitchingStepStatus.EXECUTED for item in step_results)
            else SwitchingSequenceStatus.BLOCKED
        )
        return SwitchingSequenceResult(
            sequence_id=sequence.sequence_id,
            sequence_name=sequence.name,
            sequence_description=sequence.description,
            status=status,
            initial_topology=initial,
            final_topology=current,
            final_scenario=scenario,
            permit=sequence.permit,
            steps=tuple(step_results),
        )

    @staticmethod
    def _blocked_step(
        step: SwitchingStep,
        index: int,
        equipment: EquipmentRecord,
        findings: tuple[InterlockFinding, ...],
    ) -> SwitchingStepResult:
        return SwitchingStepResult(
            step_id=step.step_id,
            index=index,
            equipment_id=equipment.equipment_id,
            equipment_name=equipment.name,
            expected_position=step.expected_position,
            target_position=step.target_position,
            status=SwitchingStepStatus.BLOCKED,
            findings=findings,
        )
