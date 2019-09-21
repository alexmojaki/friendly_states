import re


def snake(camel_string):
    result = re.sub(
        r"([a-z0-9])([A-Z])",
        lambda m: f"{m.group(1)}_{m.group(2)}",
        camel_string,
    ).lower()

    result = re.sub(
        r"([a-z])([0-9])",
        lambda m: f"{m.group(1)}_{m.group(2)}",
        result,
    )

    return result
