from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector


class OperationError(RuntimeError):
    pass


def _vector(value: Any, size: int, field: str):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise OperationError(f"{field} must contain exactly {size} numbers")
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise OperationError(f"{field} must contain numbers") from exc


def _object(name: str):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise OperationError(f"Blender object not found: {name}")
    return obj


def _material(name: str):
    material = bpy.data.materials.get(name)
    if material is None:
        raise OperationError(f"Blender material not found: {name}")
    return material


def set_world(params: dict[str, Any], root: Path) -> dict[str, Any]:
    scene = bpy.context.scene
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is None:
        raise OperationError("World Background node is missing")

    before = {
        "color": list(background.inputs["Color"].default_value),
        "strength": float(background.inputs["Strength"].default_value),
    }

    if "color" in params:
        background.inputs["Color"].default_value = _vector(
            params["color"], 4, "set_world.color"
        )
    if "strength" in params:
        background.inputs["Strength"].default_value = float(params["strength"])

    return {
        "before": before,
        "after": {
            "color": list(background.inputs["Color"].default_value),
            "strength": float(background.inputs["Strength"].default_value),
        },
    }


def scale_camera_framing(params: dict[str, Any], root: Path) -> dict[str, Any]:
    scene = bpy.context.scene
    camera_name = str(params.get("camera", scene.camera.name if scene.camera else "Camera"))
    camera = _object(camera_name)
    factor = float(params["factor"])
    if factor <= 0:
        raise OperationError("scale_camera_framing.factor must be > 0")

    before = {
        "type": camera.data.type,
        "location": list(camera.location),
        "rotation": list(camera.rotation_euler),
    }

    if camera.data.type == "ORTHO":
        before["ortho_scale"] = float(camera.data.ortho_scale)
        camera.data.ortho_scale *= factor
        after_value = float(camera.data.ortho_scale)
        mode = "ortho_scale"
    else:
        # For perspective cameras, move along the view ray while preserving
        # rotation. A factor < 1 moves the camera closer to target.
        target = _vector(params.get("target", (0.0, 0.0, 0.0)), 3, "target")
        target_v = Vector(target)
        before_distance = (camera.location - target_v).length
        camera.location = target_v + (camera.location - target_v) * factor
        after_value = (camera.location - target_v).length
        before["distance_to_target"] = before_distance
        mode = "distance"

    return {
        "mode": mode,
        "factor": factor,
        "before": before,
        "after_value": after_value,
        "location": list(camera.location),
        "rotation": list(camera.rotation_euler),
    }


def add_area_light(params: dict[str, Any], root: Path) -> dict[str, Any]:
    name = str(params["name"])
    if bpy.data.objects.get(name) is not None:
        raise OperationError(f"Object already exists: {name}")

    data = bpy.data.lights.new(name=name, type="AREA")
    data.color = _vector(params["color"], 3, "add_area_light.color")
    data.energy = float(params["energy"])
    data.size = float(params.get("size", 1.0))
    data.shape = str(params.get("shape", "DISK"))

    light = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(light)
    light.location = _vector(params["location"], 3, "add_area_light.location")

    target = Vector(
        _vector(params.get("target", (0.0, 0.0, 0.0)), 3, "add_area_light.target")
    )
    direction = target - light.location
    light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    return {
        "name": name,
        "type": "AREA",
        "color": list(data.color),
        "energy": float(data.energy),
        "size": float(data.size),
        "location": list(light.location),
        "rotation": list(light.rotation_euler),
    }


def set_material(params: dict[str, Any], root: Path) -> dict[str, Any]:
    material = _material(str(params["material"]))
    before = {
        "diffuse_color": list(material.diffuse_color),
        "use_nodes": bool(material.use_nodes),
    }

    if "base_color" in params:
        color = _vector(params["base_color"], 4, "set_material.base_color")
        material.diffuse_color = color
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = color

    if "roughness" in params:
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Roughness"].default_value = float(params["roughness"])

    return {
        "material": material.name,
        "before": before,
        "after": {
            "diffuse_color": list(material.diffuse_color),
            "use_nodes": bool(material.use_nodes),
        },
    }


def set_transform(params: dict[str, Any], root: Path) -> dict[str, Any]:
    obj = _object(str(params["object"]))
    before = {
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
    }

    if "location" in params:
        obj.location = _vector(params["location"], 3, "set_transform.location")
    if "rotation_euler" in params:
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = _vector(
            params["rotation_euler"], 3, "set_transform.rotation_euler"
        )
    if "scale" in params:
        obj.scale = _vector(params["scale"], 3, "set_transform.scale")

    return {
        "object": obj.name,
        "before": before,
        "after": {
            "location": list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale": list(obj.scale),
        },
    }


def set_render(params: dict[str, Any], root: Path) -> dict[str, Any]:
    scene = bpy.context.scene
    before = {
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "fps": scene.render.fps,
        "frame_range": [scene.frame_start, scene.frame_end],
    }

    if "resolution" in params:
        width, height = _vector(params["resolution"], 2, "set_render.resolution")
        scene.render.resolution_x = int(width)
        scene.render.resolution_y = int(height)
        scene.render.resolution_percentage = int(params.get("resolution_percentage", 100))
    if "fps" in params:
        scene.render.fps = int(params["fps"])
        scene.render.fps_base = 1.0
    if "frame_start" in params:
        scene.frame_start = int(params["frame_start"])
    if "frame_end" in params:
        scene.frame_end = int(params["frame_end"])

    return {
        "before": before,
        "after": {
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "fps": scene.render.fps,
            "frame_range": [scene.frame_start, scene.frame_end],
        },
    }


def render_preview(params: dict[str, Any], root: Path) -> dict[str, Any]:
    scene = bpy.context.scene
    frame = int(params.get("frame", scene.frame_start))
    output = (root / str(params["path"])).resolve()
    try:
        output.relative_to(root.resolve())
    except ValueError as exc:
        raise OperationError("render_preview.path escapes workspace root") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    scene.frame_set(frame)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)

    return {
        "frame": frame,
        "path": str(output),
        "exists": output.exists(),
        "size": output.stat().st_size if output.exists() else 0,
    }


OPERATIONS: dict[str, Callable[[dict[str, Any], Path], dict[str, Any]]] = {
    "set_world": set_world,
    "scale_camera_framing": scale_camera_framing,
    "add_area_light": add_area_light,
    "set_material": set_material,
    "set_transform": set_transform,
    "set_render": set_render,
    "render_preview": render_preview,
}


def execute_operation(name: str, params: dict[str, Any], root: Path) -> dict[str, Any]:
    handler = OPERATIONS.get(name)
    if handler is None:
        raise OperationError(f"Unsupported operation: {name}")
    return handler(params, root)
