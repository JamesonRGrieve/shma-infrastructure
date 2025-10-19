from __future__ import annotations

import argparse
import json
import subprocess
from typing import List

ROTATION_ANNOTATION = "shma.dev/secrets-rotation"


def run_kubectl(args: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        check=True,
    )


def get_deployment(namespace: str, deployment: str) -> dict:
    result = run_kubectl(
        [
            "get",
            "deployment",
            deployment,
            "-n",
            namespace,
            "-o",
            "json",
        ]
    )
    return json.loads(result.stdout)


def get_pod_names(namespace: str, label_selector: str) -> list[str]:
    result = run_kubectl(
        [
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            label_selector,
            "-o",
            "json",
        ]
    )
    payload = json.loads(result.stdout)
    items = payload.get("items", [])
    return sorted(item["metadata"]["name"] for item in items)


def annotate_rotation(namespace: str, deployment: str, timestamp: str) -> None:
    run_kubectl(
        [
            "annotate",
            "deployment",
            deployment,
            "-n",
            namespace,
            f"{ROTATION_ANNOTATION}={timestamp}",
            "--overwrite",
        ]
    )


def wait_for_rollout(namespace: str, deployment: str, timeout: str) -> None:
    run_kubectl(
        [
            "rollout",
            "status",
            f"deployment/{deployment}",
            "-n",
            namespace,
            "--timeout",
            timeout,
        ]
    )


def validate_rotation_env(namespace: str, pod_name: str, timestamp: str) -> None:
    result = run_kubectl(
        [
            "get",
            "pod",
            pod_name,
            "-n",
            namespace,
            "-o",
            "json",
        ]
    )
    payload = json.loads(result.stdout)
    containers = payload.get("spec", {}).get("containers", [])
    if not containers:
        raise SystemExit(f"Pod {pod_name} has no containers to inspect.")

    env_list = containers[0].get("env", [])
    for entry in env_list:
        if (
            entry.get("name") == "SHMA_SECRETS_ROTATION"
            and entry.get("value") == timestamp
        ):
            return
    raise SystemExit(
        f"Pod {pod_name} is missing SHMA_SECRETS_ROTATION={timestamp} after rotation."
    )


def ensure_secret_rotation(
    namespace: str,
    deployment: str,
    timestamp: str,
    timeout: str,
    label_selector: str | None,
) -> None:
    selector = label_selector or f"app={deployment}"
    deployment_doc = get_deployment(namespace, deployment)
    current_annotation = (
        deployment_doc.get("spec", {})
        .get("template", {})
        .get("metadata", {})
        .get("annotations", {})
        .get(ROTATION_ANNOTATION)
    )

    if current_annotation == timestamp:
        raise SystemExit(
            f"Deployment {deployment} already has {ROTATION_ANNOTATION}={timestamp}; provide a new timestamp to trigger rotation."
        )

    initial_pods = get_pod_names(namespace, selector)
    if not initial_pods:
        raise SystemExit(
            f"No pods found for deployment {deployment} using selector {selector}."
        )

    annotate_rotation(namespace, deployment, timestamp)
    wait_for_rollout(namespace, deployment, timeout)

    refreshed_pods = get_pod_names(namespace, selector)
    if not refreshed_pods:
        raise SystemExit("No pods found after applying the rotation annotation.")

    if not set(refreshed_pods) - set(initial_pods):
        raise SystemExit(
            "Secret rotation annotation did not trigger a new ReplicaSet; pod names are unchanged."
        )

    validate_rotation_env(namespace, refreshed_pods[0], timestamp)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that updating secrets.rotation_timestamp triggers a rollout in Kubernetes"
        )
    )
    parser.add_argument(
        "namespace", help="Kubernetes namespace containing the deployment"
    )
    parser.add_argument("deployment", help="Deployment name to annotate")
    parser.add_argument("timestamp", help="New secrets.rotation_timestamp value")
    parser.add_argument(
        "--timeout",
        default="120s",
        help="Timeout to wait for the rollout to complete (default: 120s)",
    )
    parser.add_argument(
        "--label-selector",
        help="Optional label selector used to find pods (defaults to app=<deployment>)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_secret_rotation(
        namespace=args.namespace,
        deployment=args.deployment,
        timestamp=args.timestamp,
        timeout=args.timeout,
        label_selector=args.label_selector,
    )


if __name__ == "__main__":
    main()
