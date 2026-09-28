from __future__ import annotations

import fnmatch
import hashlib
import json
from typing import Any

import bpy


def _q(value: float) -> float:
    return round(float(value), 6)


def _vec(values):
    return [_q(value) for value in values]


def _matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _mesh_payload(mesh):
    return {
        "vertices": [_vec(vertex.co) for vertex in mesh.vertices],
        "polygons": [list(poly.vertices) for poly in mesh.polygons],
    }


def _curve_payload(curve):
    splines = []
    for spline in curve.splines:
        item: dict[str, Any] = {"type": spline.type}
        if spline.type == "BEZIER":
            item["bezier"] = [
                {
                    "co": _vec(point.co),
                    "left": _vec(point.handle_left),
                    "right": _vec(point.handle_right),
                }
                for point in spline.bezier_points
            ]
        else:
            item["points"] = [_vec(point.co) for point in spline.points]
        splines.append(item)
    return {
        "bevel_depth": _q(curve.bevel_depth),
        "bevel_resolution": int(curve.bevel_resolution),
        "splines": splines,
    }


def _font_payload(font):
    return {
        "body": font.body,
        "size": _q(font.size),
        "extrude": _q(font.extrude),
        "align_x": font.align_x,
        "align_y": font.align_y,
    }


def _data_payload(obj):
    if obj.type == "MESH":
        return _mesh_payload(obj.data)
    if obj.type == "CURVE":
        return _curve_payload(obj.data)
    if obj.type == "FONT":
        return _font_payload(obj.data)
    return None


def _modifier_payload(obj):
    result = []
    for modifier in obj.modifiers:
        item: dict[str, Any] = {"name": modifier.name, "type": modifier.type}
        for attr in ("width", "segments"):
            if hasattr(modifier, attr):
                value = getattr(modifier, attr)
                item[attr] = _q(value) if isinstance(value, float) else value
        result.append(item)
    return result


def _material_names(obj):
    if obj.data is None or not hasattr(obj.data, "materials"):
        return []
    return [slot.name if slot else None for slot in obj.data.materials]


def _custom_props(obj):
    result = {}
    for key in sorted(obj.keys()):
        if key == "_RNA_UI":
            continue
        value = obj[key]
        if isinstance(value, (bool, int, float, str)):
            result[key] = value
        elif isinstance(value, (list, tuple)):
            try:
                result[key] = [
                    _q(item) if isinstance(item, float) else item for item in value
                ]
            except TypeError:
                pass
    return result


def _transform_payload(obj):
    result = {
        "location": _vec(obj.location),
        "scale": _vec(obj.scale),
        "rotation_mode": obj.rotation_mode,
    }
    if obj.rotation_mode == "QUATERNION":
        result["rotation"] = _vec(obj.rotation_quaternion)
    else:
        result["rotation"] = _vec(obj.rotation_euler)
    return result


def object_static_payload(obj):
    return {
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "data": _data_payload(obj),
        "materials": _material_names(obj),
        "modifiers": _modifier_payload(obj),
        "custom": _custom_props(obj),
    }


def resolve_frames(frames_spec):
    scene = bpy.context.scene
    if frames_spec == "all":
        return list(range(scene.frame_start, scene.frame_end + 1))
    return [int(frame) for frame in frames_spec]


def protected_manifest(protected: dict[str, Any]) -> dict[str, Any]:
    object_patterns = list(protected.get("object_globs", []))
    animation_patterns = list(
        protected.get("animation_object_globs", object_patterns)
    )
    frames = resolve_frames(protected.get("frames", []))
    scene_keys = list(protected.get("scene_keys", []))

    objects = sorted(
        [obj for obj in bpy.data.objects if _matches(obj.name, object_patterns)],
        key=lambda obj: obj.name,
    )
    animation_objects = sorted(
        [obj for obj in bpy.data.objects if _matches(obj.name, animation_patterns)],
        key=lambda obj: obj.name,
    )

    static = {
        obj.name: object_static_payload(obj)
        for obj in objects
    }

    animation = {}
    scene = bpy.context.scene
    original_frame = scene.frame_current
    for frame in frames:
        scene.frame_set(frame)
        animation[str(frame)] = {
            obj.name: _transform_payload(obj)
            for obj in animation_objects
        }
    scene.frame_set(original_frame)

    scene_values = {
        key: scene.get(key)
        for key in scene_keys
    }

    payload = {
        "object_patterns": object_patterns,
        "animation_patterns": animation_patterns,
        "frames": frames,
        "scene": scene_values,
        "static": static,
        "animation": animation,
    }
    payload["static_hash"] = hashlib.sha256(
        json.dumps(
            {"scene": scene_values, "static": static},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    payload["animation_hash"] = hashlib.sha256(
        json.dumps(animation, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def world_payload():
    scene = bpy.context.scene
    if scene.world is None or not scene.world.use_nodes:
        return None
    background = scene.world.node_tree.nodes.get("Background")
    if background is None:
        return None
    return {
        "color": _vec(background.inputs["Color"].default_value),
        "strength": _q(background.inputs["Strength"].default_value),
    }


def camera_payload(camera_name: str | None = None):
    scene = bpy.context.scene
    camera = bpy.data.objects.get(camera_name) if camera_name else scene.camera
    if camera is None:
        return None
    result = {
        "name": camera.name,
        "type": camera.data.type,
        **_transform_payload(camera),
    }
    if camera.data.type == "ORTHO":
        result["ortho_scale"] = _q(camera.data.ortho_scale)
    else:
        result["lens"] = _q(camera.data.lens)
    return result


def light_payload(name: str):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "LIGHT":
        return None
    data = obj.data
    result = {
        "name": obj.name,
        "type": data.type,
        "color": _vec(data.color),
        "energy": _q(data.energy),
        "location": _vec(obj.location),
        "rotation": _vec(obj.rotation_euler),
    }
    if hasattr(data, "size"):
        result["size"] = _q(data.size)
    return result


def render_payload():
    scene = bpy.context.scene
    return {
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "resolution_percentage": scene.render.resolution_percentage,
        "fps": scene.render.fps,
        "fps_base": _q(scene.render.fps_base),
        "frame_range": [scene.frame_start, scene.frame_end],
        "engine": scene.render.engine,
    }
