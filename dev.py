"""Development commands using only the Python standard library."""

import argparse
import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run, test or inspect BombCat.")
    parser.add_argument("task", nargs="?", default="run", choices=("run", "test", "check", "arena"))
    args, remaining = parser.parse_known_args(argv)
    if args.task == "run":
        command = [sys.executable, str(ROOT / "main.py"), *remaining]
    elif args.task == "test":
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v", *remaining]
    elif args.task == "arena":
        command = [sys.executable, str(ROOT / "arena.py"), *remaining]
    else:
        if remaining:
            parser.error("check does not accept extra arguments")
        files = [*ROOT.glob("*.py"), *ROOT.joinpath("tests").glob("*.py")]
        for path in files:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        print(f"Checked {len(files)} Python files.")
        return 0
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
