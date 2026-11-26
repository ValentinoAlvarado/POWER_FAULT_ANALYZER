"""Registry separating standards publication metadata from PFA implementation evidence."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum


class ImplementationStatus(StrEnum):
    NOT_ASSESSED = "not_assessed"
    RESEARCH = "research"
    SPECIFIED = "specified"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    VALIDATED = "validated"


@dataclass(frozen=True, slots=True)
class StandardRecord:
    identifier: str
    title: str
    edition: str
    publication_date: str | None
    scope: str
    implementation_status: ImplementationStatus
    evidence: tuple[str, ...] = ()
    notes: str = ""


STANDARDS = (
    StandardRecord(
        "IEC 60909-0",
        "Short-circuit currents in three-phase a.c. systems — Part 0: Calculation of currents",
        "2026, Edition 3.0", "2026-07-23",
        "Short-circuit current calculation in three-phase AC systems.",
        ImplementationStatus.RESEARCH,
        ("https://webstore.iec.ch/",),
        "The existing PFA symmetrical-components solver is a general network fault solver. "
        "Do not label it IEC 60909 compliant until the 2026 edition procedures, factors, "
        "applicability conditions and independent validation have been implemented and audited.",
    ),
    StandardRecord(
        "IEC 60617", "Graphical symbols for diagrams",
        "Verify current catalogue edition per symbol family", None,
        "Graphical symbols used in electrotechnical diagrams.",
        ImplementationStatus.RESEARCH, ("https://www.iec.ch/standards",),
        "Maintain PFA-owned vector assets and normative mappings; visual resemblance alone "
        "does not establish normative equivalence.",
    ),
    StandardRecord(
        "IEC 61082-1", "Preparation of documents used in electrotechnology",
        "Verify current edition", None,
        "Rules for preparation of electrotechnical documents.",
        ImplementationStatus.NOT_ASSESSED, ("https://www.iec.ch/standards",),
        "Requires a clause-level compliance matrix.",
    ),
)


def get_standard(identifier: str) -> StandardRecord:
    normalized = identifier.strip().casefold()
    for record in STANDARDS:
        if record.identifier.casefold() == normalized:
            return record
    raise KeyError(f"Unknown standard identifier: {identifier!r}")
