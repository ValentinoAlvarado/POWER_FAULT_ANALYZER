"""Stable generated-label identity, independent from status-decorated display text."""
from uuid import NAMESPACE_URL, uuid5

from examples.canonical_model_scenarios import build_single_bus_substation
from power_fault_analyzer.diagram.model_projection import project_network_to_diagram


def test_equipment_label_identity_does_not_depend_on_visible_text_or_status_marker():
    workspace = build_single_bus_substation()
    equipment = workspace.network.equipment[0]
    document = project_network_to_diagram(workspace)

    expected_id = uuid5(
        NAMESPACE_URL, f"urn:pfa:diagram-label:{equipment.id}:equipment-name"
    )
    labels = [item for item in document.labels if item.label_id == expected_id]

    assert len(labels) == 1
    label = labels[0]
    assert label.owner_id == equipment.id
    assert label.text
    # Canonical engineering name and presentation label are distinct concepts.
    assert workspace.network.get_equipment(equipment.id).name == equipment.name
    assert label.text in {equipment.name, f"{equipment.name}†", f"{equipment.name}‡"}
