# AGENTS.md

This repository contains the generic APatch Blender bridge.

## Authority model

Contracts define the allowed Blender operations. The executor must reject operations that are not explicitly listed in `allowed_operations`.

## Core files

- `src/apatch_blender/contracts.py` — contract validation and path confinement.
- `src/apatch_blender/ops.py` — bounded Blender operation implementations.
- `src/apatch_blender/executor.py` — applies a validated plan to a base `.blend`.
- `src/apatch_blender/manifest.py` — semantic protected-state snapshots.
- `src/apatch_blender/verifier.py` — independently re-opens base and edited scenes and verifies protected state + expected effects.

## Security / governance boundary

Do not add a generic arbitrary-Python operation. New capabilities must be explicit named operations with bounded parameters and corresponding verifier support.

Do not let an execution plan rewrite or bypass the verifier. Protected selectors and expected effects are human-owned contract data.

All contract-relative paths are confined to the declared workspace root.


## APatch SDD integration

For contracts with `governance.mode = "apatch_sdd"`, the JSON contract is a
derived execution plan, not the authority source.

The executor must fail closed unless the live APatch session is bound to the
same `SPEC#Rk`, exact plan SHA-256, operation tool ids, and output write-set.
Keep APatch admission before any filesystem or Blender mutation.

Do not replace APatch's `admit_session_effect` policy with a local duplicate.
Do not weaken the plan-hash check or silently fall back to standalone execution.
The verifier must keep checking the APatch binding embedded in the edited scene.
