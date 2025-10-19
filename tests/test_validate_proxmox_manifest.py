from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci import validate_proxmox_manifest as proxmox_validator


class ValidateProxmoxManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._schema_original = proxmox_validator.SCHEMA_PATH
        cls._schema_tmpdir = TemporaryDirectory()
        schema_path = Path(cls._schema_tmpdir.name) / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        proxmox_validator.SCHEMA_PATH = schema_path

    @classmethod
    def tearDownClass(cls) -> None:
        proxmox_validator.SCHEMA_PATH = cls._schema_original
        cls._schema_tmpdir.cleanup()

    def _write_yaml(self, base: Path, name: str, payload: dict) -> Path:
        path = base / name
        path.write_text(json.dumps(payload))
        return path

    def _run_validator(
        self, manifest: dict, service: dict, registry: dict | None = None
    ) -> tuple[int, str, str]:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            manifest_path = self._write_yaml(base, "manifest.yml", manifest)
            service_path = self._write_yaml(base, "service.yml", service)
            registry_path = None
            if registry is not None:
                registry_path = self._write_yaml(base, "registry.yml", registry)

            stderr = io.StringIO()
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = proxmox_validator.validate_manifest(
                    manifest_path, service_path, registry_path
                )

            return result, stdout.getvalue(), stderr.getvalue()

    def test_features_allowed_when_runtime_enabled(self) -> None:
        manifest = {
            "container_ip": "192.0.2.10",
            "container": {
                "vmid": "100",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "yes",
                "features": "keyctl=1",
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {"needs_container_runtime": True}

        result, stdout, stderr = self._run_validator(manifest, service)

        self.assertEqual(result, 0)
        self.assertIn("Validated Proxmox manifest", stdout)
        self.assertEqual("", stderr)

    def test_unprivileged_required_without_privilege_override(self) -> None:
        manifest = {
            "container_ip": "192.0.2.20",
            "container": {
                "vmid": "101",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "no",
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {"needs_container_runtime": True}

        result, _, stderr = self._run_validator(manifest, service)

        self.assertEqual(result, 1)
        self.assertIn("must remain unprivileged", stderr)

    def test_privilege_override_allows_privileged_container(self) -> None:
        manifest = {
            "container_ip": "192.0.2.21",
            "container": {
                "vmid": "102",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "no",
                "features": "nesting=1",
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {
            "needs_container_runtime": True,
            "service_security": {"allow_privilege_escalation": True},
        }

        result, stdout, stderr = self._run_validator(manifest, service)

        self.assertEqual(result, 0)
        self.assertIn("Validated Proxmox manifest", stdout)
        self.assertEqual("", stderr)

    def test_nesting_requires_privilege_override(self) -> None:
        manifest = {
            "container_ip": "192.0.2.22",
            "container": {
                "vmid": "103",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "yes",
                "features": "nesting=1,keyctl=1",
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {"needs_container_runtime": True}

        result, _, stderr = self._run_validator(manifest, service)

        self.assertEqual(result, 1)
        self.assertIn("container nesting requires", stderr)

    def test_invalid_feature_rejected(self) -> None:
        manifest = {
            "container_ip": "192.0.2.30",
            "container": {
                "vmid": "104",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "yes",
                "features": "unsupported=1",
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {"needs_container_runtime": True}

        result, _, stderr = self._run_validator(manifest, service)

        self.assertEqual(result, 1)
        self.assertIn("Unsupported Proxmox LXC feature", stderr)

    def test_vmid_conflict_detected(self) -> None:
        manifest = {
            "container_ip": "192.0.2.31",
            "container": {
                "vmid": "105",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "yes",
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {"needs_container_runtime": True, "service_id": "new-service"}

        registry = {"vmids": [{"vmid": 105, "service": "other-service"}]}

        result, _, stderr = self._run_validator(manifest, service, registry)

        self.assertEqual(result, 1)
        self.assertIn("conflicts with existing container", stderr)

    def test_firewall_validation(self) -> None:
        manifest = {
            "container_ip": "192.0.2.32",
            "container": {
                "vmid": "106",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "yes",
                "firewall": {
                    "enabled": True,
                    "rules": [
                        {
                            "action": "ACCEPT",
                            "direction": "in",
                            "protocol": "tcp",
                            "destination_port": "443",
                        }
                    ],
                },
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {"needs_container_runtime": True}

        result, stdout, stderr = self._run_validator(manifest, service)

        self.assertEqual(result, 0)
        self.assertIn("Validated Proxmox manifest", stdout)
        self.assertEqual("", stderr)

    def test_firewall_invalid_direction(self) -> None:
        manifest = {
            "container_ip": "192.0.2.33",
            "container": {
                "vmid": "107",
                "hostname": "example",
                "ostemplate": "tpl",
                "disk": "5",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "netif": {"net0": "name=eth0"},
                "onboot": "yes",
                "unprivileged": "yes",
                "firewall": {
                    "enabled": True,
                    "rules": [{"action": "ACCEPT", "direction": "invalid"}],
                },
            },
            "setup": {
                "packages": [],
                "config": [],
                "services": [],
                "commands": [],
            },
        }
        service = {"needs_container_runtime": True}

        result, _, stderr = self._run_validator(manifest, service)

        self.assertEqual(result, 1)
        self.assertIn("direction must be 'in' or 'out'", stderr)


if __name__ == "__main__":
    unittest.main()
