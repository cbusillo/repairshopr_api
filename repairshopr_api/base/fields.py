from typing import Callable

from repairshopr_api.base.model import BaseModel
from repairshopr_api.converters.strings import snake_case

ID_SUFFIX = "_id"
PLURAL_SUFFIX = "s"


def related_field(model_cls: type[BaseModel]) -> Callable[[Callable[..., BaseModel]], property]:
    def build_id_key(default_key: str) -> str:
        return default_key if default_key else f"{model_cls.__name__.lower()}{ID_SUFFIX}"

    def fetch_single_related_model(instance: BaseModel, model_id: int) -> BaseModel:
        return instance.rs_client.get_model_by_id(model_cls, model_id) if model_id else None

    def fetch_multiple_related_models(instance: BaseModel, model_ids: list[int]) -> list[dict[str, any]]:
        valid_model_ids = [model_id for model_id in model_ids if model_id]
        return [instance.rs_client.fetch_from_api_by_id(model_cls, model_id) for model_id in valid_model_ids]

    def decorator(_f: Callable[..., BaseModel]) -> property:
        def wrapper(instance: BaseModel, id_key: str = None) -> BaseModel | list[dict[str, any]]:
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

                    model_ids.extend([result.get("id") for result in results])

                    for result in results:
                        cache_key = f"{model_cls.__name__.lower()}_{result.get('id')}"
                        # noinspection PyProtectedMember
                        instance.rs_client._cache[cache_key] = model_cls.from_dict(result)

                return fetch_multiple_related_models(instance, model_ids)

        return property(wrapper)

    return decorator
