import textwrap
from pathlib import Path

import pytest

jinja2 = pytest.importorskip("jinja2")
Environment = jinja2.Environment
FileSystemLoader = jinja2.FileSystemLoader


TEMPLATE_DIR = Path("templates")
TEMPLATE_NAME = "baremetal.yml.j2"


def render_baremetal(**overrides: object) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(TEMPLATE_NAME)

    context: dict[str, object] = {
        "service_id": "sample-service",
        "service_name": "sample-service",
        "service_unit": {},
        "service_security": {},
        "mounts": {},
    }
    context.update(overrides)
    rendered = template.render(**context)
    return textwrap.dedent(rendered).strip()


def test_system_call_filter_sequence_renders() -> None:
    rendered = render_baremetal(
        service_security={
            "system_call_filter": ["~clone", "@system-service"],
        }
    )

    assert "SystemCallFilter=~clone @system-service" in rendered


def test_restart_parameters_apply_defaults() -> None:
    rendered = render_baremetal(
        service_restart={
            "restart": "on-failure",
            "restart_sec": "5s",
            "restart_prevent_exit_status": ["SIGKILL", "SIGTERM"],
            "start_limit_burst": 5,
        }
    )

    assert "Restart=on-failure" in rendered
    assert "RestartSec=5s" in rendered
    assert "RestartPreventExitStatus=SIGKILL SIGTERM" in rendered
    assert "StartLimitBurst=5" in rendered


def test_service_section_override_skips_restart_defaults() -> None:
    rendered = render_baremetal(
        service_restart={"restart": "on-failure"},
        service_unit={"service": {"Restart": "always"}},
    )

    service_lines = [
        line.strip() for line in rendered.splitlines() if line.startswith("Restart=")
    ]

    assert service_lines == ["Restart=always"]


def test_protect_home_boolean_converts_to_yes() -> None:
    rendered = render_baremetal(
        service_security={
            "protect_home": True,
        }
    )

    assert "ProtectHome=yes" in rendered
