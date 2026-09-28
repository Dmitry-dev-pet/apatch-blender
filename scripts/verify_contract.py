from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from apatch_blender.verifier import verify_contract_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--root", default=str(REPO_ROOT))
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])

    result = verify_contract_file(args.contract, args.root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
