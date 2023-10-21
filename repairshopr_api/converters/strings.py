import re


def snake_case(input_string: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", input_string).lower()
