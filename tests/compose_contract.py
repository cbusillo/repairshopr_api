from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADDON_COMPOSE_PATH = ROOT / "addons" / "repairshopr-sync" / "compose.yml"
COOLIFY_COMPOSE_PATH = ROOT / "docker" / "coolify" / "compose.yml"
DEPENDABOT_PATH = ROOT / ".github" / "dependabot.yml"
LAUNCHPLANE_IMAGE_REFERENCE = (
    "${DOCKER_IMAGE_REFERENCE:?DOCKER_IMAGE_REFERENCE is required}"
)


def _load_yaml(text: str) -> object:
    safe_load = getattr(import_module("yaml"), "safe_load")
    assert callable(safe_load), "yaml.safe_load must be callable"
    return safe_load(text)


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    document = _load_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path} is not a YAML mapping"
    return document


def compose_services(document: dict[str, Any]) -> dict[str, Any]:
    services = document.get("services")
    assert isinstance(services, dict), "compose services must be a mapping"
    return services


def compose_service(document: dict[str, Any], name: str) -> dict[str, Any]:
    service = compose_services(document).get(name)
    assert isinstance(service, dict), f"compose service {name!r} must be a mapping"
    return service


def _scalar_text(value: object) -> str:
    if value is None:
        return ""
    assert isinstance(value, (str, int, float, bool, date)), "unsupported YAML scalar"
    return str(value)


def service_environment(service: dict[str, Any]) -> dict[str, str]:
    environment = service.get("environment", {})
    if isinstance(environment, dict):
        return {
            _scalar_text(key): _scalar_text(value) for key, value in environment.items()
        }

    assert isinstance(
        environment, list
    ), "service environment must be a mapping or list"
    entries: dict[str, str] = {}
    for entry in environment:
        assert isinstance(entry, str), "environment list entries must be strings"
        key, separator, value = entry.partition("=")
        entries[key] = value if separator else ""
    return entries


def service_ports(service: dict[str, Any]) -> list[str]:
    ports = service.get("ports", [])
    assert isinstance(ports, list), "service ports must be a list"
    normalized: list[str] = []
    for entry in ports:
        if isinstance(entry, dict):
            published = _scalar_text(entry.get("published"))
            target = _scalar_text(entry.get("target"))
            normalized.append(f"{published}:{target}")
        else:
            assert not isinstance(entry, int), "short-form compose ports must be quoted"
            normalized.append(_scalar_text(entry))
    return normalized


def dependabot_directories(update: dict[str, Any]) -> list[str]:
    directories = update.get("directories")
    if directories is None:
        directory = update.get("directory")
        assert isinstance(directory, str), "dependabot directory must be a string"
        return [directory]

    assert isinstance(directories, list), "dependabot directories must be a list"
    assert all(isinstance(directory, str) for directory in directories)
    return directories


def include_paths(document: dict[str, Any], base_path: Path) -> list[Path]:
    include = document.get("include", [])
    assert isinstance(include, list), "compose include must be a list"
    paths: list[Path] = []
    for entry in include:
        raw_paths = entry.get("path", []) if isinstance(entry, dict) else entry
        candidates = raw_paths if isinstance(raw_paths, list) else [raw_paths]
        paths.extend(
            (base_path / _scalar_text(candidate)).resolve() for candidate in candidates
        )
    return paths


def iter_scalar_texts(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield _scalar_text(key)
            yield from iter_scalar_texts(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_scalar_texts(item)
    elif node is not None:
        yield _scalar_text(node)
