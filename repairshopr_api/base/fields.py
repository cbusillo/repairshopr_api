from typing import Callable

from repairshopr_api.base.model import BaseModel


def related_field(model_cls: type[BaseModel]) -> Callable[[Callable[..., BaseModel]], property]:
    def decorator(_f: Callable[..., BaseModel]):
        def wrapper(instance: BaseModel, key_name: str = None) -> BaseModel:
            if not key_name:
                key_name = f"{model_cls.__name__.lower()}_id"
            model_id = getattr(instance, key_name)
            return instance.client.fetch_from_api_by_id(model_cls, model_id) if model_id else None

        return property(wrapper)

    return decorator


def related_list_field(model_cls: type[BaseModel]) -> Callable[[Callable[..., BaseModel]], property]:
    def decorator(_f: Callable[..., BaseModel]):
        def wrapper(instance: BaseModel, key_name: str = None) -> list[BaseModel]:
            if not key_name:
                key_name = f"{model_cls.__name__.lower()}_ids"
            model_ids = getattr(instance, key_name)
            if not model_ids:
                return []
            valid_model_ids = [model_id for model_id in model_ids if model_id]
            return [instance.client.fetch_from_api_by_id(model_cls, model_id) for model_id in valid_model_ids]

        return property(wrapper)

    return decorator
