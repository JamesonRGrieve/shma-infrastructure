from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
os.environ["PATH"] = f"{BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}"


class AnsiblePlaybookStubTests(unittest.TestCase):
    def tearDown(self) -> None:
        runtime_root = Path("/tmp/ansible-runtime")
        if runtime_root.exists():
            shutil.rmtree(runtime_root)

    def test_supports_extra_vars_file(self) -> None:
        service_file = Path("tests/sample_service.yml").resolve()
        service_id = "sample-service"

        with TemporaryDirectory() as tmpdir:
            vars_file = Path(tmpdir) / "vars.yml"
            vars_file.write_text(
                "\n".join(
                    [
                        f"service_definition_file: {service_file}",
                    ]
                )
                + "\n"
            )

            command = [
                "ansible-playbook",
                "tests/render.yml",
                "-e",
                f"@{vars_file}",
                "-e",
                "runtime=podman",
            ]

            subprocess.run(command, check=True)

        quadlet_manifest = Path("/tmp/ansible-runtime") / service_id / "podman.yml"
        self.assertTrue(
            quadlet_manifest.exists(), "Expected Quadlet manifest to be rendered"
        )

    def test_supports_json_extra_vars_payload(self) -> None:
        service_definition = {
            "service_id": "json-stub",
            "service_name": "json-stub",
            "health": {"cmd": ["/usr/bin/true"]},
        }

        with TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.json"
            service_file.write_text(json.dumps(service_definition))

            extra_vars = json.dumps(
                {
                    "runtime": "docker",
                    "service_definition_file": str(service_file),
                }
            )

            command = [
                "ansible-playbook",
                "tests/render.yml",
                "-e",
                extra_vars,
            ]

            subprocess.run(command, check=True)

        compose_manifest = Path("/tmp/ansible-runtime") / "json-stub" / "docker.yml"
        self.assertTrue(
            compose_manifest.exists(), "Expected Compose manifest to be rendered"
        )


if __name__ == "__main__":
    unittest.main()
