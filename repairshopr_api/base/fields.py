from datetime import date, datetime
from typing import Callable

from repairshopr_api.base.model import BaseModel
from repairshopr_api.converters.strings import snake_case
from repairshopr_api.type_defs import JsonObject, is_json_object

ID_SUFFIX = "_id"
PLURAL_SUFFIX = "s"


def related_field(
    model_cls: type[BaseModel],
) -> Callable[[Callable[..., BaseModel]], property]:
    def build_id_key(default_key: str | None) -> str:
        return (
            default_key if default_key else f"{model_cls.__name__.lower()}{ID_SUFFIX}"
        )

    def fetch_single_related_model(
        instance: BaseModel, model_id: int
    ) -> BaseModel | None:
        return (
            instance.rs_client.get_model_by_id(model_cls, model_id)
            if model_id
            else None
        )

    def fetch_multiple_related_models(
        instance: BaseModel, model_ids: list[int]
    ) -> list[JsonObject]:
        valid_model_ids = [model_id for model_id in model_ids if model_id]
        return [
            instance.rs_client.fetch_from_api_by_id(model_cls, model_id)
            for model_id in valid_model_ids
        ]

    def is_invoice_line_item_model() -> bool:
        return model_cls.__name__ == "LineItem" and "invoice" in model_cls.__module__

    def fetch_related_models_by_parent(
        instance: BaseModel, query_params: dict[str, int | None]
    ) -> list[JsonObject]:
        def normalize_related_payload(candidate: object) -> JsonObject | None:
            if not isinstance(candidate, dict):
                return None

            normalized: JsonObject = {}
            for key, value in candidate.items():
                if not isinstance(key, str):
                    return None

                if isinstance(value, (datetime, date)):
                    normalized[key] = value.isoformat()
                else:
                    normalized[key] = value

            return normalized if is_json_object(normalized) else None

        if is_invoice_line_item_model():
            instance.rs_client.prefetch_line_items()

        related_models: list[JsonObject] = []
        page = 1
        while True:
            page_params = dict(query_params)
            if page > 1:
                page_params["page"] = page

            results, meta_data = instance.rs_client.fetch_from_api(
                snake_case(model_cls.__name__), params=page_params
            )

            for result in results:
                normalized_result = normalize_related_payload(result)
                if normalized_result is None:
                    continue

                result_id = normalized_result.get("id")
                if isinstance(result_id, int):
                    cache_key = f"{model_cls.__name__.lower()}_{result_id}"
                    # noinspection PyProtectedMember
                    instance.rs_client._cache[cache_key] = normalized_result
                related_models.append(normalized_result)

            if not isinstance(meta_data, dict):
                break

            total_pages = meta_data.get("total_pages")
            if not isinstance(total_pages, int) or page >= total_pages:
                break
            page += 1

        return related_models

    def decorator(_f: Callable[..., BaseModel]) -> property:
        def wrapper(
            instance: BaseModel, id_key: str | None = None
        ) -> BaseModel | list[JsonObject] | None:
            id_key = build_id_key(id_key)

            if hasattr(instance, id_key):
                model_id = getattr(instance, id_key)
                return fetch_single_related_model(instance, model_id)

            else:
                model_ids = getattr(instance, f"{id_key}{PLURAL_SUFFIX}", [])

                if model_ids:
                    return fetch_multiple_related_models(instance, model_ids)

                query_params = {
                    f"{type(instance).__name__.lower()}{ID_SUFFIX}": getattr(
                        instance, "id", None
                    )
                }
                return fetch_related_models_by_parent(instance, query_params)

        return property(wrapper)

    return decorator
