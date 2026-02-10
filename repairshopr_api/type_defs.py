from __future__ import annotations

from typing import TypeAlias, TypeGuard

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
JsonArray: TypeAlias = list[JsonValue]

QueryParamValue: TypeAlias = str | int | float | bool | None
QueryParams: TypeAlias = dict[str, QueryParamValue]


def is_json_scalar(value: object) -> TypeGuard[JsonScalar]:
    return value is None or isinstance(value, (str, int, float, bool))


def is_query_param_value(value: object) -> TypeGuard[QueryParamValue]:
    return value is None or isinstance(value, (str, int, float, bool))


def is_query_params(value: object) -> TypeGuard[QueryParams]:
    return isinstance(value, dict) and all(
        isinstance(key, str) and is_query_param_value(item)
        for key, item in value.items()
    )


def is_json_value(value: object) -> TypeGuard[JsonValue]:
    if is_json_scalar(value):
        return True
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and is_json_value(item) for key, item in value.items()
        )
    return False


def is_json_object(value: object) -> TypeGuard[JsonObject]:
    return isinstance(value, dict) and all(
        isinstance(key, str) and is_json_value(item) for key, item in value.items()
    )


def is_json_array(value: object) -> TypeGuard[JsonArray]:
    return isinstance(value, list) and all(is_json_value(item) for item in value)
