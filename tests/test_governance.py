import json
from pathlib import Path

import pytest

from apatch_blender.contracts import ContractError, load_contract
from apatch_blender import governance


def write_contract(tmp_path: Path, payload: dict):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload, sort_keys=True))
    return load_contract(path)


def payload():
    return {
        "schema_version": 1,
        "id": "BLENDER-GOV-001",
        "base_scene": "input/base.blend",
        "output_scene": "output/edited.blend",
        "execution_record": "evidence/execution.json",
        "verification_report": "evidence/verification.json",
        "video": {"path": "output/final.mp4"},
        "allowed_operations": ["set_world", "render_preview"],
        "operations": [
            {
                "op": "set_world",
                "params": {"color": [0, 0, 0, 1], "strength": 0.1},
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


def test_contract_requires_requirement_for_apatch_sdd(tmp_path):
    raw = payload()
    del raw["governance"]["requirement"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ContractError, match="governance.requirement"):
        load_contract(path)


def test_required_scope_binds_plan_operations_and_writes(tmp_path):
    contract = write_contract(tmp_path, payload())
    scope = governance.required_apatch_scope(contract, tmp_path)

    assert scope["requirement"] == "SPEC-BLENDER-1#R1"
    assert scope["allowed_writes"] == [
        "output/edited.blend",
        "evidence/execution.json",
        "evidence/verification.json",
        "output/final.mp4",
        "evidence/preview.png",
    ]
    assert scope["tools"] == [
        "apatch_blender:set_world",
        "apatch_blender:render_preview",
    ]
    assert scope["checks"] == [governance.plan_check(contract)]


class FakeAdmissionError(RuntimeError):
    pass


def test_authorize_contract_uses_live_apatch_session(monkeypatch, tmp_path):
    contract = write_contract(tmp_path, payload())
    scope = governance.required_apatch_scope(contract, tmp_path)
    admitted = []

    state = {
        "session_id": "apatch_sess_test",
        "ended_at": None,
        "artifacts": [
            {
                "kind": "spec",
                "id": "SPEC-BLENDER-1#R1",
                "content_hash": "sha256:reqhash",
            }
        ],
        "sdd": {
            "requirement": "SPEC-BLENDER-1#R1",
            "contract_hash": "sha256:contract",
            "envelope_hash": "sha256:envelope",
            "actor": {"actor_id": "agent-1", "role": "implementation"},
            "capability": {
                "envelope": {
                    "checks": scope["checks"],
                }
            },
        },
    }

    def admit(_root, effect):
        admitted.append(effect)
        return {"decision": "allowed"}

    monkeypatch.setattr(
        governance,
        "_load_apatch_api",
        lambda: (lambda _root: state, admit, FakeAdmissionError),
    )

    evidence = governance.authorize_contract(contract, tmp_path)

    assert evidence.session_id == "apatch_sess_test"
    assert evidence.requirement == "SPEC-BLENDER-1#R1"
    assert evidence.actor_id == "agent-1"
    assert evidence.spec_artifact_hash == "sha256:reqhash"
    assert admitted[0]["surface"] == "mutation"
    assert admitted[0]["paths"] == scope["allowed_writes"]
    assert [item["tool"] for item in admitted[1:]] == scope["tools"]


def test_authorize_contract_rejects_unbound_plan_hash(monkeypatch, tmp_path):
    contract = write_contract(tmp_path, payload())

    state = {
        "session_id": "apatch_sess_test",
        "ended_at": None,
        "artifacts": [
            {
                "kind": "spec",
                "id": "SPEC-BLENDER-1#R1",
                "content_hash": "sha256:reqhash",
            }
        ],
        "sdd": {
            "requirement": "SPEC-BLENDER-1#R1",
            "contract_hash": "sha256:contract",
            "envelope_hash": "sha256:envelope",
            "actor": {"actor_id": "agent-1", "role": "implementation"},
            "capability": {"envelope": {"checks": []}},
        },
    }

    monkeypatch.setattr(
        governance,
        "_load_apatch_api",
        lambda: (lambda _root: state, lambda *_args, **_kwargs: None, FakeAdmissionError),
    )

    with pytest.raises(governance.GovernanceError, match="exact Blender plan hash"):
        governance.authorize_contract(contract, tmp_path)


def test_authorize_contract_rejects_wrong_requirement(monkeypatch, tmp_path):
    contract = write_contract(tmp_path, payload())

    state = {
        "session_id": "apatch_sess_test",
        "ended_at": None,
        "artifacts": [],
        "sdd": {
            "requirement": "SPEC-OTHER#R9",
            "actor": {"actor_id": "agent-1", "role": "implementation"},
            "capability": {"envelope": {"checks": [governance.plan_check(contract)]}},
        },
    }

    monkeypatch.setattr(
        governance,
        "_load_apatch_api",
        lambda: (lambda _root: state, lambda *_args, **_kwargs: None, FakeAdmissionError),
    )

    with pytest.raises(governance.GovernanceError, match="does not match"):
        governance.authorize_contract(contract, tmp_path)
