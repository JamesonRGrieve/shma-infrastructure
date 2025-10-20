from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Iterable


def _extend_sys_path_for_pipx() -> None:
    """Ensure pipx-managed site-packages are importable for test utilities."""

    pipx_venvs = Path.home() / ".local/share/pipx/venvs"
    if not pipx_venvs.exists():
        return

    for venv in pipx_venvs.iterdir():
        lib_dir = venv / "lib"
        if not lib_dir.exists():
            continue
        for python_dir in lib_dir.iterdir():
            site_packages = python_dir / "site-packages"
            if site_packages.exists() and str(site_packages) not in sys.path:
                sys.path.insert(0, str(site_packages))


_extend_sys_path_for_pipx()

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # type: ignore  # noqa: E402  (available via pipx ansible environment)

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
os.environ["PATH"] = f"{BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}"


class RuntimeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service_file = Path("tests/sample_service.yml").resolve()
        cls.service_doc = yaml.safe_load(cls.service_file.read_text())
        cls.service_id = cls.service_doc["service_id"]
        cls.runtime_dir = Path("/tmp/ansible-runtime") / cls.service_id

        if cls.runtime_dir.exists():
            shutil.rmtree(cls.runtime_dir)

        for runtime in ("docker", "podman"):
            cls._render_runtime(runtime)

        cls.compose_manifest_text = (cls.runtime_dir / "docker.yml").read_text()
        cls.quadlet_manifest_text = (cls.runtime_dir / "podman.yml").read_text()
        cls.quadlet_manifest_lines = tuple(
            line.strip() for line in cls.quadlet_manifest_text.splitlines()
        )

        health = cls.service_doc.get("health", {}) or {}
        cmd: Iterable[str] = health.get("cmd") or ["true"]
        cls.expected_health_cmd = list(cmd)
        cls.expected_health_cmd_string = " ".join(cls.expected_health_cmd)
        cls.compose_service_name = cls.service_doc.get("service_name") or cls.service_id

    @classmethod
    def _render_runtime(cls, runtime: str) -> None:
        command = [
            "ansible-playbook",
            "tests/render.yml",
            "-e",
            f"runtime={runtime}",
            "-e",
            f"service_definition_file={cls.service_file}",
        ]
        subprocess.run(command, check=True)

    def _assert_health_cmd(self, runtime: str, actual: object) -> None:
        if runtime == "docker":
            self.assertEqual(self.expected_health_cmd, list(actual))
        elif runtime == "podman":
            self.assertEqual(self.expected_health_cmd_string, str(actual))
        else:  # pragma: no cover - defensive guard for new runtimes
            raise ValueError(f"Unsupported runtime {runtime}")

    def test_quadlet_emits_security_defaults(self) -> None:
        self.assertIn("ReadOnly=true", self.quadlet_manifest_lines)
        self.assertIn("NoNewPrivileges=true", self.quadlet_manifest_lines)
        self.assertIn("NoNewPrivileges=yes", self.quadlet_manifest_lines)

        drop_caps = [
            line
            for line in self.quadlet_manifest_lines
            if line.startswith("DropCapability=")
        ]
        self.assertTrue(drop_caps, "Expected at least one DropCapability directive")
        self.assertIn("DropCapability=ALL", drop_caps)

    def test_compose_health_cmd_matches_service_definition(self) -> None:
        match = None
        for line in self.compose_manifest_text.splitlines():
            if "healthcheck" in line:
                continue
            if "test:" in line:
                match = line
                break
        self.assertIsNotNone(
            match, "Compose manifest missing healthcheck test definition"
        )
        _, _, raw = match.partition(":")
        parsed = json.loads(raw.strip())
        self._assert_health_cmd("docker", parsed)

    def test_quadlet_health_cmd_matches_compose(self) -> None:
        health_line = next(
            (line for line in self.quadlet_manifest_lines if "HealthCmd=" in line),
            None,
        )
        self.assertIsNotNone(health_line, "Quadlet manifest missing HealthCmd entry")
        _, _, value = health_line.partition("HealthCmd=")
        self._assert_health_cmd("podman", value.strip())


if __name__ == "__main__":  # pragma: no cover - manual invocation
    unittest.main()
