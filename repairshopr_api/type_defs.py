from __future__ import annotations

from typing import TypeGuard

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
type JsonObject = dict[str, JsonValue]
type JsonArray = list[JsonValue]

type QueryParamValue = str | int | float | bool | None
type QueryParams = dict[str, QueryParamValue]


def is_json_scalar(value: object) -> TypeGuard[JsonScalar]:
    return value is None or isinstance(value, (str, int, float, bool))


def is_query_param_value(value: object) -> TypeGuard[QueryParamValue]:
    return value is None or isinstance(value, (str, int, float, bool))


def is_query_params(value: object) -> TypeGuard[QueryParams]:
    return isinstance(value, dict) and all(isinstance(key, str) and is_query_param_value(item) for key, item in value.items())


def is_json_value(value: object) -> TypeGuard[JsonValue]:
    if is_json_scalar(value):
        return True
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_value(item) for key, item in value.items())
    return False


def is_json_object(value: object) -> TypeGuard[JsonObject]:
    return isinstance(value, dict) and all(isinstance(key, str) and is_json_value(item) for key, item in value.items())


def is_json_array(value: object) -> TypeGuard[JsonArray]:
    return isinstance(value, list) and all(is_json_value(item) for item in value)
