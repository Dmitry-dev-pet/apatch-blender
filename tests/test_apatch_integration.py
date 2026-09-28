import json
from pathlib import Path

import pytest

from apatch_blender.contracts import load_contract
from apatch_blender.governance import GovernanceError, authorize_contract, required_apatch_scope


apatch = pytest.importorskip("apatch.sdd_integrity")


def _freeze_request() -> dict:
    obligation = {
        "acceptance_id": "AC-BLENDER-1",
        "test_id": "tests/test_bridge_contract.py::test_governed_execution",
        "oracle": "Only the frozen Blender plan may execute inside the admitted scope",
        "perspectives": ["positive", "negative", "boundary", "regression"],
        "asset_hashes": ["sha256:" + "a" * 64],
        "judge_assets": [
            {
                "path": "tests/test_bridge_contract.py",
                "sha256": "sha256:" + "a" * 64,
            }
        ],
        "command": [
            "python3",
            "-m",
            "pytest",
            "tests/test_bridge_contract.py::test_governed_execution",
            "-q",
        ],
        "command_hash": "sha256:" + "b" * 64,
        "baseline": {
            "kind": "observed_red",
            "result_hash": "sha256:" + "c" * 64,
        },
        "falsification": {
            "kind": "reversible_seed",
            "expected": "red",
            "target_hash": "sha256:" + "d" * 64,
            "target_path": "src/apatch_blender/executor.py",
        },
        "approver": "owner:test",
        "material": True,
    }
    return {
        "brief_hash": "sha256:" + "1" * 64,
        "rfp_hash": "sha256:" + "2" * 64,
        "spec_hash": "sha256:" + "3" * 64,
        "plan_hash": "sha256:" + "4" * 64,
        "baseline_hash": "sha256:" + "5" * 64,
        "coverage": {
            "complete": True,
            "missing": [],
            "ambiguous": [],
            "waivers": [],
        },
        "obligations": [obligation],
        "authority": {"actor_id": "owner:test", "role": "authority"},
        "source_mutation_count": 0,
        "frozen_at": "2026-09-28T12:00:00.000000Z",
    }


def _plan() -> dict:
    return {
        "schema_version": 1,
        "id": "BLENDER-LIVE-APATCH-001",
        "base_scene": "input/base.blend",
        "output_scene": "output/edited.blend",
        "execution_record": "evidence/execution.json",
        "allowed_operations": ["set_world", "render_preview"],
        "operations": [
            {
                "op": "set_world",
                "params": {
                    "color": [0.0025, 0.006, 0.018, 1.0],
                    "strength": 0.1,
                },
            },
            {
                "op": "render_preview",
                "params": {"frame": 1, "path": "evidence/preview.png"},
            },
        ],
        "protected": {"object_globs": [], "frames": []},
        "expected": {},
        "governance": {
            "mode": "apatch_sdd",
            "requirement": "SPEC-BLENDER-1#R1",
        },
    }


def test_real_apatch_session_admits_exact_plan_and_rejects_drift(tmp_path: Path):
    from apatch.runtime.session import start_session

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan(), sort_keys=True))
    contract = load_contract(plan_path)
    scope = required_apatch_scope(contract, tmp_path)

    frozen = apatch.freeze_contract(_freeze_request())
    envelope = apatch.validate_task_envelope(
        {
            "schema": "apatch.sdd.task-envelope.v1",
            "requirement": scope["requirement"],
            "contract_hash": frozen["document_hash"],
            "baseline_hash": "sha256:" + "5" * 64,
            "allowed_reads": scope["allowed_reads"],
            "allowed_writes": scope["allowed_writes"],
            "allowed_symbols": [],
            "forbidden_paths": ["docs/specs/**", "tests/**", "schemas/**"],
            "tools": scope["tools"],
            "commands": [],
            "network": [],
            "remote": [],
            "services": [],
            "budgets": {
                "files": 4,
                "insertions": 0,
                "deletions": 0,
                "seconds": 300,
            },
            "checks": scope["checks"],
            "rollback_owner": "session:self",
            "containment": "mediated_only",
        }
    )

    started = start_session(
        str(tmp_path),
        "SPEC-BLENDER-1#R1: render the admitted Blender plan",
        artifacts=[
            {
                "kind": "spec",
                "id": "SPEC-BLENDER-1#R1",
                "content_hash": "sha256:" + "9" * 64,
            }
        ],
        sdd_contract=frozen,
        task_envelope=envelope,
        actor={"actor_id": "agent:integration", "role": "implementation"},
    )
    assert started["ok"] is True

    evidence = authorize_contract(contract, tmp_path)
    assert evidence.session_id == started["session_capability"]["session_id"]
    assert evidence.requirement == "SPEC-BLENDER-1#R1"
    assert evidence.contract_hash == frozen["document_hash"]
    assert evidence.envelope_hash == envelope["document_hash"]
    assert evidence.actor_id == "agent:integration"

    changed = _plan()
    changed["operations"][0]["params"]["strength"] = 0.2
    plan_path.write_text(json.dumps(changed, sort_keys=True))
    drifted_contract = load_contract(plan_path)

    with pytest.raises(GovernanceError, match="exact Blender plan hash"):
        authorize_contract(drifted_contract, tmp_path)
