from typing import Callable

from repairshopr_api.base.model import BaseModel


def related_field(model_cls: type[BaseModel]) -> Callable[[Callable[..., BaseModel]], property]:
    def decorator(_f: Callable[..., BaseModel]):
        def wrapper(instance: BaseModel) -> BaseModel:
            model_id = getattr(instance, f"{model_cls.__name__.lower()}_id")
            return instance.client.fetch_from_api_by_id(model_cls, model_id) if model_id else None

        return property(wrapper)

    return decorator
