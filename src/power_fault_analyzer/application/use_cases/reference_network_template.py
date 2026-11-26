"""Build an editable physical network from an existing ND-016 reference dataset case."""

from __future__ import annotations

from dataclasses import dataclass

from power_fault_analyzer.application.use_cases.network_editing import (
    AddBusToNetwork,
    AddTheveninEquivalentSourceToNetwork,
)
from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.projects.models import TheveninStudySettings
from power_fault_analyzer.validation.reference_cases import load_reference_dataset


@dataclass(frozen=True, slots=True)
class ReferenceNetworkTemplate:
    case_id: str
    dataset_id: str
    workspace: NetworkWorkspace
    study_settings: TheveninStudySettings
    fault_bus_id: object


class BuildReferenceNetworkTemplate:
    """Materialize reference data as real domain Bus and EquivalentSource entities."""

    def execute(self, case_id: str = "REF-3PH-001") -> ReferenceNetworkTemplate:
        dataset_id, _basis, cases = load_reference_dataset()
        try:
            case = next(item for item in cases if item.case_id == case_id)
        except StopIteration as exc:
            raise ValueError(f"Unknown analytical reference case '{case_id}'.") from exc

        data = case.network
        settings = TheveninStudySettings(
            bus_name="101",
            study_name=case.case_id,
            base_power_mva=float(data["base_power_mva"]),
            base_voltage_ll_kv=float(data["base_voltage_ll_kv"]),
            prefault_positive_voltage_pu=complex(*data["prefault_positive_voltage_pu"]),
            positive_sequence_impedance_pu=complex(*data["sequence_impedances_pu"]["positive"]),
            negative_sequence_impedance_pu=complex(*data["sequence_impedances_pu"]["negative"]),
            zero_sequence_impedance_pu=complex(
                data["sequence_impedances_pu"]["zero"][0], data["sequence_impedances_pu"]["zero"][1]
            ),
            fault_type=case.fault_type,
            fault_impedance_pu=case.fault_impedance_pu,
        )
        network = Network(f"{case.case_id} physical network")
        bus = AddBusToNetwork().execute(network, "101", settings.base_voltage_ll_kv)
        AddTheveninEquivalentSourceToNetwork().execute(
            network,
            name=f"{case.case_id} Thevenin source",
            bus_id=bus.id,
            base_power_mva=settings.base_power_mva,
            positive_sequence_pu=settings.positive_sequence_impedance_pu,
            negative_sequence_pu=settings.negative_sequence_impedance_pu,
            zero_sequence_pu=settings.zero_sequence_impedance_pu,
            prefault_voltage_pu=settings.prefault_positive_voltage_pu,
        )
        workspace = NetworkWorkspace(
            network=network,
            diagram_positions={bus.id: (100.0, 120.0)},
        )
        return ReferenceNetworkTemplate(
            case_id=case.case_id,
            dataset_id=dataset_id,
            workspace=workspace,
            study_settings=settings,
            fault_bus_id=bus.id,
        )
