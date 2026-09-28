from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

SUPPORTED_OPERATIONS = {
    "set_world",
    "scale_camera_framing",
    "add_area_light",
    "set_material",
    "set_transform",
    "set_render",
    "render_preview",
}


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Contract:
    path: Path
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def base_scene(self) -> str:
        return self.raw["base_scene"]

    @property
    def output_scene(self) -> str:
        return self.raw["output_scene"]

    @property
    def allowed_operations(self) -> frozenset[str]:
        return frozenset(self.raw["allowed_operations"])

    @property
    def operations(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.raw["operations"])

    @property
    def protected(self) -> dict[str, Any]:
        return self.raw.get("protected", {})

    @property
    def expected(self) -> dict[str, Any]:
        return self.raw.get("expected", {})

    def resolve(self, root: Path, relative_path: str) -> Path:
        root = root.resolve()
        path = (root / relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ContractError(
                f"Path escapes workspace root: {relative_path!r}"
            ) from exc
        return path


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be an object")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _validate_contract(raw: dict[str, Any]) -> None:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(
            f"schema_version must be {SCHEMA_VERSION}; got {raw.get('schema_version')!r}"
        )

    _require_string(raw.get("id"), "id")
    _require_string(raw.get("base_scene"), "base_scene")
    _require_string(raw.get("output_scene"), "output_scene")

    allowed = raw.get("allowed_operations")
    if not isinstance(allowed, list) or not allowed:
        raise ContractError("allowed_operations must be a non-empty list")

    unknown_allowed = sorted(set(allowed) - SUPPORTED_OPERATIONS)
    if unknown_allowed:
        raise ContractError(
            f"Unsupported allowed_operations: {', '.join(unknown_allowed)}"
        )

    operations = raw.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ContractError("operations must be a non-empty list")

    for index, operation in enumerate(operations):
        operation = _require_mapping(operation, f"operations[{index}]")
        op_name = _require_string(operation.get("op"), f"operations[{index}].op")
        if op_name not in SUPPORTED_OPERATIONS:
            raise ContractError(f"Unsupported operation {op_name!r}")
        if op_name not in allowed:
            raise ContractError(
                f"Operation {op_name!r} is not present in allowed_operations"
            )
        params = operation.get("params", {})
        _require_mapping(params, f"operations[{index}].params")

    protected = raw.get("protected", {})
    protected = _require_mapping(protected, "protected")
    object_globs = protected.get("object_globs", [])
    if not isinstance(object_globs, list) or not all(
        isinstance(pattern, str) and pattern for pattern in object_globs
    ):
        raise ContractError("protected.object_globs must be a list of strings")

    animation_globs = protected.get("animation_object_globs", object_globs)
    if not isinstance(animation_globs, list) or not all(
        isinstance(pattern, str) and pattern for pattern in animation_globs
    ):
        raise ContractError(
            "protected.animation_object_globs must be a list of strings"
        )

    frames = protected.get("frames", [])
    if frames != "all" and (
        not isinstance(frames, list)
        or not all(isinstance(frame, int) for frame in frames)
    ):
        raise ContractError('protected.frames must be "all" or a list of integers')

    expected = raw.get("expected", {})
    _require_mapping(expected, "expected")


def load_contract(path: str | Path) -> Contract:
    contract_path = Path(path).resolve()
    if not contract_path.is_file():
        raise ContractError(f"Contract does not exist: {contract_path}")

    try:
        raw = json.loads(contract_path.read_text())
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"Invalid JSON in contract {contract_path}: {exc}"
        ) from exc

    raw = _require_mapping(raw, "contract")
    _validate_contract(raw)
    return Contract(path=contract_path, raw=raw)
