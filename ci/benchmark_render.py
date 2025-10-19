from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

import yaml

DEFAULT_CONFIG_PATH = Path("ci/benchmark_config.yml")


def load_config(config_path: Path) -> dict:
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "defaults": {
                "max_render_seconds": 15.0,
                "max_manifest_size_bytes": 512 * 1024,
                "runtimes": [
                    "docker",
                    "podman",
                    "kubernetes",
                    "proxmox",
                    "baremetal",
                ],
            },
            "services": {},
            "files": {},
        }


def resolve_settings(
    service_file: Path, service_id: str, config: dict
) -> Dict[str, object]:
    defaults = config.get("defaults", {})
    settings: Dict[str, object] = {
        "max_render_seconds": defaults.get("max_render_seconds", 15.0),
        "max_manifest_size_bytes": defaults.get("max_manifest_size_bytes", 512 * 1024),
        "runtimes": list(defaults.get("runtimes", [])),
    }

    file_key = str(service_file)
    file_overrides = config.get("files", {}).get(file_key, {})
    service_overrides = config.get("services", {}).get(service_id, {})

    for overrides in (file_overrides, service_overrides):
        if "max_render_seconds" in overrides:
            settings["max_render_seconds"] = float(overrides["max_render_seconds"])
        if "max_manifest_size_bytes" in overrides:
            settings["max_manifest_size_bytes"] = int(
                overrides["max_manifest_size_bytes"]
            )
        if "runtimes" in overrides:
            settings["runtimes"] = list(overrides["runtimes"])

    return settings


def load_service_id(service_file: Path) -> str:
    with service_file.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    service_id = document.get("service_id")
    if not service_id:
        raise SystemExit(f"service_id missing from {service_file}")
    return service_id


def render_runtime(service_file: Path, runtime: str) -> float:
    command = [
        "ansible-playbook",
        "tests/render.yml",
        "-e",
        f"runtime={runtime}",
        "-e",
        f"service_definition_file={service_file}",
    ]
    start = time.perf_counter()
    subprocess.run(command, check=True)
    return time.perf_counter() - start


def measure_manifest(runtime_dir: Path, runtime: str) -> int:
    manifest_path = runtime_dir / f"{runtime}.yml"
    if not manifest_path.exists():
        raise SystemExit(f"Expected manifest {manifest_path} was not generated")
    return manifest_path.stat().st_size


def benchmark(
    service_file: Path, service_id: str, runtimes: List[str]
) -> Dict[str, Dict[str, float]]:
    runtime_dir = Path("/tmp/ansible-runtime") / service_id
    results: Dict[str, Dict[str, float]] = {}

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    for runtime in runtimes:
        duration = render_runtime(service_file, runtime)
        size_bytes = measure_manifest(runtime_dir, runtime)
        results[runtime] = {"duration": duration, "size_bytes": size_bytes}
    return results


def validate(
    results: Dict[str, Dict[str, float]],
    max_render_seconds: float,
    max_manifest_size_bytes: int,
) -> List[str]:
    failures: List[str] = []
    for runtime, metrics in results.items():
        if metrics["duration"] > max_render_seconds:
            failures.append(
                "Rendering "
                f"{runtime} runtime exceeded {max_render_seconds}s "
                f"(actual {metrics['duration']:.2f}s)"
            )
        if metrics["size_bytes"] > max_manifest_size_bytes:
            failures.append(
                "Manifest for "
                f"{runtime} runtime exceeded {max_manifest_size_bytes} bytes "
                f"(actual {metrics['size_bytes']})"
            )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark runtime rendering speed and size"
    )
    parser.add_argument(
        "service_file", type=Path, help="Path to the service definition file"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Optional path to benchmark configuration overrides",
    )
    args = parser.parse_args()

    service_id = load_service_id(args.service_file)
    config = load_config(args.config)
    settings = resolve_settings(args.service_file, service_id, config)

    runtimes = settings.get("runtimes", [])
    if not runtimes:
        raise SystemExit("No runtimes configured for benchmark execution")

    results = benchmark(args.service_file, service_id, list(runtimes))
    print(json.dumps(results, indent=2))

    failures = validate(
        results,
        float(settings["max_render_seconds"]),
        int(settings["max_manifest_size_bytes"]),
    )
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
