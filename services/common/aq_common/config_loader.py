from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT / "config"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def load_cities() -> list[dict[str, Any]]:
    return load_yaml(CONFIG_DIR / "cities.yaml").get("cities", [])


def load_thresholds() -> dict[str, dict[str, float]]:
    return load_yaml(CONFIG_DIR / "thresholds.yaml").get("thresholds", {})


def load_units() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "units.yaml")


def load_collector_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "collector.yaml")

