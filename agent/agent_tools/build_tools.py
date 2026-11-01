import inspect
from typing import get_type_hints

PY_TO_JSON = {
    str: "string", int: "integer", float: "number",
    bool: "boolean", list: "array", dict: "object",
}

_TOOL_SCHEMAS: list[dict] = []
_TOOL_REGISTRY: dict[str, callable] = {}

def tool(description: str, param_descriptions: dict | None = None):
    def decorator(func):
        schema = _build_schema(func, description, param_descriptions)
        func.tool_schema = schema              # 与 discover_tools 的 hasattr 对齐
        _TOOL_SCHEMAS.append(schema)           # 自动收集
        _TOOL_REGISTRY[func.__name__] = func   # 自动注册
        return func
    return decorator

def _build_schema(func, description: str, param_descriptions: dict | None = None) -> dict:
    hints = get_type_hints(func)
    sig = inspect.signature(func)
    param_desc = param_descriptions or {}

    properties, required = {}, []
    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue

        py_type = hints.get(name, str)
        properties[name] = {
            "type": PY_TO_JSON.get(py_type, "string"),
            "description": param_desc.get(name, f"参数 {name}"),
        }
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def get_tools() -> list[dict]:
    return list(_TOOL_SCHEMAS)

def get_registry() -> dict:
    return dict(_TOOL_REGISTRY)


    
