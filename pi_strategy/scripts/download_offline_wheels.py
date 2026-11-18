from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = ROOT / "requirements.lock.txt"
WHEELS_DIR = ROOT / "wheels"

TARGET_PLATFORMS = {
    "amd64": ["manylinux_2_28_x86_64", "manylinux2014_x86_64"],
    "arm64": ["manylinux_2_28_aarch64", "manylinux2014_aarch64"],
}


def build_command(platforms: list[str], index_url: str | None) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--requirement",
        str(LOCK_FILE),
        "--dest",
        str(WHEELS_DIR),
        "--only-binary=:all:",
        "--timeout",
        "120",
        "--retries",
        "5",
        "--implementation",
        "cp",
        "--python-version",
        "3.12",
        "--abi",
        "cp312",
    ]
    for platform in platforms:
        command.extend(["--platform", platform])
    if index_url:
        command.extend(["--index-url", index_url])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Linux Python 3.12 wheels for the Pi Dify plugin."
    )
    parser.add_argument(
        "--arch",
        choices=["all", *TARGET_PLATFORMS.keys()],
        default="all",
        help="Target architecture to download. Defaults to both.",
    )
    parser.add_argument("--index-url", help="Optional package index mirror.")
    args = parser.parse_args()
    WHEELS_DIR.mkdir(parents=True, exist_ok=True)
    arches = TARGET_PLATFORMS.keys() if args.arch == "all" else [args.arch]
    for arch in arches:
        command = build_command(TARGET_PLATFORMS[arch], args.index_url)
        print(f"Downloading wheels for {arch} ({', '.join(TARGET_PLATFORMS[arch])})")
        subprocess.run(command, cwd=ROOT, check=True)
    print(f"Wheels downloaded to: {WHEELS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
