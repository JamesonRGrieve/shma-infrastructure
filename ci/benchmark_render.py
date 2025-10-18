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

MAX_RENDER_SECONDS = 15.0
MAX_MANIFEST_SIZE_BYTES = 512 * 1024
SUPPORTED_RUNTIMES = ["docker", "podman", "kubernetes", "proxmox", "baremetal"]


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


def benchmark(service_file: Path) -> Dict[str, Dict[str, float]]:
    service_id = load_service_id(service_file)
    runtime_dir = Path("/tmp/ansible-runtime") / service_id
    results: Dict[str, Dict[str, float]] = {}

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    for runtime in SUPPORTED_RUNTIMES:
        duration = render_runtime(service_file, runtime)
        size_bytes = measure_manifest(runtime_dir, runtime)
        results[runtime] = {"duration": duration, "size_bytes": size_bytes}
    return results


def validate(results: Dict[str, Dict[str, float]]) -> List[str]:
    failures: List[str] = []
    for runtime, metrics in results.items():
        if metrics["duration"] > MAX_RENDER_SECONDS:
            failures.append(
                f"Rendering {runtime} runtime exceeded {MAX_RENDER_SECONDS}s (actual {metrics['duration']:.2f}s)"
            )
        if metrics["size_bytes"] > MAX_MANIFEST_SIZE_BYTES:
            failures.append(
                f"Manifest for {runtime} runtime exceeded {MAX_MANIFEST_SIZE_BYTES} bytes (actual {metrics['size_bytes']})"
            )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark runtime rendering speed and size"
    )
    parser.add_argument(
        "service_file", type=Path, help="Path to the service definition file"
    )
    args = parser.parse_args()

    results = benchmark(args.service_file)
    print(json.dumps(results, indent=2))

    failures = validate(results)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
