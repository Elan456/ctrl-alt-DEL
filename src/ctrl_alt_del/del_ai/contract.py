from __future__ import annotations

from importlib.resources import files
from typing import Any

import yaml

COMMAND_CONTRACT_FILE = "del_commands.yaml"


def load_command_contract() -> dict[str, Any]:
    raw = files("ctrl_alt_del.data").joinpath(COMMAND_CONTRACT_FILE).read_text()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{COMMAND_CONTRACT_FILE} must be a YAML mapping")
    return data
