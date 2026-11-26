from __future__ import annotations

import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.projects.models import Project, TheveninStudySettings


def test_default_thevenin_settings_match_ref_3ph_001b() -> None:
    settings = TheveninStudySettings()

    assert settings.bus_name == "101"
    assert settings.base_power_mva == 100.0
    assert settings.base_voltage_ll_kv == 13.8
    assert settings.prefault_positive_voltage_pu == complex(1.02, 0.025)
    assert settings.positive_sequence_impedance_pu == complex(0.08, 0.24)
    assert settings.negative_sequence_impedance_pu == complex(0.11, 0.31)
    assert settings.zero_sequence_impedance_pu == complex(0.18, 0.52)
    assert settings.fault_type is FaultType.THREE_PHASE
    assert settings.fault_impedance_pu == complex(0.025, 0.07)


def test_settings_reject_negative_fault_resistance() -> None:
    with pytest.raises(ValueError, match="Fault resistance"):
        TheveninStudySettings(fault_impedance_pu=-0.01 + 0.1j)


def test_settings_reject_zero_sequence_impedance() -> None:
    with pytest.raises(ValueError, match="cannot be zero"):
        TheveninStudySettings(zero_sequence_impedance_pu=0j)


def test_project_updates_are_immutable() -> None:
    project = Project.create("Study A")
    updated = project.with_settings(TheveninStudySettings(base_power_mva=50.0))

    assert project.study_settings.base_power_mva == 100.0
    assert updated.study_settings.base_power_mva == 50.0
    assert updated.project_id == project.project_id
