from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse
from urllib.request import urlopen

DEFAULT_CONFIG = Path("ci/version_matrix.yml")
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "ci-tools"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def parse_checksums(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) == 2:
            checksum, filename = parts
            mapping[filename] = checksum
    return mapping


def verify_checksum(artifact: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with artifact.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"Checksum mismatch for {artifact.name}: expected {expected}, got {actual}"
        )


def verify_sigstore(artifact: Path, config: Dict[str, str], workspace: Path) -> None:
    signature_path = workspace / "signature"
    certificate_path = workspace / "certificate"
    download(config["signature"], signature_path)
    download(config["certificate"], certificate_path)

    identity = config.get("identity_regexp")
    oidc = config.get("oidc_issuer", "https://token.actions.githubusercontent.com")

    command = [
        sys.executable,
        "-m",
        "sigstore",
        "verify",
        "identity",
        str(artifact),
        "--signature",
        str(signature_path),
        "--certificate",
        str(certificate_path),
    ]
    if identity:
        command.extend(["--certificate-identity-regexp", identity])
    if oidc:
        command.extend(["--certificate-oidc-issuer", oidc])

    subprocess.run(command, check=True)


def extract_member(archive: Path, member: str, workspace: Path) -> Path:
    with tarfile.open(archive, "r:gz") as tar:
        try:
            tarinfo = tar.getmember(member)
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(f"Member {member} not found in {archive}") from exc
        extracted_path = workspace / Path(tarinfo.name).name
        with tar.extractfile(tarinfo) as fileobj:
            if fileobj is None:  # pragma: no cover - defensive guard
                raise RuntimeError(f"Unable to extract member {member} from {archive}")
            extracted_path.write_bytes(fileobj.read())
        extracted_path.chmod(0o755)
    return extracted_path


def ensure_tool(
    name: str, config: Dict[str, object], cache_dir: Path, bin_dir: Path
) -> None:
    version = str(config["version"])
    binary_name = str(config["binary"])
    tool_cache = cache_dir / name / version
    cached_binary = tool_cache / binary_name

    bin_dir.mkdir(parents=True, exist_ok=True)
    tool_cache.mkdir(parents=True, exist_ok=True)

    if cached_binary.exists():
        destination = bin_dir / binary_name
        shutil.copy2(cached_binary, destination)
        destination.chmod(0o755)
        return

    artifact_url = str(config["artifact"]).format(version=version)
    artifact_name = Path(urlparse(artifact_url).path).name or f"{name}-{version}"

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        artifact_path = workspace / artifact_name
        download(artifact_url, artifact_path)

        if "checksums" in config:
            checksums = config["checksums"]
            checksum_url = str(checksums["url"]).format(version=version)
            checksum_path = workspace / "checksums.txt"
            download(checksum_url, checksum_path)
            mapping = parse_checksums(checksum_path)
            pattern = str(checksums["pattern"]).format(version=version)
            if pattern not in mapping:
                raise RuntimeError(
                    f"Checksum for {pattern} not found in {checksum_url}"
                )
            verify_checksum(artifact_path, mapping[pattern])
        elif "sha256" in config:
            verify_checksum(artifact_path, str(config["sha256"]))
        else:
            raise RuntimeError(f"No checksum data configured for tool {name}")

        if "sigstore" in config:
            verify_sigstore(artifact_path, config["sigstore"], workspace)

        if "extract" in config:
            member = str(config["extract"]["member"])
            extracted = extract_member(artifact_path, member, workspace)
            source = extracted
        else:
            source = artifact_path

        destination = tool_cache / binary_name
        shutil.copy2(source, destination)
        destination.chmod(0o755)

    final_path = bin_dir / binary_name
    shutil.copy2(destination, final_path)
    final_path.chmod(0o755)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download, verify, and cache CI tooling"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the tool configuration file",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Directory used to cache verified tool binaries",
    )
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=DEFAULT_BIN_DIR,
        help="Directory where executables should be installed",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    tools = config.get("tools", {})
    if not tools:
        print("No tools defined in configuration", file=sys.stderr)
        return 1

    for name, tool_config in tools.items():
        ensure_tool(name, tool_config, args.cache_dir, args.bin_dir)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
