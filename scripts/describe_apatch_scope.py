from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from apatch_blender.contracts import load_contract
from apatch_blender.governance import required_apatch_scope


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Describe the APatch task-envelope scope required by a Blender plan."
    )
    parser.add_argument("--contract", required=True)
    parser.add_argument("--root", default=str(REPO_ROOT))
    args = parser.parse_args()

    contract = load_contract(args.contract)
    scope = required_apatch_scope(contract, args.root)
    print(json.dumps(scope, indent=2))


if __name__ == "__main__":
    main()
