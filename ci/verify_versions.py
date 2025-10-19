#!/usr/bin/env python3
"""Assert that toolchain versions stay within the documented compatibility matrix."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

MATRIX_PATH = Path("ci/version_matrix.yml")


def load_matrix() -> Dict[str, object]:
    try:
        return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(f"Failed to parse version matrix: {exc}") from exc


MATRIX = load_matrix()


def run_command(command: List[str]) -> subprocess.CompletedProcess[str]:
    """Execute *command* returning the completed process with UTF-8 text."""

    return subprocess.run(command, check=True, capture_output=True, text=True)


def check_python() -> List[str]:
    version = sys.version.split()[0]
    expected_prefix = str(MATRIX["python"]["prefix"])
    if not version.startswith(expected_prefix):
        return [f"Python {version} is outside the supported {expected_prefix} range."]
    return []


def check_ansible() -> List[str]:
    errors: List[str] = []

    try:
        pip_info = run_command([sys.executable, "-m", "pip", "show", "ansible"])
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive guard
        errors.append(
            "Unable to determine ansible version via pip: " + exc.stderr.strip()
        )
    else:
        version_match = re.search(
            r"^Version:\s*(?P<version>\S+)$", pip_info.stdout, re.MULTILINE
        )
        if not version_match:
            errors.append("ansible package version could not be parsed.")
        else:
            version = version_match.group("version")
            expected_prefix = str(MATRIX["ansible"]["package_prefix"])
            if not version.startswith(expected_prefix):
                errors.append(
                    "Ansible package "
                    f"{version} is outside the supported {expected_prefix} range."
                )

    try:
        ansible_out = run_command(["ansible", "--version"])
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive guard
        errors.append("Unable to execute ansible --version: " + exc.stderr.strip())
    except FileNotFoundError:  # pragma: no cover - defensive guard
        errors.append("ansible binary not found in PATH.")
    else:
        match = re.search(r"ansible \[core (?P<version>[\d.]+)\]", ansible_out.stdout)
        if not match:
            errors.append(
                "ansible --version output did not contain a core version identifier."
            )
        else:
            version = match.group("version")
            expected_prefix = str(MATRIX["ansible"]["core_prefix"])
            if not version.startswith(expected_prefix):
                errors.append(
                    "ansible-core "
                    f"{version} is outside the supported {expected_prefix} range."
                )

    return errors


def check_kubectl() -> List[str]:
    errors: List[str] = []

    try:
        result = run_command(["kubectl", "version", "--client", "--output", "json"])
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive guard
        errors.append("kubectl version command failed: " + exc.stderr.strip())
        return errors
    except FileNotFoundError:  # pragma: no cover - defensive guard
        errors.append("kubectl binary not found in PATH.")
        return errors

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        errors.append(f"kubectl returned invalid JSON: {exc}")
        return errors

    git_version = payload.get("clientVersion", {}).get("gitVersion")
    if not git_version:
        errors.append(
            "kubectl clientVersion.gitVersion was missing from the JSON payload."
        )
    else:
        allowed_versions = {
            str(MATRIX["kubectl"]["stable"]),
            str(MATRIX["kubectl"]["latest"]),
        }
        if git_version not in allowed_versions:
            allowed = ", ".join(sorted(allowed_versions))
            errors.append(
                f"kubectl {git_version} is outside the supported set: {allowed}."
            )

    return errors


CHECKS = (check_python, check_ansible, check_kubectl)


def main() -> int:
    failures: List[str] = []
    for check in CHECKS:
        failures.extend(check())

    if failures:
        for failure in failures:
            print(f"::error::{failure}")
        return 1

    print("All toolchain versions fall within the documented compatibility matrix.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
