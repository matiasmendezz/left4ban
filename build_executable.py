#!/usr/bin/env python3
"""
Left4Ban Standalone Executable Builder
Packages Left4Ban into a single self-contained executable for Windows or Linux.
"""

import os
import sys
import PyInstaller.__main__


def build():
    print("=" * 60)
    print("  Left 4 Ban — Standalone Single-File Executable Builder")
    print("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(base_dir, "app.py")
    templates_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    path_sep = ";" if sys.platform.startswith("win") else ":"

    args = [
        app_path,
        "--name=Left4Ban",
        "--onefile",
        "--clean",
        "--noconfirm",
        f"--add-data={templates_dir}{path_sep}templates",
        f"--add-data={static_dir}{path_sep}static",
        "--collect-all=DrissionPage",
        "--hidden-import=cloudscraper",
        "--hidden-import=bs4",
        "--hidden-import=lxml",
    ]

    print(f"Platform: {sys.platform}")
    print(f"Data separator: '{path_sep}'")
    print(f"Running PyInstaller...")

    PyInstaller.__main__.run(args)

    output_name = "Left4Ban.exe" if sys.platform.startswith("win") else "Left4Ban"
    dist_bin = os.path.join(base_dir, "dist", output_name)

    if os.path.exists(dist_bin):
        size_mb = os.path.getsize(dist_bin) / (1024 * 1024)
        print("=" * 60)
        print(f"SUCCESS: Binary generated at: {dist_bin} ({size_mb:.2f} MB)")
        print("=" * 60)
    else:
        print(f"WARNING: Output binary was not found at {dist_bin}")


if __name__ == "__main__":
    build()
