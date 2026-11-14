#!/usr/bin/env python3
"""Build the arika_backend cdylib and copy it next to arika_backend.py."""
import shutil
import filecmp
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    subprocess.run(["cargo", "build", "--release"], cwd=root, check=True)

    if sys.platform == "win32":
        src = root / "target" / "release" / "arika_backend.dll"
        name = "arika_backend.dll"
    elif sys.platform == "darwin":
        src = root / "target" / "release" / "libarika_backend.dylib"
        name = "libarika_backend.dylib"
    else:
        src = root / "target" / "release" / "libarika_backend.so"
        name = "libarika_backend.so"

    if not src.exists():
        print(f"error: expected shared library at {src}", file=sys.stderr)
        return 1

    dst = root / name
    if dst.exists() and filecmp.cmp(src, dst, shallow=False):
        print(f"backend already current: {dst}")
        return 0

    shutil.copy2(src, dst)
    print(f"copied {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
