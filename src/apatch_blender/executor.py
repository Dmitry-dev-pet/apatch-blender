from __future__ import annotations

import json
from pathlib import Path

import bpy

from .contracts import Contract, load_contract
from .governance import authorize_contract
from .ops import execute_operation


def execute_contract(contract: Contract, root: Path) -> dict:
    root = root.resolve()
    base_scene = contract.resolve(root, contract.base_scene)
    output_scene = contract.resolve(root, contract.output_scene)

    if not base_scene.is_file():
        raise FileNotFoundError(f"Base scene not found: {base_scene}")

    governance = authorize_contract(contract, root)
    output_scene.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(base_scene))
    scene = bpy.context.scene
    scene["apatch_blender_contract_id"] = contract.id
    scene["apatch_blender_governance_mode"] = governance.mode
    scene["apatch_blender_plan_sha256"] = governance.plan_sha256
    if governance.session_id:
        scene["apatch_session_id"] = governance.session_id
    if governance.requirement:
        scene["apatch_requirement"] = governance.requirement
    if governance.envelope_hash:
        scene["apatch_envelope_hash"] = governance.envelope_hash

    results = []
    for index, operation in enumerate(contract.operations):
        op_name = operation["op"]
        if op_name not in contract.allowed_operations:
            raise RuntimeError(
                f"Operation {op_name!r} is not authorized by contract {contract.id}"
            )
        result = execute_operation(op_name, operation.get("params", {}), root)
        results.append({"index": index, "op": op_name, "result": result})

    bpy.ops.wm.save_as_mainfile(filepath=str(output_scene))

    execution = {
        "contract": contract.id,
        "base_scene": str(base_scene),
        "output_scene": str(output_scene),
        "operations": results,
        "governance": governance.to_dict(),
    }

    execution_path_value = contract.raw.get("execution_record")
    if execution_path_value:
        execution_path = contract.resolve(root, execution_path_value)
        execution_path.parent.mkdir(parents=True, exist_ok=True)
        execution_path.write_text(json.dumps(execution, indent=2) + "\n")

    return execution


def execute_contract_file(contract_path: str | Path, root: str | Path) -> dict:
    contract = load_contract(contract_path)
    return execute_contract(contract, Path(root))
