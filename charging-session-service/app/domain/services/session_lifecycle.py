"""
Tilstandsmaskine for VoltEdge ladesessioner.

Lovlige overgange:
  PENDING    → AUTHORIZED
  AUTHORIZED → ACTIVE
  ACTIVE     → COMPLETED
  ACTIVE     → FAULTED

Alle andre overgange kaster ValueError og afvises af aggregatet.
"""

VALID_TRANSITIONS: dict[str, list[str]] = {
    "PENDING":    ["AUTHORIZED"],
    "AUTHORIZED": ["ACTIVE"],
    "ACTIVE":     ["COMPLETED", "FAULTED"],
    "COMPLETED":  [],
    "FAULTED":    [],
}


def transition(current_status: str, new_status: str) -> str:
    """Udfører statustransition hvis overgangen er lovlig — kaster ValueError ellers."""
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Ulovlig overgang: {current_status} → {new_status}. "
            f"Tilladte fra '{current_status}': {allowed or 'ingen'}"
        )
    return new_status
