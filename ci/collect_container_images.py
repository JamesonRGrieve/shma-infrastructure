from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Set

import yaml


def _iter_image_values(node: object) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"image", "service_image"} and isinstance(value, str):
                yield value
            else:
                yield from _iter_image_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_image_values(item)


def _collect_from_yaml_file(path: Path) -> Set[str]:
    images: Set[str] = set()
    if not path.exists():
        return images

    try:
        documents = list(yaml.safe_load_all(path.read_text()))
    except yaml.YAMLError as exc:  # pragma: no cover - validation happens in CI
        raise SystemExit(f"Failed to parse YAML from {path}: {exc}") from exc

    for doc in documents:
        if doc is None:
            continue
        for image in _iter_image_values(doc):
            images.add(image)
    return images


def _collect_from_quadlet(path: Path) -> Set[str]:
    images: Set[str] = set()
    if not path.exists():
        return images

    for line in path.read_text().splitlines():
        if line.startswith("Image="):
            _, _, value = line.partition("=")
            if value:
                images.add(value.strip())
    return images


def collect_images(service_file: Path, runtime_dir: Path) -> Set[str]:
    service_doc = yaml.safe_load(service_file.read_text())
    images = set(_iter_image_values(service_doc))

    images.update(_collect_from_yaml_file(runtime_dir / "docker.yml"))
    images.update(_collect_from_yaml_file(runtime_dir / "kubernetes.yml"))
    images.update(_collect_from_quadlet(runtime_dir / "podman.yml"))

    return {image for image in images if image}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect container images for scanning"
    )
    parser.add_argument(
        "service_file", type=Path, help="Path to the service definition"
    )
    parser.add_argument(
        "runtime_dir", type=Path, help="Directory containing rendered runtime manifests"
    )
    args = parser.parse_args()

    images = sorted(collect_images(args.service_file, args.runtime_dir))
    if not images:
        return

    for image in images:
        print(image)


if __name__ == "__main__":
    main()
