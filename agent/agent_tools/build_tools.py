import inspect
from typing import get_type_hints

PY_TO_JSON = {
    str: "string", int: "integer", float: "number",
    bool: "boolean", list: "array", dict: "object",
}

_TOOL_SCHEMAS: list[dict] = []
_TOOL_REGISTRY: dict[str, callable] = {}
_TOOL_META: dict[str, dict] = {}


def tool(description: str, param_descriptions: dict | None = None,
         timeout: float = 60.0, slow: bool = False):
    """工具装饰器：自动生成 Schema 并注册；timeout/slow 用于执行调度（快慢分流 + 超时）。"""
    def decorator(func):
        schema = _build_schema(func, description, param_descriptions)
        func.tool_schema = schema              # 与 discover_tools 的 hasattr 对齐
        _TOOL_SCHEMAS.append(schema)           # 自动收集
        _TOOL_REGISTRY[func.__name__] = func   # 自动注册
        _TOOL_META[func.__name__] = {"timeout": timeout, "slow": slow}
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


def get_tool_meta() -> dict:
    """返回 {工具名: {"timeout": 秒, "slow": 是否慢工具}}，供执行器分流与超时控制。"""
    return dict(_TOOL_META)
