from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
IDEA_ROOT = ROOT / ".idea"
PYPROJECT_PATH = ROOT / "pyproject.toml"


def _module_name() -> str:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project_name = pyproject["project"]["name"]
    return re.sub(r"[-_.]+", "-", project_name)


def test_pycharm_module_matches_pyproject_name() -> None:
    module_name = _module_name()
    module_files = sorted(IDEA_ROOT.glob("*.iml"))

    assert module_files == [IDEA_ROOT / f"{module_name}.iml"]
    assert (IDEA_ROOT / ".name").read_text(
        encoding="utf-8"
    ).strip() == "repairshopr_api"

    modules_root = ElementTree.parse(IDEA_ROOT / "modules.xml").getroot()
    module = modules_root.find("./component/modules/module")
    assert module is not None
    assert module.attrib["filepath"] == f"$PROJECT_DIR$/.idea/{module_name}.iml"


def test_shared_run_configurations_use_canonical_module() -> None:
    module_name = _module_name()

    for run_configuration in sorted((IDEA_ROOT / "runConfigurations").glob("*.xml")):
        root = ElementTree.parse(run_configuration).getroot()
        configuration = root.find("./configuration")
        assert configuration is not None, run_configuration
        if configuration.attrib.get("type") not in {
            "Python.DjangoServer",
            "PythonConfigurationType",
        }:
            continue
        module = root.find("./configuration/module")
        assert module is not None, run_configuration
        assert module.attrib["name"] == module_name, run_configuration


def test_pycharm_module_preserves_shared_django_roots() -> None:
    module_root = ElementTree.parse(IDEA_ROOT / f"{_module_name()}.iml").getroot()

    assert module_root.attrib["external.system.id"] == "pyproject.toml"
    assert module_root.find("./component/facet[@type='django']") is not None

    content = module_root.find("./component[@name='NewModuleRootManager']/content")
    assert content is not None
    source_urls = {folder.attrib["url"] for folder in content.findall("sourceFolder")}
    excluded_urls = {
        folder.attrib["url"] for folder in content.findall("excludeFolder")
    }

    assert {
        "file://$MODULE_DIR$",
        "file://$MODULE_DIR$/config",
        "file://$MODULE_DIR$/repairshopr_api",
        "file://$MODULE_DIR$/repairshopr_sync",
    }.issubset(source_urls)
    assert {
        "file://$MODULE_DIR$/.code",
        "file://$MODULE_DIR$/.idea/copilot/chatSessions",
        "file://$MODULE_DIR$/.venv",
        "file://$MODULE_DIR$/dist",
        "file://$MODULE_DIR$/repairshopr_sync/repairshopr_data/migrations",
    }.issubset(excluded_urls)


def test_plugin_local_idea_state_is_ignored() -> None:
    ignore_entries = set()
    for line in (IDEA_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            ignore_entries.add(stripped)

    assert "/db-forest-config.xml" in ignore_entries
    assert "/dataSources.xml" in ignore_entries
    assert "/pyLspTools.xml" in ignore_entries


def test_tracked_idea_files_exclude_machine_local_paths() -> None:
    tracked_paths = subprocess.run(
        ["git", "ls-files", ".idea"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    forbidden_fragments = ("$USER_HOME$", "/Users/", "/home/", "pypoetry")
    for relative_path in tracked_paths:
        file_text = (ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            assert fragment not in file_text, relative_path
