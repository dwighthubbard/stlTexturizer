"""Refresh the BeeWare app's bundled web assets."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBROOT = ROOT / "src" / "bumpmesh_native" / "webroot"

FILES = [
    "index.html",
    "style.css",
    "logo.png",
    "pyscript.json",
]

DIRS = [
    "assets",
    "textures",
    "js",
    "pyscript_app",
]


def main():
    WEBROOT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(ROOT / name, WEBROOT / name)
    for name in DIRS:
        dst = WEBROOT / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(ROOT / name, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


if __name__ == "__main__":
    main()
