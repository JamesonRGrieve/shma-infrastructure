from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TextIO

if __package__ in {None, ""}:  # pragma: no cover - CLI fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import yaml
else:  # pragma: no cover - package import
    import yaml


def load_service(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - runtime validation
        raise ValueError(f"Failed to parse service definition {path}: {exc}") from exc


def determine_metadata(service: dict, runtime_base: Path) -> dict[str, str]:
    service_id = service["service_id"]
    service_name = service.get("service_name", service_id)
    namespace = service.get("service_namespace", "default")
    runtime_dir = runtime_base / service_id
    return {
        "service_id": str(service_id),
        "service_name": str(service_name),
        "namespace": str(namespace),
        "runtime_dir": str(runtime_dir),
    }


def emit_metadata(metadata: dict[str, str], handle: TextIO) -> None:
    for key, value in metadata.items():
        handle.write(f"{key}={value}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit CI metadata for a service definition"
    )
    parser.add_argument(
        "service_file", type=Path, help="Path to the service YAML definition"
    )
    parser.add_argument(
        "--runtime-base",
        type=Path,
        default=Path("/tmp/ansible-runtime"),
        help="Directory used as the root for render outputs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional file to receive key=value pairs (defaults to GITHUB_OUTPUT)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        service = load_service(args.service_file)
    except (ValueError, KeyError) as exc:
        print(exc, file=sys.stderr)
        return 1

    try:
        metadata = determine_metadata(service, args.runtime_base)
    except KeyError as exc:
        print(f"Missing required key in service definition: {exc}", file=sys.stderr)
        return 1

    output_path = args.output or os.environ.get("GITHUB_OUTPUT")
    if output_path:
        path = Path(output_path)
        with path.open("a", encoding="utf-8") as handle:
            emit_metadata(metadata, handle)
    else:
        emit_metadata(metadata, sys.stdout)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
