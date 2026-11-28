"""Acceptance assessment for restoration plans using externally computed AC load flow.

This module does not solve power flow. It validates the completeness, identity and
reported operating limits of externally produced AC load-flow cases.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum, StrEnum
from math import isfinite
from types import MappingProxyType
from uuid import UUID

from .adapter import network_to_snapshot
from .models import OperatingScenario
from .restoration import RestorationPlan
from .sequences import SwitchingSequenceService, SwitchingSequenceStatus


class RestorationAssessmentStatus(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class ACLoadFlowCaseResult:
    """External AC load-flow result for one base or contingency case.

    Loading values are percentages of the continuous/declared rating supplied by
    the external solver. The provenance and engineering validity of that solver
    remain the responsibility of the caller.
    """

    case_id: str
    network_id: UUID
    scenario_fingerprint: str
    converged: bool
    bus_voltages_pu: Mapping[UUID, float] = field(default_factory=dict)
    branch_loading_pct: Mapping[UUID, float] = field(default_factory=dict)
    generator_output_mw: Mapping[UUID, float] = field(default_factory=dict)
    generator_limits_mw: Mapping[UUID, tuple[float, float]] = field(default_factory=dict)
    solved_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must be a non-empty string.")
        if not isinstance(self.network_id, UUID):
            raise TypeError("network_id must be a UUID.")
        if not isinstance(self.scenario_fingerprint, str) or len(self.scenario_fingerprint) != 64:
            raise ValueError("scenario_fingerprint must be a 64-character SHA-256 hex digest.")
        try:
            int(self.scenario_fingerprint, 16)
        except ValueError as exc:
            raise ValueError("scenario_fingerprint must be hexadecimal.") from exc
        if not isinstance(self.converged, bool):
            raise TypeError("converged must be bool.")
        if not isinstance(self.solved_at, datetime) or self.solved_at.tzinfo is None:
            raise ValueError("solved_at must be a timezone-aware datetime.")
        for field_name in (
            "bus_voltages_pu", "branch_loading_pct", "generator_output_mw", "generator_limits_mw"
        ):
            values = dict(getattr(self, field_name))
            if any(not isinstance(key, UUID) for key in values):
                raise TypeError(f"{field_name} keys must be UUID values.")
            object.__setattr__(self, field_name, MappingProxyType(values))
        for bus_id, value in self.bus_voltages_pu.items():
            _finite_nonnegative(value, f"bus voltage for {bus_id}")
        for branch_id, value in self.branch_loading_pct.items():
            _finite_nonnegative(value, f"branch loading for {branch_id}")
        for generator_id, value in self.generator_output_mw.items():
            if not isinstance(value, (int, float)) or not isfinite(float(value)):
                raise ValueError(f"Generator output for {generator_id} must be finite.")
        normalized_generator_limits: dict[UUID, tuple[float, float]] = {}
        for generator_id, limits in self.generator_limits_mw.items():
            if not isinstance(limits, (tuple, list)) or len(limits) != 2:
                raise TypeError("Generator limits must be (minimum_mw, maximum_mw) pairs.")
            minimum, maximum = map(float, limits)
            if not isfinite(minimum) or not isfinite(maximum) or minimum > maximum:
                raise ValueError("Generator limits must be finite and minimum <= maximum.")
            normalized_generator_limits[generator_id] = (minimum, maximum)
        object.__setattr__(
            self, "generator_limits_mw", MappingProxyType(normalized_generator_limits)
        )


@dataclass(frozen=True, slots=True)
class RestorationAssessmentFinding:
    code: str
    message: str
    case_id: str
    entity_id: UUID | None = None
    blocking: bool = False


@dataclass(frozen=True, slots=True)
class RestorationAssessment:
    plan_id: UUID
    network_id: UUID
    scenario_fingerprint: str
    status: RestorationAssessmentStatus
    cases_evaluated: tuple[str, ...]
    findings: tuple[RestorationAssessmentFinding, ...]
    limits: tuple[float, float, float]
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def feasible(self) -> bool:
        return self.status is RestorationAssessmentStatus.FEASIBLE

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": str(self.plan_id),
            "network_id": str(self.network_id),
            "scenario_fingerprint": self.scenario_fingerprint,
            "status": self.status.value,
            "cases_evaluated": list(self.cases_evaluated),
            "limits": {
                "voltage_min_pu": self.limits[0],
                "voltage_max_pu": self.limits[1],
                "branch_loading_max_pct": self.limits[2],
            },
            "findings": [
                {
                    "code": item.code,
                    "message": item.message,
                    "case_id": item.case_id,
                    "entity_id": str(item.entity_id) if item.entity_id else None,
                    "blocking": item.blocking,
                }
                for item in self.findings
            ],
            "evaluated_at": self.evaluated_at.isoformat(),
        }


def scenario_fingerprint(network, scenario: OperatingScenario) -> str:
    """Return a stable digest tying a load-flow result to a physical network + overlay."""
    snapshot = network_to_snapshot(network)
    payload = {
        "network_id": str(snapshot.network_id),
        "network_name": network.name,
        # Include complete public electrical state (equipment sequence parameters,
        # ratings, terminals, bus nominal voltage and source data), not only the
        # topology projection exposed by NetworkSnapshot.
        "buses": sorted((_canonical_object(item) for item in network.buses), key=_stable_json),
        "equipment": sorted(
            (_canonical_object(item) for item in network.equipment), key=_stable_json
        ),
        "connections": sorted(
            (_canonical_object(item) for item in network.connections), key=_stable_json
        ),
        # Identity and labels are metadata, not electrical state. Excluding them
        # keeps the fingerprint stable when a deterministic sequence replay creates
        # a fresh scenario UUID for the same effective overlay.
        "scenario_state": {
            "switch_positions": {
                str(key): value.value for key, value in sorted(
                    scenario.switch_positions.items(), key=lambda item: str(item[0])
                )
            },
            "equipment_in_service": {
                str(key): value for key, value in sorted(
                    scenario.equipment_in_service.items(), key=lambda item: str(item[0])
                )
            },
            "source_enabled": {
                str(key): value for key, value in sorted(
                    scenario.source_enabled.items(), key=lambda item: str(item[0])
                )
            },
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class RestorationAssessmentService:
    """Assess a simulated restoration against supplied AC base and N-1 cases."""

    def assess(
        self,
        network,
        plan: RestorationPlan,
        base_case: ACLoadFlowCaseResult,
        *,
        contingency_cases: Sequence[ACLoadFlowCaseResult] = (),
        required_contingency_case_ids: Sequence[str] = (),
        required_branch_ids: Sequence[UUID] = (),
        required_generator_ids: Sequence[UUID] = (),
        voltage_min_pu: float = 0.95,
        voltage_max_pu: float = 1.05,
        branch_loading_max_pct: float = 100.0,
    ) -> RestorationAssessment:
        if not isinstance(plan, RestorationPlan):
            raise TypeError("plan must be a RestorationPlan.")
        if not isinstance(base_case, ACLoadFlowCaseResult):
            raise TypeError("base_case must be an ACLoadFlowCaseResult.")
        cases = (base_case, *tuple(contingency_cases))
        if any(not isinstance(item, ACLoadFlowCaseResult) for item in cases):
            raise TypeError("Every contingency case must be an ACLoadFlowCaseResult.")
        limits = tuple(map(float, (voltage_min_pu, voltage_max_pu, branch_loading_max_pct)))
        if not all(isfinite(value) for value in limits):
            raise ValueError("Assessment limits must be finite.")
        if limits[0] <= 0 or limits[0] > limits[1] or limits[2] <= 0:
            raise ValueError("Voltage and loading limits are invalid.")

        if plan.projected_topology.network_id != network.id:
            raise ValueError("Restoration plan belongs to a different physical network.")
        if plan.sequence.initial_scenario is None:
            raise ValueError("Restoration plan has no initial operating scenario.")
        replay = SwitchingSequenceService().simulate(network, plan.sequence)
        if replay.status is not SwitchingSequenceStatus.COMPLETED:
            raise ValueError("Restoration plan does not replay to a completed sequence.")
        replay_topology = replay.final_topology.to_dict()
        planned_topology = plan.projected_topology.to_dict()
        # Sequence replay can assign a fresh UUID to its final immutable scenario.
        # Compare all topology content while retaining the plan's persisted scenario identity.
        replay_topology["scenario"]["id"] = planned_topology["scenario"]["id"]
        if replay_topology != planned_topology:
            raise ValueError(
                "Restoration plan topology differs from deterministic sequence replay."
            )
        canonical_final_scenario = replace(
            replay.final_scenario, scenario_id=plan.projected_topology.scenario_id
        )
        fingerprint = scenario_fingerprint(network, canonical_final_scenario)
        required_cases = tuple(required_contingency_case_ids)
        if len(required_cases) != len(set(required_cases)):
            raise ValueError("required_contingency_case_ids must be unique.")
        if any(not isinstance(item, str) or not item.strip() for item in required_cases):
            raise ValueError("Contingency case identifiers must be non-empty strings.")
        if len({item.case_id for item in cases}) != len(cases):
            raise ValueError("Load-flow case identifiers must be unique.")
        if base_case.case_id != "base":
            raise ValueError("base_case.case_id must be exactly 'base'.")

        required_buses = tuple(sorted(plan.projected_topology.energized_bus_ids, key=str))
        branch_ids = tuple(required_branch_ids)
        generator_ids = tuple(required_generator_ids)
        if any(not isinstance(item, UUID) for item in (*branch_ids, *generator_ids)):
            raise TypeError("Required branch and generator identifiers must be UUID values.")
        if len(branch_ids) != len(set(branch_ids)) or len(generator_ids) != len(set(generator_ids)):
            raise ValueError("Required branch and generator identifiers must be unique.")
        snapshot = network_to_snapshot(network)
        known_equipment_ids = {item.equipment_id for item in snapshot.equipment}
        unknown_equipment_ids = (set(branch_ids) | set(generator_ids)) - known_equipment_ids
        if unknown_equipment_ids:
            raise ValueError(
                f"Required load-flow equipment IDs are not in the network: "
                f"{sorted(map(str, unknown_equipment_ids))}."
            )

        findings: list[RestorationAssessmentFinding] = []
        infeasible = False
        indeterminate = False
        case_by_id = {item.case_id: item for item in cases}
        missing_required_cases = set(required_cases) - set(case_by_id)
        for missing in sorted(missing_required_cases):
            findings.append(RestorationAssessmentFinding(
                "N1_CASE_MISSING", f"Required contingency case {missing!r} was not supplied.",
                missing, blocking=True,
            ))
            indeterminate = True

        for case in cases:
            if case.network_id != network.id:
                findings.append(RestorationAssessmentFinding(
                    "NETWORK_ID_MISMATCH", "Load-flow result belongs to another network.",
                    case.case_id, blocking=True,
                ))
                indeterminate = True
                continue
            if case.scenario_fingerprint != fingerprint:
                findings.append(RestorationAssessmentFinding(
                    "SCENARIO_FINGERPRINT_MISMATCH",
                    "Load-flow result was produced for a different network/scenario state.",
                    case.case_id, blocking=True,
                ))
                indeterminate = True
                continue
            if not case.converged:
                findings.append(RestorationAssessmentFinding(
                    "LOAD_FLOW_NOT_CONVERGED", "External AC load flow did not converge.",
                    case.case_id, blocking=True,
                ))
                indeterminate = True
                continue

            for bus_id in required_buses:
                value = case.bus_voltages_pu.get(bus_id)
                if value is None:
                    findings.append(RestorationAssessmentFinding(
                        "BUS_VOLTAGE_MISSING", "No voltage result exists for an energized bus.",
                        case.case_id, bus_id, True,
                    ))
                    indeterminate = True
                elif value < limits[0] or value > limits[1]:
                    findings.append(RestorationAssessmentFinding(
                        "BUS_VOLTAGE_LIMIT_VIOLATION",
                        f"Bus voltage {value:.6g} p.u. is outside "
                        f"[{limits[0]:g}, {limits[1]:g}] p.u.",
                        case.case_id, bus_id, True,
                    ))
                    infeasible = True

            for branch_id in branch_ids:
                value = case.branch_loading_pct.get(branch_id)
                if value is None:
                    findings.append(RestorationAssessmentFinding(
                        "BRANCH_LOADING_MISSING", "No loading result exists for a required branch.",
                        case.case_id, branch_id, True,
                    ))
                    indeterminate = True
                elif value > limits[2]:
                    findings.append(RestorationAssessmentFinding(
                        "BRANCH_LOADING_LIMIT_VIOLATION",
                        f"Branch loading {value:.6g}% exceeds {limits[2]:g}%.",
                        case.case_id, branch_id, True,
                    ))
                    infeasible = True

            for generator_id in generator_ids:
                output = case.generator_output_mw.get(generator_id)
                generator_limits = case.generator_limits_mw.get(generator_id)
                if output is None or generator_limits is None:
                    findings.append(RestorationAssessmentFinding(
                        "GENERATOR_DATA_MISSING",
                        "Generator output and minimum/maximum limits are both required.",
                        case.case_id, generator_id, True,
                    ))
                    indeterminate = True
                elif output < generator_limits[0] or output > generator_limits[1]:
                    findings.append(RestorationAssessmentFinding(
                        "GENERATOR_LIMIT_VIOLATION",
                        f"Generator output {output:.6g} MW is outside "
                        f"[{generator_limits[0]:g}, {generator_limits[1]:g}] MW.",
                        case.case_id, generator_id, True,
                    ))
                    infeasible = True

        status = (
            RestorationAssessmentStatus.INFEASIBLE if infeasible
            else RestorationAssessmentStatus.INDETERMINATE if indeterminate
            else RestorationAssessmentStatus.FEASIBLE
        )
        return RestorationAssessment(
            plan_id=plan.plan_id,
            network_id=network.id,
            scenario_fingerprint=fingerprint,
            status=status,
            cases_evaluated=tuple(item.case_id for item in cases),
            findings=tuple(findings),
            limits=limits,
        )


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_object(value: object, active: set[int] | None = None) -> object:
    """Serialize slot-backed PFA domain state deterministically for fingerprints."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("Cannot fingerprint non-finite electrical model data.")
        return value
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_object(item, active)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_object(item, active) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonical_object(item, active) for item in value]
        return sorted(items, key=_stable_json)

    stack = set() if active is None else active
    object_id = id(value)
    if object_id in stack:
        return {"cycle": f"{type(value).__module__}.{type(value).__qualname__}"}
    stack.add(object_id)
    try:
        slots: dict[str, object] = {}
        for cls in reversed(type(value).__mro__):
            declared = getattr(cls, "__slots__", ())
            if isinstance(declared, str):
                declared = (declared,)
            for name in declared:
                if name in {"__dict__", "__weakref__"} or name.startswith("_cache"):
                    continue
                if hasattr(value, name):
                    slots[name.lstrip("_")] = _canonical_object(getattr(value, name), stack)
        if hasattr(value, "__dict__"):
            for name, item in sorted(vars(value).items()):
                if not name.startswith("_"):
                    slots[name] = _canonical_object(item, stack)
        if slots:
            return {
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "state": slots,
            }
        return {"type": f"{type(value).__module__}.{type(value).__qualname__}", "value": str(value)}
    finally:
        stack.remove(object_id)


def _finite_nonnegative(value: object, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or float(value) < 0
    ):
        raise ValueError(f"{label} must be finite and non-negative.")
