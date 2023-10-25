from typing import Any, Callable

from repairshopr_api.base.model import BaseModel
from repairshopr_api.converters.strings import snake_case


def related_field(model_cls: type[BaseModel]) -> Callable[[Callable[..., BaseModel]], property]:
    def decorator(_f: Callable[..., BaseModel]):
        def wrapper(instance: BaseModel, id_key: str = None) -> BaseModel | list[BaseModel] | list[dict[str, Any]]:
            if not id_key:
                id_key = f"{model_cls.__name__.lower()}_id"

            if hasattr(instance, id_key):
                model_id = getattr(instance, id_key)
                return instance.rs_client.get_model_by_id(model_cls, model_id) if model_id else None
            else:
                model_ids = getattr(instance, f"{id_key}s", [])

                if not model_ids:
                    query_params = {f"{type(instance).__name__.lower()}_id": getattr(instance, "id", None)}
                    results, _ = instance.rs_client.fetch_from_api(f"{snake_case(model_cls.__name__)}", params=query_params)
                    if not results:
                        return []
                    model_ids.extend([result.get("id") for result in results])
                    for result in results:
                        cache_key = f"{model_cls.__name__.lower()}_{result.get('id')}"
                        # noinspection PyProtectedMember
                        instance.rs_client._cache[cache_key] = model_cls.from_dict(result)

                valid_model_ids = [model_id for model_id in model_ids if model_id]
                return [instance.rs_client.fetch_from_api_by_id(model_cls, model_id) for model_id in valid_model_ids]

        return property(wrapper)

    return decorator
