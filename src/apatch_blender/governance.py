from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contracts import Contract


APATCH_PLAN_CHECK_PREFIX = "apatch-blender-plan:"
APATCH_TOOL_PREFIX = "apatch_blender:"


class GovernanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class GovernanceEvidence:
    mode: str
    plan_sha256: str
    session_id: str | None = None
    requirement: str | None = None
    actor_id: str | None = None
    contract_hash: str | None = None
    envelope_hash: str | None = None
    spec_artifact_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_digest(contract: Contract) -> str:
    return "sha256:" + hashlib.sha256(contract.path.read_bytes()).hexdigest()


def plan_check(contract: Contract) -> str:
    return APATCH_PLAN_CHECK_PREFIX + plan_digest(contract)


def operation_tool(operation_name: str) -> str:
    return APATCH_TOOL_PREFIX + operation_name


def _relative_to_root(root: Path, path: Path, field: str) -> str:
    root = root.resolve()
    path = path.resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise GovernanceError(f"{field} must be inside the APatch workspace root") from exc


def _write_paths(contract: Contract, root: Path) -> list[str]:
    values: list[str] = [contract.output_scene]

    execution_record = contract.raw.get("execution_record")
    if isinstance(execution_record, str) and execution_record:
        values.append(execution_record)

    preview_path = contract.raw.get("preview_path")
    if isinstance(preview_path, str) and preview_path:
        values.append(preview_path)

    verification_report = contract.raw.get("verification_report")
    if isinstance(verification_report, str) and verification_report:
        values.append(verification_report)

    video = contract.raw.get("video")
    if isinstance(video, dict):
        video_path = video.get("path")
        if isinstance(video_path, str) and video_path:
            values.append(video_path)

    for operation in contract.operations:
        if operation.get("op") != "render_preview":
            continue
        path = operation.get("params", {}).get("path")
        if isinstance(path, str) and path:
            values.append(path)

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        resolved = contract.resolve(root, value)
        relative = _relative_to_root(root, resolved, "Blender write path")
        if relative not in seen:
            seen.add(relative)
            result.append(relative)
    return result


def required_apatch_scope(contract: Contract, root: str | Path) -> dict[str, Any]:
    root_path = Path(root).resolve()
    plan_path = _relative_to_root(root_path, contract.path, "contract plan")
    tools = list(dict.fromkeys(operation_tool(item["op"]) for item in contract.operations))

    return {
        "requirement": contract.governance.get("requirement"),
        "allowed_reads": [plan_path, contract.base_scene],
        "allowed_writes": _write_paths(contract, root_path),
        "tools": tools,
        "checks": [plan_check(contract)],
    }


def _load_apatch_api():
    try:
        from apatch.sdd_integrity import SddAdmissionError, admit_session_effect
        from apatch.session_state import load_session_state
    except ImportError as exc:
        raise GovernanceError(
            'APatch-governed execution requires the optional dependency: '
            'pip install "apatch-blender[apatch]"'
        ) from exc
    return load_session_state, admit_session_effect, SddAdmissionError


def _require_spec_artifact(state: dict[str, Any], requirement: str) -> dict[str, Any]:
    for artifact in state.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("kind") != "spec" or artifact.get("id") != requirement:
            continue
        if not artifact.get("content_hash"):
            raise GovernanceError(
                f"APatch spec artifact {requirement!r} is missing its content hash"
            )
        return artifact
    raise GovernanceError(
        f"Active APatch session is not anchored to spec artifact {requirement!r}"
    )


def authorize_contract(contract: Contract, root: str | Path) -> GovernanceEvidence:
    mode = str(contract.governance.get("mode") or "standalone")
    digest = plan_digest(contract)
    if mode == "standalone":
        return GovernanceEvidence(mode=mode, plan_sha256=digest)
    if mode != "apatch_sdd":
        raise GovernanceError(f"Unsupported governance mode: {mode}")

    requirement = str(contract.governance.get("requirement") or "")
    if not requirement:
        raise GovernanceError("apatch_sdd governance requires a requirement")

    root_path = Path(root).resolve()
    scope = required_apatch_scope(contract, root_path)
    load_session_state, admit_session_effect, admission_error = _load_apatch_api()
    state = load_session_state(str(root_path))

    session_id = str(state.get("session_id") or "")
    if not session_id or state.get("ended_at"):
        raise GovernanceError("APatch-governed Blender execution requires an active session")

    sdd = state.get("sdd")
    if not isinstance(sdd, dict):
        raise GovernanceError("Active APatch session has no SDD task-envelope binding")
    if sdd.get("requirement") != requirement:
        raise GovernanceError(
            f"APatch session requirement {sdd.get('requirement')!r} does not match "
            f"Blender plan requirement {requirement!r}"
        )

    actor = sdd.get("actor")
    if not isinstance(actor, dict) or actor.get("role") != "implementation":
        raise GovernanceError("Blender execution requires an APatch implementation capability")

    spec_artifact = _require_spec_artifact(state, requirement)

    capability = sdd.get("capability")
    envelope = capability.get("envelope") if isinstance(capability, dict) else None
    if not isinstance(envelope, dict):
        raise GovernanceError("APatch session capability has no task envelope")

    expected_plan_check = plan_check(contract)
    if expected_plan_check not in (envelope.get("checks") or []):
        raise GovernanceError(
            "The active APatch task envelope is not bound to the exact Blender plan hash"
        )

    try:
        if scope["allowed_writes"]:
            admit_session_effect(
                str(root_path),
                {
                    "surface": "mutation",
                    "effect": "write",
                    "paths": scope["allowed_writes"],
                    "plan_match": True,
                },
            )
        for tool in scope["tools"]:
            admit_session_effect(
                str(root_path),
                {
                    "surface": "mcp_tool",
                    "effect": "invoke",
                    "tool": tool,
                    "plan_match": True,
                },
            )
    except admission_error as exc:
        raise GovernanceError(f"APatch denied Blender execution: {exc}") from exc

    return GovernanceEvidence(
        mode=mode,
        plan_sha256=digest,
        session_id=session_id,
        requirement=requirement,
        actor_id=str(actor.get("actor_id") or "") or None,
        contract_hash=str(sdd.get("contract_hash") or "") or None,
        envelope_hash=str(sdd.get("envelope_hash") or "") or None,
        spec_artifact_hash=str(spec_artifact.get("content_hash") or "") or None,
    )
