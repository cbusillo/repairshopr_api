import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path
from collections.abc import Sequence


def _manage_script() -> str:
    spec = find_spec("repairshopr_sync.manage")
    if spec is None or spec.origin is None:
        raise RuntimeError("Could not locate repairshopr_sync.manage")
    return str(Path(spec.origin).resolve())


def _run_manage(args: Sequence[str]) -> int:
    completed = subprocess.run([sys.executable, _manage_script(), *args])
    return completed.returncode


def runserver() -> int:
    exit_code = makemigrations()
    if exit_code != 0:
        return exit_code

    exit_code = migrate()
    if exit_code != 0:
        return exit_code

    return _run_manage(["runserver"])


def makemigrations() -> int:
    return _run_manage(["makemigrations"])


def migrate() -> int:
    return _run_manage(["migrate"])


def import_from_repairshopr() -> int:
    exit_code = makemigrations()
    if exit_code != 0:
        return exit_code

    exit_code = migrate()
    if exit_code != 0:
        return exit_code

    return _run_manage(["import_from_repairshopr"])
