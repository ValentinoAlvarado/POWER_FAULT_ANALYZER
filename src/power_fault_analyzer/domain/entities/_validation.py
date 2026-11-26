"""Small shared validation helpers for electrical entities."""


def validate_non_empty_name(value: str, field_name: str = "name") -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty.")
