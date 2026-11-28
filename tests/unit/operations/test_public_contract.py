from __future__ import annotations

from uuid import uuid4

import pytest

from power_fault_analyzer.operations import OperatingScenario, SwitchPosition


def test_operating_scenario_serialization_rejects_non_boolean_override_values():
    with pytest.raises(TypeError, match="JSON booleans"):
        OperatingScenario.from_dict(
            {
                "name": "Invalid",
                "scenario_id": str(uuid4()),
                "equipment_in_service": {str(uuid4()): "false"},
            }
        )


def test_operating_scenario_rejects_mutable_invalid_switch_position_values():
    with pytest.raises(TypeError, match="SwitchPosition"):
        OperatingScenario("Invalid", switch_positions={uuid4(): "open"})  # type: ignore[dict-item]


def test_operating_scenario_json_contract_has_stable_enum_values():
    device_id = uuid4()
    scenario = OperatingScenario("Open breaker", switch_positions={device_id: SwitchPosition.OPEN})
    payload = scenario.to_dict()
    assert payload["switch_positions"] == {str(device_id): "open"}
