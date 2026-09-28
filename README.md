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
- `animate_camera_path`
- `set_camera_dof`
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


## APatch-governed execution

The JSON file can run in legacy standalone mode, but it can also be treated as a
**derived Blender execution plan** whose authority comes from a live APatch SDD
session.

Add a governance binding to the plan:

```json
{
  "governance": {
    "mode": "apatch_sdd",
    "requirement": "SPEC-COIMBRA-1#R1"
  }
}
```

Then ask the bridge what the APatch task envelope must authorize:

```bash
python scripts/describe_apatch_scope.py \
  --contract contracts/coimbra-003-slow.json \
  --root "$PWD"
```

The output contains:

- the exact `SPEC#Rk` requirement;
- `allowed_writes` for the edited `.blend` and evidence artifacts;
- exact Blender operation tool ids such as `apatch_blender:animate_camera_path`;
- a `checks` entry containing `apatch-blender-plan:sha256:<hash>`.

Before Blender mutates anything, `apatch-blender` requires an active APatch
implementation session that:

1. is anchored to the exact `spec:SPEC#Rk@<content-hash>` artifact;
2. carries an SDD task envelope for the same requirement;
3. contains the exact Blender plan hash;
4. admits every requested Blender operation;
5. admits every output path.

The executor embeds the APatch session id, requirement, envelope hash, and plan
hash into the edited scene. The independent verifier checks that binding in
addition to protected semantic state.

This keeps the authority chain:

```text
APatch SPEC#Rk
    |
frozen task envelope + governed session
    |
hash-bound Blender execution plan
    |
apatch-blender executor
    |
edited .blend
    |
semantic verifier
    |
APatch verification / attestation
```

Install the optional APatch runtime in the Python environment visible to Blender:

```bash
python -m pip install -e ".[apatch]"
```

As with APatch itself, this is mediated enforcement rather than sealed
containment: a process with unrestricted out-of-band filesystem access can still
bypass the bridge.

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


### Camera paths

`animate_camera_path` accepts explicit frame/location/target keyframes. The generic verifier can independently assert those checkpoints through `expected.camera_path`, so cinematic camera motion remains contract data rather than arbitrary Blender Python.


### Camera depth of field

`set_camera_dof` is a bounded visual-development operation for camera depth of
field. It can enable DOF, set the aperture f-stop, set a fixed focus distance,
or keyframe focus distance over the existing camera path. Contracts can assert
the same values through `expected.camera_dof`, so miniature/tilt-shift-like
looks remain independently verifiable rather than arbitrary Blender Python.
