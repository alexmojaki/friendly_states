import re


def snake(camel_string):
    return re.sub(
        r"([a-z0-9])([A-Z])",
        lambda m: (m.group(1).lower() + "_" + m.group(2).lower()),
        camel_string,
    ).lower()
