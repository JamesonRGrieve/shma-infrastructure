"""Expose docker compose filters within the render_runtime role."""

from __future__ import annotations

import os
import sys


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))


root_path = _project_root()
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from filter_plugins.docker_compose import docker_compose_prepare_services


class FilterModule:
    def filters(self):
        return {"docker_compose_prepare_services": docker_compose_prepare_services}
