from __future__ import annotations

from typing import Optional

from aq_common.config_loader import load_units


UNITS = load_units()
CANONICAL = UNITS.get("canonical_unit", "ug/m3")
CONVERSION_MODE = UNITS.get("conversion_mode", "fixed_25C_1atm")
MW = UNITS.get("molecular_weights", {})


def normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.strip().lower()
    aliases = {
        "ug/m3": "ug/m3",
        "ug/m^3": "ug/m3",
        "µg/m3": "ug/m3",
        "μg/m³": "ug/m3",
        "µg/m³": "ug/m3",
        "mg/m3": "mg/m3",
        "ppm": "ppm",
        "ppb": "ppb",
    }
    return aliases.get(u, u)


def to_canonical(pollutant: str, value: Optional[float], unit: str | None) -> tuple[Optional[float], str]:
    if value is None:
        return None, CANONICAL
    unit_norm = normalize_unit(unit) or CANONICAL
    pol = pollutant.upper()

    if unit_norm == CANONICAL:
        return float(value), CANONICAL
    if unit_norm == "mg/m3":
        return float(value) * 1000.0, CANONICAL
    if unit_norm == "ppb" and pol in MW:
        # ug/m3 = ppb * MW / 24.45 at 25C, 1 atm.
        return float(value) * float(MW[pol]) / 24.45, CANONICAL
    if unit_norm == "ppm":
        # 1 ppm = 1000 ppb.
        ppb_value = float(value) * 1000.0
        if pol in MW:
            return ppb_value * float(MW[pol]) / 24.45, CANONICAL
    return float(value), CANONICAL


def from_canonical(
    pollutant: str, canonical_value: Optional[float], target_unit: str
) -> Optional[float]:
    if canonical_value is None:
        return None
    t = normalize_unit(target_unit)
    if t is None or t == CANONICAL:
        return float(canonical_value)
    if t == "mg/m3":
        return float(canonical_value) / 1000.0
    pol = pollutant.upper()
    if t == "ppb" and pol in MW:
        return float(canonical_value) * 24.45 / float(MW[pol])
    if t == "ppm" and pol in MW:
        return float(canonical_value) * 24.45 / float(MW[pol]) / 1000.0
    return float(canonical_value)

