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
         timeout: float = 60.0, slow: bool = False, public: bool = True):
    """工具装饰器：自动生成 Schema 并注册。

    timeout/slow 用于执行调度（快慢分流 + 超时）；public=False 表示私有工具，
    仅 get_tools(include_private=True) 场景可见（本地 WS 会话），对外 /api/v1 默认排除。
    """
    def decorator(func):
        schema, required = _build_schema(func, description, param_descriptions)
        func.tool_schema = schema              # 与 discover_tools 的 hasattr 对齐
        _TOOL_SCHEMAS.append(schema)           # 自动收集
        _TOOL_REGISTRY[func.__name__] = func   # 自动注册
        _TOOL_META[func.__name__] = {
            "timeout": timeout, "slow": slow, "public": public, "required": required,
        }
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

    schema = {
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
    return schema, required


def get_tools(include_private: bool = True) -> list[dict]:
    """返回工具 Schema 列表；include_private=False 时排除 private 工具（对外接口用）。"""
    if include_private:
        return list(_TOOL_SCHEMAS)
    return [
        s for s in _TOOL_SCHEMAS
        if _TOOL_META.get(s["function"]["name"], {}).get("public", True)
    ]


def get_registry() -> dict:
    return dict(_TOOL_REGISTRY)


def get_tool_meta() -> dict:
    """返回 {工具名: {timeout, slow, public, required}}，供执行器调度、可见性过滤与参数校验。"""
    return {name: dict(meta) for name, meta in _TOOL_META.items()}
