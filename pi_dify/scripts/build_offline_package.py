from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_FILE = ROOT / "manifest.yaml"
LOCK_FILE = ROOT / "requirements.lock.txt"
WHEELS_DIR = ROOT / "wheels"
DIST_DIR = ROOT / "dist"
WORKBENCH_DIST = ROOT.parent / "pi_workbench" / "dist"

TARGET_PLATFORMS = {
    "amd64": ["manylinux_2_28_x86_64", "manylinux2014_x86_64"],
    "arm64": ["manylinux_2_28_aarch64", "manylinux2014_aarch64"],
}
ARCH_OUTPUT_SUFFIXES = {"all": "amd64-arm64", "amd64": "amd64", "arm64": "arm64"}
SKIP_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "tests",
    "scripts",
    "tmp_dify_official_plugins",
}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_manifest_identity() -> tuple[str, str]:
    plugin_name = plugin_version = None
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


def ensure_locked_wheels_exist(arch: str = "all") -> None:
    if not WHEELS_DIR.exists():
        raise RuntimeError(f"Missing wheels directory: {WHEELS_DIR}")
    locked = read_lock_requirements()
    available: dict[str, set[str]] = {}
    for wheel_path in WHEELS_DIR.glob("*.whl"):
        if not wheel_matches_arch(wheel_path.name, arch):
            continue
        name, version = read_wheel_identity(wheel_path)
        available.setdefault(normalize_name(name), set()).add(version)
    missing = [
        f"{name}=={version}"
        for name, version in sorted(locked.items())
        if version not in available.get(name, set())
    ]
    if missing:
        raise RuntimeError(
            "Missing offline wheels for locked requirements:\n"
            + "\n".join(f"  - {item}" for item in missing)
            + "\nRun scripts/download_offline_wheels.py --arch amd64 --arch arm64 first."
        )


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
    if relative_path.suffix in SKIP_SUFFIXES:
        return True
    if relative_path.parts and relative_path.parts[0] == "wheels":
        return not wheel_matches_arch(relative_path.name, arch)
    return False


def render_manifest(arch: str) -> str:
    text = MANIFEST_FILE.read_text(encoding="utf-8")
    if arch == "all":
        return text
    lines = text.splitlines()
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
        "Pi Agent's own source is distributed with the repository's license and notices; "
        "the bundled frontend retains the Leyline Apache-2.0 notice separately."
    )
    evidence = {
        "plugin": parse_manifest_identity()[0],
        "plugin_version": parse_manifest_identity()[1],
        "architecture": arch,
        "python": "3.12",
        "locked_requirements": locked,
        "wheels": wheels,
        "wheel_count": len(wheels),
        "static_frontend": _static_frontend_evidence(),
    }
    licenses["THIRD_PARTY_NOTICES.md"] = "\n".join(notices).encode("utf-8")
    return evidence, licenses


def _static_frontend_evidence() -> dict[str, object] | None:
    report = WORKBENCH_DIST / "static-report.json"
    if not report.exists():
        return None
    payload = json.loads(report.read_text(encoding="utf-8"))
    return {
        "file_count": payload.get("fileCount"),
        "total_bytes": payload.get("totalBytes"),
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "violations": payload.get("violations", []),
    }


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
                # Pin the packaged requirements to the verified lock; the target
                # must install exactly these versions from the bundled wheels.
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
    parser = argparse.ArgumentParser(description="Build an offline Pi Dify plugin package.")
    parser.add_argument("--output", type=Path, help="Optional output path.")
    parser.add_argument("--arch", choices=["all", *TARGET_PLATFORMS.keys()], default="all")
    args = parser.parse_args()
    ensure_locked_wheels_exist(args.arch)
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
