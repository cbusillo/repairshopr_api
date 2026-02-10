from typing import Callable

from repairshopr_api.base.model import BaseModel
from repairshopr_api.converters.strings import snake_case
from repairshopr_api.type_defs import JsonObject, is_json_object

ID_SUFFIX = "_id"
PLURAL_SUFFIX = "s"


def related_field(model_cls: type[BaseModel]) -> Callable[[Callable[..., BaseModel]], property]:
    def build_id_key(default_key: str | None) -> str:
        return default_key if default_key else f"{model_cls.__name__.lower()}{ID_SUFFIX}"

    def fetch_single_related_model(instance: BaseModel, model_id: int) -> BaseModel | None:
        return instance.rs_client.get_model_by_id(model_cls, model_id) if model_id else None

    def fetch_multiple_related_models(instance: BaseModel, model_ids: list[int]) -> list[JsonObject]:
        valid_model_ids = [model_id for model_id in model_ids if model_id]
        return [instance.rs_client.fetch_from_api_by_id(model_cls, model_id) for model_id in valid_model_ids]

    def decorator(_f: Callable[..., BaseModel]) -> property:
        def wrapper(instance: BaseModel, id_key: str | None = None) -> BaseModel | list[JsonObject] | None:
            id_key = build_id_key(id_key)

            if hasattr(instance, id_key):
                model_id = getattr(instance, id_key)
                return fetch_single_related_model(instance, model_id)

            else:
                model_ids = getattr(instance, f"{id_key}{PLURAL_SUFFIX}", [])

                if not model_ids:
                    query_params = {f"{type(instance).__name__.lower()}{ID_SUFFIX}": getattr(instance, "id", None)}
                    results, _ = instance.rs_client.fetch_from_api(snake_case(model_cls.__name__), params=query_params)

                    if not results:
                        return []

                    for result in results:
                        if not is_json_object(result):
                            continue

                        result_id = result.get("id")
                        if not isinstance(result_id, int):
                            continue

                        model_ids.append(result_id)
                        cache_key = f"{model_cls.__name__.lower()}_{result_id}"
                        # noinspection PyProtectedMember
                        instance.rs_client._cache[cache_key] = result

                return fetch_multiple_related_models(instance, model_ids)

        return property(wrapper)

    return decorator
