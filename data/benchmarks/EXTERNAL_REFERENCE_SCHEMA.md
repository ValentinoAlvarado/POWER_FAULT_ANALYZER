# External reference JSON interchange — schema 1.0.0

This is a data interchange format, not a claim that a third-party calculation has been performed.

## Required document fields

- `schema_version`: exactly `1.0.0`
- `tool_name`: non-empty vendor/application name
- `tool_version`: actual installed release/build identifier
- `reference_dataset_id`: exactly `PFA-ND016-ANALYTICAL-FAULTS-001`
- `case_id`: one of the reference case IDs in `data/reference_cases/nd016_analytical_fault_cases.json`
- `quantities`: non-empty object of supported identifiers

Each quantity is `{ "value": number | { "real": number, "imag": number }, "unit": string }`. Real values must be finite. Complex values are intended for phasors. Units must match the identifier.

## Supported quantity identifiers

| Identifier | Unit |
|---|---|
| `sequence_current_zero_pu` | p.u. |
| `sequence_current_positive_pu` | p.u. |
| `sequence_current_negative_pu` | p.u. |
| `ground_current_pu` | p.u. |
| `ground_current_ka` | kA |
| `base_current_ka` | kA |
| `phase_current_A_pu`, `phase_current_B_pu`, `phase_current_C_pu` | p.u. |
| `phase_current_A_ka`, `phase_current_B_ka`, `phase_current_C_ka` | kA |
| `phase_voltage_A_pu`, `phase_voltage_B_pu`, `phase_voltage_C_pu` | p.u. |
| `phase_voltage_A_kv`, `phase_voltage_B_kv`, `phase_voltage_C_kv` | kV |

## Template

Replace all metadata and values with the actual independently calculated case output. Do not use example/placeholder numbers as benchmark results.

```json
{
  "schema_version": "1.0.0",
  "tool_name": "REPLACE_WITH_ACTUAL_TOOL_NAME",
  "tool_version": "REPLACE_WITH_ACTUAL_VERSION",
  "reference_dataset_id": "PFA-ND016-ANALYTICAL-FAULTS-001",
  "case_id": "REF-3PH-001",
  "quantities": {
    "sequence_current_positive_pu": {
      "value": { "real": 0.0, "imag": 0.0 },
      "unit": "p.u."
    },
    "phase_current_A_ka": {
      "value": { "real": 0.0, "imag": 0.0 },
      "unit": "kA"
    }
  }
}
```
