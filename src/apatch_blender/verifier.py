from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

import bpy

from .contracts import Contract, load_contract
from .manifest import (
    camera_payload,
    light_payload,
    protected_manifest,
    render_payload,
    world_payload,
)


def _close(a: float, b: float, tol: float = 1e-4) -> bool:
    return abs(float(a) - float(b)) <= tol


def _quat_close(actual, expected, tol: float = 1e-4) -> bool:
    return 1.0 - abs(float(actual.normalized().dot(expected.normalized()))) <= tol


def _vector_close(actual, expected, tol: float = 1e-4) -> bool:
    return (
        actual is not None
        and expected is not None
        and len(actual) == len(expected)
        and all(_close(a, b, tol) for a, b in zip(actual, expected))
    )


def _check(checks: dict, name: str, ok: bool, actual, expected):
    checks[name] = {
        "pass": bool(ok),
        "actual": actual,
        "expected": expected,
    }


def _open_snapshot(scene_path: Path, contract: Contract) -> dict[str, Any]:
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    return {
        "protected": protected_manifest(contract.protected),
        "world": world_payload(),
        "render": render_payload(),
    }


def _verify_expected(
    checks: dict,
    expected: dict[str, Any],
    base: dict[str, Any],
    edited: dict[str, Any],
):
    if "world" in expected:
        wanted = expected["world"]
        actual = edited["world"]
        ok = (
            actual is not None
            and _vector_close(actual["color"], wanted["color"])
            and _close(actual["strength"], wanted["strength"])
        )
        _check(checks, "expected_world", ok, actual, wanted)

    if "camera" in expected:
        spec = expected["camera"]
        name = spec.get("name")
        edited_camera = camera_payload(name)
        # Camera payload above was read from current file. The caller will
        # provide explicit base/edited camera payloads separately.
        _check(
            checks,
            "_internal_camera_placeholder",
            edited_camera is not None,
            edited_camera,
            "camera exists",
        )

    if "render" in expected:
        wanted = expected["render"]
        actual = edited["render"]
        ok = True
        for key, value in wanted.items():
            if actual.get(key) != value:
                ok = False
        _check(checks, "expected_render", ok, actual, wanted)


def _probe_video(path: Path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def verify_contract(contract: Contract, root: Path) -> dict[str, Any]:
    root = root.resolve()
    base_scene = contract.resolve(root, contract.base_scene)
    edited_scene = contract.resolve(root, contract.output_scene)

    if not base_scene.is_file():
        raise FileNotFoundError(f"Base scene not found: {base_scene}")
    if not edited_scene.is_file():
        raise FileNotFoundError(f"Edited scene not found: {edited_scene}")

    checks: dict[str, Any] = {}

    bpy.ops.wm.open_mainfile(filepath=str(base_scene))
    base_protected = protected_manifest(contract.protected)
    base_world = world_payload()
    base_render = render_payload()

    expected = contract.expected
    camera_spec = expected.get("camera", {})
    camera_name = camera_spec.get("name")
    base_camera = camera_payload(camera_name)

    light_specs = expected.get("lights", [])

    bpy.ops.wm.open_mainfile(filepath=str(edited_scene))
    edited_protected = protected_manifest(contract.protected)
    edited_world = world_payload()
    edited_render = render_payload()
    edited_camera = camera_payload(camera_name)

    _check(
        checks,
        "protected_static_unchanged",
        base_protected["static_hash"] == edited_protected["static_hash"],
        edited_protected["static_hash"],
        base_protected["static_hash"],
    )
    _check(
        checks,
        "protected_animation_unchanged",
        base_protected["animation_hash"] == edited_protected["animation_hash"],
        edited_protected["animation_hash"],
        base_protected["animation_hash"],
    )

    if "world" in expected:
        wanted = expected["world"]
        world_ok = (
            edited_world is not None
            and _vector_close(edited_world["color"], wanted["color"])
            and _close(edited_world["strength"], wanted["strength"])
            and edited_world != base_world
        )
        _check(
            checks,
            "expected_world",
            world_ok,
            {"base": base_world, "edited": edited_world},
            wanted,
        )

    if camera_spec:
        factor = float(camera_spec.get("framing_scale_factor", 1.0))
        transform_unchanged = bool(camera_spec.get("transform_unchanged", False))
        camera_type = camera_spec.get("type")

        camera_ok = base_camera is not None and edited_camera is not None
        if camera_ok and camera_type:
            camera_ok = (
                base_camera["type"] == camera_type
                and edited_camera["type"] == camera_type
            )

        if camera_ok and transform_unchanged:
            camera_ok = (
                _vector_close(base_camera["location"], edited_camera["location"])
                and _vector_close(base_camera["rotation"], edited_camera["rotation"])
                and _vector_close(base_camera["scale"], edited_camera["scale"])
            )

        if camera_ok and base_camera["type"] == "ORTHO":
            camera_ok = _close(
                edited_camera["ortho_scale"],
                base_camera["ortho_scale"] * factor,
            )
        elif camera_ok and "distance_target" in camera_spec:
            # Perspective-camera distance assertions can be added here
            # without changing the execution API.
            target = camera_spec["distance_target"]
            from mathutils import Vector

            base_distance = (
                Vector(base_camera["location"]) - Vector(target)
            ).length
            edited_distance = (
                Vector(edited_camera["location"]) - Vector(target)
            ).length
            camera_ok = _close(edited_distance, base_distance * factor)

        _check(
            checks,
            "expected_camera",
            camera_ok,
            {"base": base_camera, "edited": edited_camera},
            camera_spec,
        )


    camera_path_spec = expected.get("camera_path")
    if camera_path_spec:
        from mathutils import Vector

        path_camera = bpy.data.objects.get(camera_path_spec.get("name", "Camera"))
        checkpoints = camera_path_spec.get("checkpoints", [])
        tolerance = float(camera_path_spec.get("tolerance", 1e-3))
        failures = []
        original_frame = bpy.context.scene.frame_current

        if path_camera is None:
            failures.append({"error": "camera missing"})
        else:
            for checkpoint in checkpoints:
                frame = int(checkpoint["frame"])
                bpy.context.scene.frame_set(frame)

                expected_location = Vector(checkpoint["location"])
                expected_target = Vector(checkpoint["target"])
                actual_location = path_camera.location.copy()
                expected_quat = (
                    expected_target - expected_location
                ).to_track_quat("-Z", "Y")
                actual_quat = path_camera.rotation_euler.to_quaternion()

                ok = (
                    (actual_location - expected_location).length <= tolerance
                    and _quat_close(actual_quat, expected_quat, tolerance)
                )
                if "lens" in checkpoint:
                    ok = ok and _close(
                        path_camera.data.lens,
                        float(checkpoint["lens"]),
                        tolerance,
                    )

                if not ok:
                    failures.append(
                        {
                            "frame": frame,
                            "actual_location": list(actual_location),
                            "expected_location": list(expected_location),
                            "actual_rotation": list(path_camera.rotation_euler),
                            "expected_rotation": list(expected_quat.to_euler()),
                            "actual_lens": float(path_camera.data.lens),
                            "expected_lens": checkpoint.get("lens"),
                        }
                    )

        bpy.context.scene.frame_set(original_frame)
        _check(
            checks,
            "expected_camera_path",
            not failures and bool(checkpoints),
            failures,
            checkpoints,
        )

    for light_spec in light_specs:
        name = light_spec["name"]
        actual = light_payload(name)
        ok = actual is not None
        if ok and "type" in light_spec:
            ok = actual["type"] == light_spec["type"]
        if ok and "color" in light_spec:
            ok = _vector_close(actual["color"], light_spec["color"])
        if ok and "energy" in light_spec:
            ok = _close(actual["energy"], light_spec["energy"])
        if ok and "size" in light_spec:
            ok = _close(actual.get("size"), light_spec["size"])
        if ok and "location" in light_spec:
            ok = _vector_close(actual["location"], light_spec["location"])
        _check(checks, f"expected_light:{name}", ok, actual, light_spec)

    if "render" in expected:
        wanted = expected["render"]
        render_ok = all(edited_render.get(key) == value for key, value in wanted.items())
        _check(checks, "expected_render", render_ok, edited_render, wanted)

    preview_path = contract.raw.get("preview_path")
    if preview_path:
        preview = contract.resolve(root, preview_path)
        preview_ok = preview.exists() and preview.stat().st_size > 10_000
        _check(
            checks,
            "preview_exists",
            preview_ok,
            {
                "path": str(preview),
                "exists": preview.exists(),
                "size": preview.stat().st_size if preview.exists() else 0,
            },
            "PNG larger than 10 KB",
        )

    video_spec = contract.raw.get("video")
    if video_spec:
        video_path = contract.resolve(root, video_spec["path"])
        try:
            probe = _probe_video(video_path)
            stream = probe["streams"][0]
            fmt = probe["format"]
            num, den = stream["r_frame_rate"].split("/")
            actual = {
                "width": int(stream["width"]),
                "height": int(stream["height"]),
                "fps": float(num) / float(den),
                "duration": float(fmt["duration"]),
                "size": int(fmt["size"]),
            }
            ok = (
                actual["width"] == int(video_spec["width"])
                and actual["height"] == int(video_spec["height"])
                and _close(actual["fps"], video_spec["fps"], 1e-6)
                and abs(actual["duration"] - video_spec["duration"]) <= float(
                    video_spec.get("duration_tolerance", 0.15)
                )
                and actual["size"] > int(video_spec.get("min_size", 100_000))
            )
        except Exception as exc:
            ok = False
            actual = {"error": repr(exc)}

        _check(checks, "video_probe", ok, actual, video_spec)

    # Remove internal placeholders if future helper logic adds any.
    checks.pop("_internal_camera_placeholder", None)

    passed = all(item["pass"] for item in checks.values())
    report = {
        "contract": contract.id,
        "status": "PASS" if passed else "FAIL",
        "blender_version": bpy.app.version_string,
        "checks": checks,
        "protected": {
            "base_static_hash": base_protected["static_hash"],
            "edited_static_hash": edited_protected["static_hash"],
            "base_animation_hash": base_protected["animation_hash"],
            "edited_animation_hash": edited_protected["animation_hash"],
        },
    }

    report_path_value = contract.raw.get("verification_report")
    if report_path_value:
        report_path = contract.resolve(root, report_path_value)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    if not passed:
        raise RuntimeError(f"Contract {contract.id} verification failed")

    return report


def verify_contract_file(contract_path: str | Path, root: str | Path) -> dict[str, Any]:
    contract = load_contract(contract_path)
    return verify_contract(contract, Path(root))
