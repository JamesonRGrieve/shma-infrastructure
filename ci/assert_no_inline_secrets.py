from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:  # pragma: no cover - CLI fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import yaml
else:  # pragma: no cover - package import
    import yaml


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
        raise ValueError(f"Failed to parse YAML file {path}: {exc}") from exc


def _register_secret(secrets: set[str], raw_value: str | None) -> None:
    if not raw_value:
        return

    text = str(raw_value)
    if text:
        secrets.add(text)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                secrets.add(stripped)


def gather_secret_values(service: dict) -> set[str]:
    secrets: set[str] = set()
    secret_block = service.get("secrets", {})

    def _collect_candidates(item: dict) -> set[str]:
        candidates: set[str] = set()
        for field in ("value", "content"):
            value = item.get(field)
            if value:
                candidates.add(str(value))
        return candidates

    for item in secret_block.get("env", []) or []:
        _register_secret(secrets, item.get("value"))

    for item in secret_block.get("files", []) or []:
        _register_secret(secrets, item.get("value"))
        _register_secret(secrets, item.get("content"))

    return secrets


def _extract_quadlet_entries(content: str) -> tuple[set[str], set[str]]:
    entries: set[str] = set()
    paths: set[str] = set()

    for line in content.splitlines():
        key, _, value = line.partition("=")
        if not value:
            continue
        key = key.strip()
        value = value.strip()
        if key in {"Environment", "EnvironmentFile", "Volume"}:
            if value:
                entries.add(value)
        if key in {"EnvironmentFile", "Volume"}:
            host_path, _, _ = value.partition(":")
            host_path = host_path.strip()
            if host_path:
                paths.add(host_path)

    return entries, paths


def check_manifest(manifest_path: Path, secrets: set[str]) -> list[str]:
    content = manifest_path.read_text()
    found: set[str] = set()

    for secret in secrets:
        if secret and secret in content:
            found.add(secret)

    if "[Container]" in content and "[Service]" in content:
        entries, paths = _extract_quadlet_entries(content)
        for candidate in entries.union(paths):
            for secret in secrets:
                if secret and secret in candidate:
                    found.add(secret)

    return sorted(found)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensure rendered manifests do not contain inline secrets"
    )
    parser.add_argument(
        "service_definition",
        type=Path,
        help="Service definition file used during rendering",
    )
    parser.add_argument(
        "manifest", nargs="+", type=Path, help="Manifest files to inspect"
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        service = load_yaml(args.service_definition)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    secrets = gather_secret_values(service)
    if not secrets:
        return 0

    failures: list[str] = []
    for manifest in args.manifest:
        if not manifest.exists():
            print(f"Manifest not found: {manifest}", file=sys.stderr)
            return 1
        inlined = check_manifest(manifest, secrets)
        if inlined:
            failures.append(
                f"{manifest}: found inline secrets {', '.join(sorted(inlined))}"
            )

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
