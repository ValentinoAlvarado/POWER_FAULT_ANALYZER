from __future__ import annotations

import pytest

from power_fault_analyzer.standards.registry import STANDARDS, ImplementationStatus, get_standard


def test_iec_60909_2026_is_registered_without_false_conformity_claim() -> None:
    record = get_standard("IEC 60909-0")
    assert record.edition == "2026, Edition 3.0"
    assert record.implementation_status is ImplementationStatus.RESEARCH
    assert "Do not label it IEC 60909 compliant" in record.notes


def test_standard_lookup_is_case_insensitive() -> None:
    assert get_standard("iec 60617").identifier == "IEC 60617"


def test_unknown_standard_is_rejected() -> None:
    with pytest.raises(KeyError):
        get_standard("IEC 99999")


def test_registry_identifiers_are_unique() -> None:
    identifiers = [record.identifier for record in STANDARDS]
    assert len(identifiers) == len(set(identifiers))
