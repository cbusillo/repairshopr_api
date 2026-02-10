import logging
from typing import Mapping

from repairshopr_api.type_defs import is_json_object, JsonObject, JsonValue

logger = logging.getLogger(__name__)


class Serializable:
    def _annotations(self) -> dict[str, object]:
        annotations: dict[str, object] = {}
        for cls in reversed(type(self).mro()):
            cls_annotations = getattr(cls, "__annotations__", None)
            if isinstance(cls_annotations, dict):
                annotations.update(cls_annotations)
        return annotations

    def to_dict(self) -> JsonObject:
        result: JsonObject = {}
        all_keys = self.get_all_keys()
        for key in all_keys:
            if not key.startswith("_"):
                value = getattr(self, key, None)
                if isinstance(value, Serializable):
                    result[key] = value.to_dict()
                else:
                    result[key] = value
        return result

    def from_dict(self, data: Mapping[str, JsonValue]) -> None:
        for key, _type_hint in self._annotations().items():
            value = data.get(key, getattr(self, key, None))

            try:
                existing_attr = getattr(self, key)
            except AttributeError:
                logger.warning(f"{key} not in {self.__class__.__name__}. Skipping...")
                continue

            if isinstance(existing_attr, Serializable):
                if not is_json_object(value):
                    logger.warning(
                        f"Expected dict for {key} in {self.__class__.__name__}, got {type(value)}. Skipping..."
                    )
                    continue
                existing_attr.from_dict(value)
            else:
                setattr(self, key, value)

        self.validate()

    def validate(self) -> None:
        for key, _value in self._annotations().items():
            if getattr(self, key, None) is None:
                logger.warning(
                    f"Warning: Configuration value '{key}' is missing or None in {self.__class__.__name__}"
                )

    def get_all_keys(self) -> set[str]:
        instance_keys = set(self.__dict__.keys())
        annotation_keys = set(self._annotations().keys())
        return instance_keys | annotation_keys

    def gather_missing_data(self, parent_name: str = "") -> None:
        all_keys = self.get_all_keys()
        for key in all_keys:
            if not key.startswith("_"):
                value = getattr(self, key, None)
                full_key_name = f"{parent_name}.{key}" if parent_name else key
                if value == "from_terminal":
                    new_value = input(
                        f"{full_key_name} not in configuration. Please enter a value: "
                    )
                    setattr(self, key, new_value)
                elif isinstance(value, Serializable):
                    value.gather_missing_data(full_key_name)
