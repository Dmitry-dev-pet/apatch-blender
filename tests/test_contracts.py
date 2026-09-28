import json
from pathlib import Path

import pytest

from apatch_blender.contracts import ContractError, load_contract


def write_contract(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(payload))
    return path


def base_payload():
    return {
        "schema_version": 1,
        "id": "TEST-001",
        "base_scene": "base.blend",
        "output_scene": "out.blend",
        "allowed_operations": ["set_world"],
        "operations": [
            {
                "op": "set_world",
                "params": {"color": [0, 0, 0, 1], "strength": 0.1},
            }
        ],
        "protected": {
            "object_globs": ["Cube*"],
            "animation_object_globs": ["Cube*"],
            "frames": "all",
        },
        "expected": {},
    }


def test_loads_valid_contract(tmp_path):
    contract = load_contract(write_contract(tmp_path, base_payload()))
    assert contract.id == "TEST-001"
    assert contract.allowed_operations == frozenset({"set_world"})


def test_rejects_operation_not_authorized(tmp_path):
    payload = base_payload()
    payload["operations"][0]["op"] = "add_area_light"
    with pytest.raises(ContractError, match="not present in allowed_operations"):
        load_contract(write_contract(tmp_path, payload))


def test_rejects_unknown_operation(tmp_path):
    payload = base_payload()
    payload["allowed_operations"] = ["launch_missiles"]
    payload["operations"][0]["op"] = "launch_missiles"
    with pytest.raises(ContractError, match="Unsupported allowed_operations"):
        load_contract(write_contract(tmp_path, payload))


def test_resolve_rejects_workspace_escape(tmp_path):
    contract = load_contract(write_contract(tmp_path, base_payload()))
    with pytest.raises(ContractError, match="escapes workspace root"):
        contract.resolve(tmp_path, "../outside.blend")
