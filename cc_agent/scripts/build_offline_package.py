from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_FILE = ROOT / "manifest.yaml"
LOCK_FILE = ROOT / "requirements.lock.txt"
WHEELS_DIR = ROOT / "wheels"
DIST_DIR = ROOT / "dist"

TARGET_PLATFORMS = {
    "amd64": ["manylinux_2_28_x86_64", "manylinux2014_x86_64"],
    "arm64": ["manylinux_2_28_aarch64", "manylinux2014_aarch64"],
}
ARCH_OUTPUT_SUFFIXES = {"all": "amd64-arm64", "amd64": "amd64", "arm64": "arm64"}

SKIP_NAMES = {
    ".scratch",
    ".env",
    ".env.example",
    ".git",
    ".venv",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "__pycache__",
    "dist",
    "tmp_dify_official_plugins",
}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_manifest_identity() -> tuple[str, str]:
    plugin_name: str | None = None
    plugin_version: str | None = None

    for raw_line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith((" ", "\t")):
            continue
        key, _, value = raw_line.partition(":")
        if not value:
            continue
        value = value.strip().strip('"').strip("'")
        if key == "name" and plugin_name is None:
            plugin_name = value
        elif key == "version" and plugin_version is None:
            plugin_version = value

    if not plugin_name or not plugin_version:
        raise RuntimeError("Failed to parse plugin name/version from manifest.yaml")

    return plugin_name, plugin_version


def read_lock_requirements() -> dict[str, str]:
    requirements: dict[str, str] = {}

    for raw_line in LOCK_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name, sep, version = line.partition("==")
        if not sep or not version:
            raise RuntimeError(f"Unsupported requirement format: {raw_line}")
        requirements[normalize_name(name)] = version.strip()

    return requirements


def read_wheel_identity(wheel_path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_path = next(
            (name for name in archive.namelist() if name.endswith(".dist-info/METADATA")), None
        )
        if metadata_path is None:
            raise RuntimeError(f"Missing METADATA in wheel: {wheel_path.name}")
        metadata = Parser().parsestr(archive.read(metadata_path).decode("utf-8", errors="replace"))
        return metadata["Name"], metadata["Version"]


def read_available_wheels() -> dict[str, set[str]]:
    available: dict[str, set[str]] = {}
    for wheel_path in WHEELS_DIR.glob("*.whl"):
        name, version = read_wheel_identity(wheel_path)
        available.setdefault(normalize_name(name), set()).add(version)
    return available


def ensure_locked_wheels_exist() -> None:
    if not WHEELS_DIR.exists():
        raise RuntimeError(f"Missing wheels directory: {WHEELS_DIR}")

    locked = read_lock_requirements()
    available = read_available_wheels()

    missing = []
    for name, version in sorted(locked.items()):
        versions = available.get(name, set())
        if version not in versions:
            missing.append(f"{name}=={version}")

    if missing:
        missing_text = "\n".join(f"  - {item}" for item in missing)
        raise RuntimeError(
            "Missing offline wheels for locked requirements:\n"
            f"{missing_text}\n"
            "Run scripts/download_offline_wheels.py on a machine that can reach your package index."
        )


def selected_arches(arch: str) -> list[str]:
    return list(TARGET_PLATFORMS) if arch == "all" else [arch]


def verify_offline_resolution(arch: str) -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for target_arch in selected_arches(arch):
        platforms = TARGET_PLATFORMS[target_arch]
        with tempfile.TemporaryDirectory(
            prefix=f"offline-resolution-{target_arch}-", dir=DIST_DIR
        ) as temp_dir:
            command = [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--no-index",
                "--find-links",
                str(WHEELS_DIR),
                "--requirement",
                str(LOCK_FILE),
                "--dest",
                temp_dir,
                "--only-binary=:all:",
                "--implementation",
                "cp",
                "--python-version",
                "3.12",
                "--abi",
                "cp312",
            ]
            for platform in platforms:
                command.extend(["--platform", platform])
            print(
                f"Verifying offline dependency resolution for {target_arch} ({', '.join(platforms)})"
            )
            subprocess.run(command, cwd=ROOT, check=True)


def wheel_matches_arch(wheel_name: str, arch: str) -> bool:
    if arch == "all" or "none-any" in wheel_name:
        return True
    if "x86_64" in wheel_name:
        return arch == "amd64"
    if "aarch64" in wheel_name:
        return arch == "arm64"
    return False


def should_skip(relative_path: Path, arch: str) -> bool:
    if any(part in SKIP_NAMES for part in relative_path.parts):
        return True
    if relative_path.parts and relative_path.parts[0].startswith("tmp_"):
        return True
    if relative_path.suffix in SKIP_SUFFIXES:
        return True
    if relative_path.parts and relative_path.parts[0] == "wheels":
        return not wheel_matches_arch(relative_path.name, arch)
    return False


def render_manifest(arch: str) -> str:
    manifest_text = MANIFEST_FILE.read_text(encoding="utf-8")
    if arch == "all":
        return manifest_text

    lines = manifest_text.splitlines()
    rendered: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "arch:":
            indent = line[: len(line) - len(line.lstrip())]
            item_indent = f"{indent}  "
            rendered.append(line)
            rendered.append(f"{item_indent}- {arch}")
            i += 1
            while i < len(lines) and lines[i].startswith(item_indent):
                i += 1
            continue
        rendered.append(line)
        i += 1

    return "\n".join(rendered) + "\n"


def wheel_metadata(wheel_path: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_path = next(
            (name for name in archive.namelist() if name.endswith(".dist-info/METADATA")), None
        )
        if metadata_path is None:
            raise RuntimeError(f"Missing METADATA in wheel: {wheel_path.name}")
        raw = archive.read(metadata_path).decode("utf-8", errors="replace")
        metadata = Parser().parsestr(raw)
        licenses: list[tuple[str, bytes]] = []
        prefix = metadata_path[: -len("METADATA")]
        for name in archive.namelist():
            if not name.startswith(prefix):
                continue
            tail = name[len(prefix) :]
            if (
                tail.startswith("licenses/") or tail.upper().startswith("LICENSE")
            ) and not tail.endswith("/"):
                licenses.append((tail, archive.read(name)))
        return {
            "name": metadata["Name"],
            "version": metadata["Version"],
            "license": metadata.get("License-Expression") or metadata.get("License") or "",
            "home": metadata.get("Home-page") or "",
            "licenses": licenses,
        }


def build_evidence(arch: str) -> tuple[dict[str, object], dict[str, bytes]]:
    locked = read_lock_requirements()
    wheels = []
    licenses: dict[str, bytes] = {}
    notices = [
        "# Third-party notices",
        "",
        "This offline Dify plugin package bundles the following Python distributions.",
        "Each row records the exact version; license texts are included under LICENSES/.",
        "",
        "| Package | Version | License |",
        "| --- | --- | --- |",
    ]
    for wheel_path in sorted(WHEELS_DIR.glob("*.whl")):
        if not wheel_matches_arch(wheel_path.name, arch):
            continue
        meta = wheel_metadata(wheel_path)
        name = str(meta["name"])
        version = str(meta["version"])
        wheel_hash = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
        wheels.append(
            {
                "name": name,
                "version": version,
                "file": wheel_path.name,
                "sha256": wheel_hash,
                "license": meta["license"],
            }
        )
        notices.append(f"| {name} | {version} | {meta['license'] or 'see LICENSES/'} |")
        for license_name, content in meta["licenses"]:
            key = f"LICENSES/{normalize_name(name)}-{version}/{license_name}"
            licenses[key] = content
    notices.append("")
    notices.append(
        "CC Agent's own source is distributed with the repository's license and notices; "
        "it has no bundled frontend."
    )
    evidence = {
        "plugin": parse_manifest_identity()[0],
        "plugin_version": parse_manifest_identity()[1],
        "architecture": arch,
        "python": "3.12",
        "locked_requirements": locked,
        "wheels": wheels,
        "wheel_count": len(wheels),
        "frontend": "none (no frontend is bundled; AG-UI consumers live outside the package)",
    }
    licenses["THIRD_PARTY_NOTICES.md"] = "\n".join(notices).encode("utf-8")
    return evidence, licenses


def build_package(output_path: Path, arch: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    evidence, licenses = build_evidence(arch)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(ROOT.rglob("*")):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(ROOT)
            if should_skip(relative_path, arch):
                continue
            if relative_path == Path("manifest.yaml"):
                archive.writestr("manifest.yaml", render_manifest(arch))
                continue
            if relative_path == Path("requirements.txt"):
                # Pin the packaged requirements to the verified lock and force
                # dependency resolution from the bundled wheels: the plugin
                # daemon runs `uv pip install -r requirements.txt` in the
                # extracted package directory, so without these directives an
                # install reaches PyPI and is not offline.
                archive.writestr(
                    "requirements.txt",
                    "--no-index\n--find-links ./wheels\n" + LOCK_FILE.read_text(encoding="utf-8"),
                )
                continue
            archive.write(file_path, arcname=relative_path.as_posix())
        archive.writestr("VERSION_MANIFEST.json", json.dumps(evidence, indent=2, sort_keys=True))
        for name, content in licenses.items():
            archive.writestr(name, content)

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an offline-installable Dify plugin package."
    )
    parser.add_argument(
        "--output", type=Path, help="Optional output path for the .difypkg artifact."
    )
    parser.add_argument(
        "--arch",
        choices=["all", *TARGET_PLATFORMS.keys()],
        default="all",
        help="Target architecture to package. Defaults to all supported architectures.",
    )
    args = parser.parse_args()

    ensure_locked_wheels_exist()
    verify_offline_resolution(args.arch)
    plugin_name, plugin_version = parse_manifest_identity()
    default_name = (
        f"{plugin_name}-{plugin_version}-offline-linux-{ARCH_OUTPUT_SUFFIXES[args.arch]}.difypkg"
    )
    output_path = args.output or (DIST_DIR / default_name)
    output_path = output_path if output_path.is_absolute() else ROOT / output_path

    artifact = build_package(output_path, args.arch)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    print(
        json.dumps(
            {"artifact": str(artifact), "sha256": digest, "bytes": artifact.stat().st_size},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
