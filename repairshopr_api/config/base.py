import os
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Mapping, Self

import toml

from repairshopr_api.config.sections import Django, Repairshopr
from repairshopr_api.config.serializable import Serializable
from repairshopr_api.type_defs import JsonObject, JsonValue

logger = logging.getLogger(__name__)


class AppSettings(Serializable):
    _instance = None
    debug: bool = False

    def __init__(self) -> None:
        self.django = Django()
        self.repairshopr = Repairshopr()
        if not self.config_file_path.exists():
            self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_file_path.touch()

        self.load()  # Load config during instance creation

    @classmethod
    def get_instance(cls) -> Self:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def config_file_path(self) -> Path:
        configured_path = os.getenv("REPAIRSHOPR_CONFIG_FILE") or os.getenv(
            "CONFIG_FILE"
        )
        if configured_path:
            return Path(configured_path).expanduser()
        project_name = Path(__file__).parent.parent.name.replace("_", "-")
        file_path = Path.home() / ".config" / project_name / "config.toml"
        return file_path

    @property
    def config_data(self) -> JsonObject:
        if not self.config_file_path.exists():
            return {}
        with self.config_file_path.open() as file:
            return toml.load(file)

    @config_data.setter
    def config_data(self, data: JsonObject):
        with self.config_file_path.open("w") as file:
            toml.dump(data, file)

    def load(self) -> None:
        try:
            with self.config_file_path.open() as file:
                data = toml.load(file)
                for key, value in data.items():
                    if key.startswith("_"):
                        continue
                    attr = getattr(self, key, None)
                    if isinstance(attr, Serializable):
                        attr.from_dict(value)
                    else:
                        setattr(self, key, value)
        except (FileNotFoundError, OSError, toml.TomlDecodeError) as error:
            logger.exception(f"Error loading configuration {str(error)}")
        self.save()

    def save(self) -> None:
        self.gather_missing_data()
        data = self.to_dict()
        data = self.sort_dict(data)
        try:
            with self.config_file_path.open("w") as file:
                toml.dump(data, file)
        except (FileNotFoundError, OSError) as error:
            logger.exception(f"Error saving configuration: {str(error)}")

    def update_and_save(self, **kwargs: JsonValue) -> None:
        for key, value in kwargs.items():
            parts = key.split("__")
            if len(parts) > 1 and hasattr(self, parts[0]):
                obj = getattr(self, parts[0])
                setattr(obj, parts[1], value)
            else:
                setattr(self, key, value)
        self.save()

    def sort_dict(self, d: Mapping[str, JsonValue]) -> JsonObject:
        sorted_dict: JsonObject = {}
        for key in sorted(d.keys()):
            value = d[key]
            if isinstance(value, dict):
                sorted_dict[key] = self.sort_dict(value)
            else:
                sorted_dict[key] = value
        return sorted_dict

    @contextmanager
    def debug_on(self) -> Generator[None, None, None]:
        original_value = self.debug
        self.debug = True
        yield
        self.debug = original_value
