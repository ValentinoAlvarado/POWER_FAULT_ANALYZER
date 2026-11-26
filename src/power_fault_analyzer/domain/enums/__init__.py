"""Domain enumerations."""

from power_fault_analyzer.domain.enums.advanced_protection import (
    DifferentialProtectionKind,
    DirectionalSense,
    DistanceCharacteristic,
    DistanceLoop,
)
from power_fault_analyzer.domain.enums.construction import (
    ConductorMaterial,
    InsulationMaterial,
    ScreenBonding,
)
from power_fault_analyzer.domain.enums.converter_control_mode import (
    ConverterControlMode,
    ConverterCurrentPriority,
)
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.iec60909 import (
    IEC60909CurrentCase,
    IEC60909LowVoltageTolerance,
)
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.domain.enums.protection import (
    CircuitBreakerStandard,
    IECInverseCurveType,
    ProtectionAssessmentStatus,
    ProtectionFunction,
    ProtectionStage,
)
from power_fault_analyzer.domain.enums.protection_network import (
    ProtectionFaultLocationKind,
    ProtectionRole,
)
from power_fault_analyzer.domain.enums.sequence_equipment_kind import SequenceEquipmentKind
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation

__all__ = [
    "CircuitBreakerStandard",
    "ConductorMaterial",
    "ConverterControlMode",
    "ConverterCurrentPriority",
    "DifferentialProtectionKind",
    "DirectionalSense",
    "DistanceCharacteristic",
    "DistanceLoop",
    "EquipmentFamily",
    "FaultType",
    "GroundingMode",
    "IEC60909CurrentCase",
    "IEC60909LowVoltageTolerance",
    "IECInverseCurveType",
    "InsulationMaterial",
    "LineModelKind",
    "ProtectionAssessmentStatus",
    "ProtectionFaultLocationKind",
    "ProtectionFunction",
    "ProtectionRole",
    "ProtectionStage",
    "ScreenBonding",
    "SequenceEquipmentKind",
    "SequenceSourceKind",
    "SequenceType",
    "SourceOperatingRegime",
    "SourceSequenceStatus",
    "WindingConnection",
    "WindingDesignation",
]
