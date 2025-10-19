from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import List

import yaml

from filter_plugins.health import get_health_command


def load_health_command(service_file: Path) -> List[str]:
    document = yaml.safe_load(service_file.read_text())
    try:
        return get_health_command(document.get("health"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def ensure_health(namespace: str, app_name: str, command: List[str]) -> None:
    get_pods = subprocess.run(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            f"app={app_name}",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(get_pods.stdout)
    items = payload.get("items", [])
    if not items:
        raise SystemExit(f"No pods found for app={app_name} in namespace {namespace}")

    pod_name = items[0]["metadata"]["name"]
    subprocess.run(
        ["kubectl", "exec", "-n", namespace, pod_name, "--", *command],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run workload health checks inside Kubernetes pods"
    )
    parser.add_argument("service_file", type=Path, help="Service definition file")
    parser.add_argument("namespace", help="Kubernetes namespace")
    parser.add_argument("app_name", help="App label and deployment name")
    args = parser.parse_args()

    command = load_health_command(args.service_file)
    ensure_health(args.namespace, args.app_name, command)


if __name__ == "__main__":
    main()
