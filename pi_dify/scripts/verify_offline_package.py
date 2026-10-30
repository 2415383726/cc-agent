from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = ROOT / "requirements.lock.txt"
SMOKE = ROOT / "scripts" / "offline_smoke.py"

PLATFORM = {"amd64": "x86_64-unknown-linux-gnu", "arm64": "aarch64-unknown-linux-gnu"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(package: Path, destination: Path) -> Path:
    with zipfile.ZipFile(package) as archive:
        archive.extractall(destination)
    return destination


def run(
    command: list[str], *, cwd: Path, timeout: int = 600, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    print("+", " ".join(command))
    try:
        return subprocess.run(
            command, cwd=cwd, check=True, text=True, capture_output=True, timeout=timeout, env=env
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stdout)
        print(exc.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an offline Pi Dify plugin package.")
    parser.add_argument("package", type=Path)
    parser.add_argument("--arch", choices=["amd64", "arm64"], required=True)
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="Only resolve wheels for the target platform (used when the architecture cannot execute here).",
    )
    parser.add_argument("--output", type=Path, help="Optional evidence JSON path.")
    args = parser.parse_args()
    package = args.package.resolve()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"pi-offline-{args.arch}-") as temp:
        root = extract(package, Path(temp) / "plugin")
        version = json.loads((root / "VERSION_MANIFEST.json").read_text(encoding="utf-8"))
        wheel_count = len(list((root / "wheels").glob("*.whl")))
        evidence: dict[str, object] = {
            "package": package.name,
            "package_sha256": sha256(package),
            "package_bytes": package.stat().st_size,
            "arch": args.arch,
            "wheel_count": wheel_count,
            "version_manifest": version,
        }
        if args.resolve_only:
            venv = Path(temp) / "venv"
            run(["uv", "venv", "--python", "3.12", str(venv)], cwd=root)
            resolution = run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(venv / "bin" / "python"),
                    "--dry-run",
                    "--no-index",
                    "--find-links",
                    str(root / "wheels"),
                    "--python-platform",
                    PLATFORM[args.arch],
                    "--requirement",
                    str(root / "requirements.lock.txt"),
                ],
                cwd=root,
            )
            evidence["resolution_only"] = True
            output = f"{resolution.stdout}\n{resolution.stderr}"
            evidence["resolution_ok"] = bool(output.strip())
            evidence["resolution_output_tail"] = output.replace(str(root), "<plugin>").replace(
                temp, "<tmp>"
            )[-2_000:]
        else:
            venv = Path(temp) / "venv"
            run(["uv", "venv", "--python", "3.12", str(venv)], cwd=root)
            install_started = time.monotonic()
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(venv / "bin" / "python"),
                    "--no-index",
                    "--find-links",
                    str(root / "wheels"),
                    "--requirement",
                    str(root / "requirements.lock.txt"),
                ],
                cwd=root,
            )
            evidence["install_seconds"] = round(time.monotonic() - install_started, 2)
            import os

            smoke = run(
                [str(venv / "bin" / "python"), str(SMOKE)],
                cwd=root,
                env={**os.environ, "PYTHONPATH": str(root)},
            )
            evidence["smoke"] = json.loads(smoke.stdout.strip().splitlines()[-1])
            evidence["python"] = run(
                [str(venv / "bin" / "python"), "-c", "import sys; print(sys.version)"], cwd=root
            ).stdout.strip()
            evidence["offline"] = True
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 2)
        print(json.dumps(evidence, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
