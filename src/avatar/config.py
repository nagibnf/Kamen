"""Config helpers for stack and persona."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


def load_yaml(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge of dicts, override wins."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def load_stack_config(path: str | Path) -> Dict[str, Any]:
    return load_yaml(path)


def load_persona_config(persona_id: str, personas_dir: str | Path) -> Dict[str, Any]:
    path = Path(personas_dir) / f"{persona_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Persona config not found: {path}")
    return load_yaml(path)


def build_effective_config(
    stack_cfg: Dict[str, Any], persona_cfg: Dict[str, Any]
) -> Dict[str, Any]:
    base_stack = stack_cfg.get("stack", {})
    override = persona_cfg.get("stack_override", {})
    effective_stack = merge_dict(base_stack, override)
    return {
        "persona": persona_cfg.get("persona", {}),
        "stack": effective_stack,
    }
