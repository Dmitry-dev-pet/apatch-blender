# APatch Blender

**Contract-governed Blender automation.**

APatch Blender is a small bridge between AI agents and Blender. Instead of exposing arbitrary `bpy` execution as the product interface, it executes explicit named operations under a contract and independently verifies the resulting `.blend`.

## Why

Typical agent-to-Blender integrations answer:

> What can the agent do?

APatch Blender adds a second question:

> What was the agent actually authorized to change, and can we prove it changed nothing else?

The runtime therefore separates:

```text
human contract
      |
validated operation plan
      |
bounded Blender operations
      |
edited .blend
      |
base vs edited semantic verifier
      |
PASS / FAIL + evidence
```

## v0.1 operations

- `set_world`
- `scale_camera_framing`
- `add_area_light`
- `set_material`
- `set_transform`
- `set_render`
- `render_preview`

There is intentionally **no arbitrary Python operation**.

## Contract shape

```json
{
  "schema_version": 1,
  "id": "EXAMPLE-001",
  "base_scene": "input/base.blend",
  "output_scene": "output/edited.blend",
  "allowed_operations": [
    "set_world",
    "scale_camera_framing",
    "add_area_light"
  ],
  "operations": [
    {
      "op": "set_world",
      "params": {
        "color": [0.0025, 0.006, 0.018, 1.0],
        "strength": 0.1
      }
    }
  ],
  "protected": {
    "object_globs": ["City*", "Road*", "Building*"],
    "animation_object_globs": ["City*", "Road*", "Building*"],
    "frames": "all",
    "scene_keys": []
  },
  "expected": {
    "world": {
      "color": [0.0025, 0.006, 0.018, 1.0],
      "strength": 0.1
    }
  }
}
```

## Blender execution

```bash
blender --background --factory-startup \
  --python scripts/execute_contract.py -- \
  --contract contracts/example.json \
  --root "$PWD"

blender --background --factory-startup \
  --python scripts/verify_contract.py -- \
  --contract contracts/example.json \
  --root "$PWD"
```

The executor opens the base scene itself. The verifier independently re-opens the base and edited scenes and computes protected semantic manifests.

## Semantic verification

Protected state can include:

- mesh vertices and polygon topology;
- curves and text geometry;
- object hierarchy;
- material assignments;
- modifiers;
- custom properties;
- transforms at selected frames or **every frame**;
- selected scene metadata.

The verifier emits separate static and animation SHA-256 hashes, making protected-state equality explicit evidence.

## Current integration

The first consumer is `Dmitry-dev-pet/apatch-blender-demo`, where the existing Rubik `R U R' U'` scene is being migrated from a one-off edit script to this generic bridge.

The next target is a larger scene such as Coimbra, where contracts can protect city geometry while allowing camera, lighting, atmosphere, and render changes.
