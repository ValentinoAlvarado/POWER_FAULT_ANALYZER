"""Immutable electrical-domain value objects."""

from power_fault_analyzer.domain.value_objects.advanced_protection import (
    AdvancedProtectionFunctionAssessment,
    AdvancedProtectionFunctionBinding,
    AdvancedProtectionFunctionMeasurement,
    AdvancedProtectionNetworkAssessment,
    AdvancedProtectionScenarioAssessment,
    AdvancedProtectionScenarioMeasurements,
    CTExcitationPoint,
    CTSaturationAssessment,
    CurrentTransformerPerformanceBinding,
    CurrentTransformerPerformanceModel,
    DifferentialMeasurement,
    DifferentialOperationResult,
    DifferentialPhaseOperation,
    DifferentialProtectionSettings,
    DifferentialSideSettings,
    DirectionalMeasurement,
    DirectionalOperationResult,
    DirectionalOvercurrentSettings,
    DistanceLoopOperation,
    DistanceMeasurement,
    DistanceOperationResult,
    DistanceProtectionSettings,
    DistanceZoneSettings,
    VoltageTransformerRatio,
)
from power_fault_analyzer.domain.value_objects.branch_equivalent import BranchEquivalentModel
from power_fault_analyzer.domain.value_objects.connection import Connection
from power_fault_analyzer.domain.value_objects.converter_current_command import (
    ConverterSequenceCurrentCommand,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.iec60909_study import (
    IEC60909StudyResult,
    IEC60909StudySpecification,
)
from power_fault_analyzer.domain.value_objects.impedance import Admittance, Impedance
from power_fault_analyzer.domain.value_objects.line_fault_result import (
    LineFaultStudyResult,
    LineTerminalState,
)
from power_fault_analyzer.domain.value_objects.line_fault_specification import (
    LineFaultSpecification,
)
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)
from power_fault_analyzer.domain.value_objects.protection_assessment import (
    ConductorThermalAssessment,
    CoordinationAssessment,
    CoordinationSample,
    EquipmentDutyAssessment,
    RelaySensitivityAssessment,
)
from power_fault_analyzer.domain.value_objects.protection_devices import (
    CircuitBreaker,
    ConductorThermalLimit,
    CurrentTransformerRatio,
    FuseLink,
    FuseTimeCurrentPoint,
    OvercurrentRelay,
    RelayOperatingPoint,
)
from power_fault_analyzer.domain.value_objects.protection_network import (
    ProtectionBackupCheck,
    ProtectionBackupRelationship,
    ProtectionCurrentMeasurement,
    ProtectionDeviceBinding,
    ProtectionDeviceOperation,
    ProtectionFaultScenario,
    ProtectionNetworkAssessment,
    ProtectionNetworkModel,
    ProtectionScenarioMeasurements,
    ProtectionZone,
    ProtectionZoneScenarioAssessment,
)
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    AdmittancePerLength,
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceAdmittanceSet,
    SequenceImpedancePerLengthSet,
    SequenceImpedanceSet,
)
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
    ExternalGridShortCircuitData,
    InductionGeneratorParameters,
    SourceEquivalentSet,
    SourceSequenceEquivalent,
    SynchronousMachineSequenceImpedances,
)
from power_fault_analyzer.domain.value_objects.tap_changer import TapChanger
from power_fault_analyzer.domain.value_objects.three_winding_zero_sequence import (
    ThreeWindingZeroSequencePortModel,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
    ThreeWindingStarEquivalent,
    TransformerImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.transient_protection import (
    BreakerPoleInterruption,
    BreakerTransientResult,
    BreakerTransientSettings,
    CTTransientSample,
    CTTransientSimulationResult,
    CTTransientSimulationSettings,
    RelayCurrentSample,
    RelayTransientResult,
    RelayTransientSample,
    RelayTransientSettings,
    ThreePhaseCurrentSample,
)
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.domain.value_objects.voltage import Voltage, VoltageReference

__all__ = [
    "Admittance",
    "AdmittancePerLength",
    "AdvancedProtectionFunctionAssessment",
    "AdvancedProtectionFunctionBinding",
    "AdvancedProtectionFunctionMeasurement",
    "AdvancedProtectionNetworkAssessment",
    "AdvancedProtectionScenarioAssessment",
    "AdvancedProtectionScenarioMeasurements",
    "BranchEquivalentModel",
    "BreakerPoleInterruption",
    "BreakerTransientResult",
    "BreakerTransientSettings",
    "CTExcitationPoint",
    "CTSaturationAssessment",
    "CTTransientSample",
    "CTTransientSimulationResult",
    "CTTransientSimulationSettings",
    "CircuitBreaker",
    "ConductorThermalAssessment",
    "ConductorThermalLimit",
    "Connection",
    "ConverterFaultCurrentCapability",
    "ConverterSequenceCurrentCommand",
    "CoordinationAssessment",
    "CoordinationSample",
    "CurrentTransformerPerformanceBinding",
    "CurrentTransformerPerformanceModel",
    "CurrentTransformerRatio",
    "DiagnosticSeverity",
    "DifferentialMeasurement",
    "DifferentialOperationResult",
    "DifferentialPhaseOperation",
    "DifferentialProtectionSettings",
    "DifferentialSideSettings",
    "DirectionalMeasurement",
    "DirectionalOperationResult",
    "DirectionalOvercurrentSettings",
    "DistanceLoopOperation",
    "DistanceMeasurement",
    "DistanceOperationResult",
    "DistanceProtectionSettings",
    "DistanceZoneSettings",
    "DomainDiagnostic",
    "ElectricalImpedanceBase",
    "EquipmentDutyAssessment",
    "ExternalGridShortCircuitData",
    "FaultSpecification",
    "Frequency",
    "FuseLink",
    "FuseTimeCurrentPoint",
    "IEC60909StudyResult",
    "IEC60909StudySpecification",
    "Impedance",
    "ImpedancePerLength",
    "InductionGeneratorParameters",
    "LineFaultSpecification",
    "LineFaultStudyResult",
    "LineTerminalState",
    "NeutralGrounding",
    "OvercurrentRelay",
    "PairwiseTransformerImpedances",
    "PerUnitImpedance",
    "ProtectionBackupCheck",
    "ProtectionBackupRelationship",
    "ProtectionCurrentMeasurement",
    "ProtectionDeviceBinding",
    "ProtectionDeviceOperation",
    "ProtectionFaultScenario",
    "ProtectionNetworkAssessment",
    "ProtectionNetworkModel",
    "ProtectionScenarioMeasurements",
    "ProtectionZone",
    "ProtectionZoneScenarioAssessment",
    "RelayCurrentSample",
    "RelayOperatingPoint",
    "RelaySensitivityAssessment",
    "RelayTransientResult",
    "RelayTransientSample",
    "RelayTransientSettings",
    "SequenceAdmittancePerLengthSet",
    "SequenceAdmittanceSet",
    "SequenceImpedancePerLengthSet",
    "SequenceImpedanceSet",
    "SequencePerUnitImpedance",
    "ShortCircuitResult",
    "SourceEquivalentSet",
    "SourceSequenceEquivalent",
    "SynchronousMachineSequenceImpedances",
    "TapChanger",
    "ThreePhaseCurrentSample",
    "ThreeWindingStarEquivalent",
    "ThreeWindingZeroSequencePortModel",
    "TransformerImpedanceBase",
    "TransformerWinding",
    "VectorGroup",
    "Voltage",
    "VoltageReference",
    "VoltageTransformerRatio",
]
