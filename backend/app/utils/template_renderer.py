from typing import Any

from jinja2 import ChainableUndefined, Environment


_environment = Environment(undefined=ChainableUndefined, autoescape=False)


def render_template_object(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _environment.from_string(value).render(**context)
    if isinstance(value, dict):
        return {key: render_template_object(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template_object(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(render_template_object(item, context) for item in value)
    return value
