from uuid import uuid4

import pytest

from power_fault_analyzer.domain.value_objects import (
    Connection,
    DiagnosticSeverity,
    DomainDiagnostic,
    Voltage,
    VoltageReference,
)


def test_voltage_from_kv_uses_line_to_line_by_default() -> None:
    voltage = Voltage.from_kv(13.8)
    assert voltage.value_v == pytest.approx(13_800.0)
    assert voltage.value_kv == pytest.approx(13.8)
    assert voltage.reference is VoltageReference.LINE_TO_LINE


def test_voltage_can_explicitly_represent_phase_to_neutral() -> None:
    voltage = Voltage.from_kv(7.967, VoltageReference.PHASE_TO_NEUTRAL)
    assert voltage.reference is VoltageReference.PHASE_TO_NEUTRAL


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_voltage_rejects_non_positive_or_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError):
        Voltage(value)


def test_voltage_rejects_boolean() -> None:
    with pytest.raises(TypeError):
        Voltage(True)  # type: ignore[arg-type]


def test_connection_is_immutable_and_requires_uuids() -> None:
    terminal_id, bus_id = uuid4(), uuid4()
    connection = Connection(terminal_id=terminal_id, bus_id=bus_id)
    assert connection.terminal_id == terminal_id
    assert connection.bus_id == bus_id
    with pytest.raises((AttributeError, TypeError)):
        connection.bus_id = uuid4()  # type: ignore[misc]


def test_connection_rejects_non_uuid_values() -> None:
    with pytest.raises(TypeError):
        Connection(terminal_id="not-a-uuid", bus_id=uuid4())  # type: ignore[arg-type]


def test_domain_diagnostic_requires_code_and_message() -> None:
    diagnostic = DomainDiagnostic(
        code="NET-001",
        message="A test diagnostic.",
        severity=DiagnosticSeverity.WARNING,
    )
    assert diagnostic.severity is DiagnosticSeverity.WARNING

    with pytest.raises(ValueError):
        DomainDiagnostic("", "Message", DiagnosticSeverity.ERROR)
