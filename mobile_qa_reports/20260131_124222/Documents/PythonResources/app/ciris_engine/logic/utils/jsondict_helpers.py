"""
Helper functions for type-safe JSONDict access.

These helpers provide type narrowing for MyPy when working with JSONDict/JSONValue types.
Use these instead of direct dict access when you need to narrow union types.
"""

from typing import Any, Dict, List, Optional, TypeVar, Union, cast, overload

from ciris_engine.schemas.types import JSONDict, JSONValue

T = TypeVar("T")


@overload
def get_str(data: JSONDict, key: str, default: str = "") -> str: ...


@overload
def get_str(data: dict[str, object], key: str, default: str = "") -> str: ...


def get_str(data: JSONDict | dict[str, object], key: str, default: str = "") -> str:
    """
    Get a string value from JSONDict with type narrowing.

    Args:
        data: The JSONDict to access
        key: The key to retrieve
        default: Default value if key is missing or not a string

    Returns:
        String value, narrowed from JSONValue union type
    """
    value = data.get(key, default)
    if isinstance(value, str):
        return value
    return default


@overload
def get_str_optional(data: JSONDict, key: str) -> Optional[str]: ...


@overload
def get_str_optional(data: dict[str, object], key: str) -> Optional[str]: ...


def get_str_optional(data: JSONDict | dict[str, object], key: str) -> Optional[str]:
    """
    Get an optional string value from JSONDict.

    Args:
        data: The JSONDict to access
        key: The key to retrieve

    Returns:
        String value or None if key is missing or not a string
    """
    value = data.get(key)
    if isinstance(value, str):
        return value
    return None


def get_int(data: JSONDict, key: str, default: int = 0) -> int:
    """
    Get an integer value from JSONDict with type narrowing.

    Args:
        data: The JSONDict to access
        key: The key to retrieve
        default: Default value if key is missing or not an int

    Returns:
        Integer value, narrowed from JSONValue union type
    """
    value = data.get(key, default)
    if isinstance(value, int) and not isinstance(value, bool):  # bool is subclass of int
        return value
    return default


def get_int_optional(data: JSONDict, key: str) -> Optional[int]:
    """
    Get an optional integer value from JSONDict.

    Args:
        data: The JSONDict to access
        key: The key to retrieve

    Returns:
        Integer value or None if key is missing or not an int
    """
    value = data.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def get_float(data: JSONDict, key: str, default: float = 0.0) -> float:
    """
    Get a float value from JSONDict with type narrowing.

    Args:
        data: The JSONDict to access
        key: The key to retrieve
        default: Default value if key is missing or not a float

    Returns:
        Float value, narrowed from JSONValue union type
    """
    value = data.get(key, default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def get_float_optional(data: JSONDict, key: str) -> Optional[float]:
    """
    Get an optional float value from JSONDict.

    Args:
        data: The JSONDict to access
        key: The key to retrieve

    Returns:
        Float value or None if key is missing or not a numeric type
    """
    value = data.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def get_bool(data: JSONDict, key: str, default: bool = False) -> bool:
    """
    Get a boolean value from JSONDict with type narrowing.

    Args:
        data: The JSONDict to access
        key: The key to retrieve
        default: Default value if key is missing or not a bool

    Returns:
        Boolean value, narrowed from JSONValue union type
    """
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    return default


def get_bool_optional(data: JSONDict, key: str) -> Optional[bool]:
    """
    Get an optional boolean value from JSONDict.

    Args:
        data: The JSONDict to access
        key: The key to retrieve

    Returns:
        Boolean value or None if key is missing or not a bool
    """
    value = data.get(key)
    if isinstance(value, bool):
        return value
    return None


def get_list(data: JSONDict, key: str, default: Optional[List[Any]] = None) -> List[Any]:
    """
    Get a list value from JSONDict with type narrowing.

    Args:
        data: The JSONDict to access
        key: The key to retrieve
        default: Default value if key is missing or not a list

    Returns:
        List value, narrowed from JSONValue union type
    """
    if default is None:
        default = []
    value = data.get(key, default)
    if isinstance(value, list):
        return value
    return default


def get_list_optional(data: JSONDict, key: str) -> Optional[List[Any]]:
    """
    Get an optional list value from JSONDict.

    Args:
        data: The JSONDict to access
        key: The key to retrieve

    Returns:
        List value or None if key is missing or not a list
    """
    value = data.get(key)
    if isinstance(value, list):
        return value
    return None


def get_dict(data: JSONDict, key: str, default: Optional[JSONDict] = None) -> JSONDict:
    """
    Get a dict value from JSONDict with type narrowing.

    Args:
        data: The JSONDict to access
        key: The key to retrieve
        default: Default value if key is missing or not a dict

    Returns:
        Dict value, narrowed from JSONValue union type
    """
    if default is None:
        default = {}
    value = data.get(key, default)
    if isinstance(value, dict):
        return cast(JSONDict, value)
    return default


def get_dict_optional(data: JSONDict, key: str) -> Optional[JSONDict]:
    """
    Get an optional dict value from JSONDict.

    Args:
        data: The JSONDict to access
        key: The key to retrieve

    Returns:
        Dict value or None if key is missing or not a dict
    """
    value = data.get(key)
    if isinstance(value, dict):
        return cast(JSONDict, value)
    return None


def safe_cast_dict(value: Any) -> JSONDict:
    """
    Safely cast a value to JSONDict.

    Args:
        value: Value to cast

    Returns:
        JSONDict or empty dict if value is not a dict
    """
    if isinstance(value, dict):
        return cast(JSONDict, value)
    return {}


def safe_cast_list(value: Any) -> List[Any]:
    """
    Safely cast a value to list.

    Args:
        value: Value to cast

    Returns:
        List or empty list if value is not a list
    """
    if isinstance(value, list):
        return value
    return []


__all__ = [
    "get_str",
    "get_str_optional",
    "get_int",
    "get_int_optional",
    "get_float",
    "get_float_optional",
    "get_bool",
    "get_bool_optional",
    "get_list",
    "get_list_optional",
    "get_dict",
    "get_dict_optional",
    "safe_cast_dict",
    "safe_cast_list",
]
