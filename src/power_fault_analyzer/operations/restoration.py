"""Conservative restoration proposals over open, in-service interties.

The planner proposes and simulates candidate closures only. It does not issue
commands to equipment, calculate load pickup, verify thermal limits, or certify
that restoration is safe. Candidates are limited to ordinary, non-grounding
switches joining a source-reachable island to a non-energized island.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from .adapter import network_to_snapshot
from .interlocks import OperationPermit
from .models import NetworkSnapshot, OperatingScenario, OperatingTopologyResult, SwitchPosition
from .sequences import (
    SwitchingSequence,
    SwitchingSequenceService,
    SwitchingSequenceStatus,
    SwitchingStep,
)
from .service import OperatingTopologyService


@dataclass(frozen=True, slots=True)
class RestorationPlan:
    plan_id: UUID
    name: str
    sequence: SwitchingSequence
    initial_topology: OperatingTopologyResult
    projected_topology: OperatingTopologyResult
    restored_bus_ids: tuple[UUID, ...]
    remaining_deenergized_bus_ids: tuple[UUID, ...]
    rejected_switch_ids: tuple[UUID, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def complete_for_target(self) -> bool:
        return not self.remaining_deenergized_bus_ids

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": str(self.plan_id),
            "name": self.name,
            "complete_for_target": self.complete_for_target,
            "sequence": {
                "sequence_id": str(self.sequence.sequence_id),
                "name": self.sequence.name,
                "permit": self.sequence.permit.to_dict(),
                "steps": [
                    {
                        "step_id": str(item.step_id),
                        "equipment_id": str(item.equipment_id),
                        "expected_position": item.expected_position.value,
                        "target_position": item.target_position.value,
                        "instruction": item.instruction,
                    }
                    for item in self.sequence.steps
                ],
            },
            "initial_topology": self.initial_topology.to_dict(),
            "projected_topology": self.projected_topology.to_dict(),
            "restored_bus_ids": [str(item) for item in self.restored_bus_ids],
            "remaining_deenergized_bus_ids": [
                str(item) for item in self.remaining_deenergized_bus_ids
            ],
            "rejected_switch_ids": [str(item) for item in self.rejected_switch_ids],
            "notes": list(self.notes),
            "simulation_only": True,
        }


class RestorationPlanner:
    """Generate a greedy, deterministic proposal for restoring de-energized buses."""

    def __init__(
        self,
        topology_service: OperatingTopologyService | None = None,
        sequence_service: SwitchingSequenceService | None = None,
    ) -> None:
        self._topology = topology_service or OperatingTopologyService()
        self._sequences = sequence_service or SwitchingSequenceService(self._topology)

    def propose(
        self,
        network: object | NetworkSnapshot,
        scenario: OperatingScenario,
        *,
        target_bus_ids: tuple[UUID, ...] | None = None,
        source_equipment_ids: tuple[UUID, ...] | None = None,
        permit: OperationPermit | None = None,
    ) -> RestorationPlan:
        snapshot = (
            network
            if isinstance(network, NetworkSnapshot)
            else network_to_snapshot(network, source_equipment_ids=source_equipment_ids)
        )
        initial = self._topology.analyze_snapshot(snapshot, scenario)
        targets = (
            set(target_bus_ids)
            if target_bus_ids is not None
            else set(initial.deenergized_bus_ids)
        )
        known_bus_ids = {item.bus_id for item in snapshot.buses}
        unknown = targets - known_bus_ids
        if unknown:
            raise ValueError(
                "Restoration target contains unknown buses: "
                f"{sorted(map(str, unknown))}"
            )
        current_scenario = scenario
        current = initial
        accepted: list[SwitchingStep] = []
        rejected: set[UUID] = set()
        notes: list[str] = [
            "Proposal only: no physical switching command was issued.",
            (
                "Only open, in-service, non-grounding switches directly joining energized "
                "and de-energized buses are considered."
            ),
            (
                "Load capacity, voltage profile, thermal loading, protection coordination "
                "and field safety are outside this connectivity planner."
            ),
        ]

        while targets.intersection(current.deenergized_bus_ids):
            bus_results = {item.bus_id: item for item in current.buses}
            equipment_results = {item.equipment_id: item for item in current.equipment}
            candidates = []
            for record in snapshot.equipment:
                if not record.is_switch or record.is_grounding_switch:
                    continue
                result = equipment_results[record.equipment_id]
                if result.switch_position is not SwitchPosition.OPEN or not result.in_service:
                    continue
                connected = tuple(dict.fromkeys(result.connected_bus_ids))
                energized = [item for item in connected if bus_results[item].source_reachable]
                deenergized = [item for item in connected if not bus_results[item].source_reachable]
                if energized and deenergized and targets.intersection(deenergized):
                    candidates.append(record)

            candidates.sort(key=lambda item: (item.name.casefold(), str(item.equipment_id)))
            accepted_candidate = None
            for record in candidates:
                step = SwitchingStep(
                    equipment_id=record.equipment_id,
                    expected_position=SwitchPosition.OPEN,
                    target_position=SwitchPosition.CLOSED,
                    instruction=f"Close {record.name} to evaluate restoration connectivity.",
                )
                trial_sequence = SwitchingSequence(
                    name=f"Restoration candidate {record.name}",
                    steps=(step,),
                    initial_scenario=current_scenario,
                    permit=permit or OperationPermit(),
                )
                trial = self._sequences.simulate(snapshot, trial_sequence)
                if trial.status is not SwitchingSequenceStatus.COMPLETED:
                    rejected.add(record.equipment_id)
                    continue
                if len(trial.final_topology.energized_bus_ids) <= len(current.energized_bus_ids):
                    rejected.add(record.equipment_id)
                    continue
                accepted_candidate = (step, trial.final_scenario, trial.final_topology)
                break

            if accepted_candidate is None:
                break
            step, current_scenario, current = accepted_candidate
            accepted.append(step)

        # A plan with no feasible closure is still useful: it reports the
        # unresolved target buses and the rejected candidate switches.
        sequence = SwitchingSequence(
            name=f"{scenario.name} / proposed restoration",
            steps=tuple(accepted),
            initial_scenario=scenario,
            permit=permit or OperationPermit(),
        )
        evaluated = self._sequences.simulate(snapshot, sequence)
        if evaluated.status is SwitchingSequenceStatus.COMPLETED:
            current = evaluated.final_topology
        else:
            # Incremental trials and full replay must be identical. Surface
            # divergence instead of returning a potentially misleading plan.
            raise RuntimeError("Restoration sequence replay diverged from incremental evaluation.")

        if not accepted:
            notes.append(
                "No feasible switch closure was found for the requested restoration targets."
            )

        restored = tuple(sorted(targets.intersection(current.energized_bus_ids), key=str))
        remaining = tuple(sorted(targets.intersection(current.deenergized_bus_ids), key=str))
        return RestorationPlan(
            plan_id=uuid4(),
            name=f"Restoration proposal for {scenario.name}",
            sequence=sequence,
            initial_topology=initial,
            projected_topology=current,
            restored_bus_ids=restored,
            remaining_deenergized_bus_ids=remaining,
            rejected_switch_ids=tuple(sorted(rejected, key=str)),
            notes=tuple(notes),
        )
