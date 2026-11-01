"""短固定工作流注册表：@workflow 注册、按名发现与统一执行。"""

_WORKFLOW_REGISTRY: dict[str, dict] = {}


def workflow(description: str = ""):
    """装饰器：把模块级函数注册为可被意图路由选择的工作流。"""

    def decorator(func):
        _WORKFLOW_REGISTRY[func.__name__] = {
            "name": func.__name__,
            "description": description,
            "func": func,
        }
        return func

    return decorator


def get_workflow(name: str) -> dict:
    """按名称取工作流条目，未知名称抛出含可用列表的错误。"""
    if name not in _WORKFLOW_REGISTRY:
        raise KeyError(f"工作流 {name} 未注册，可用: {sorted(_WORKFLOW_REGISTRY)}")
    return _WORKFLOW_REGISTRY[name]


def list_workflows() -> list[dict]:
    """返回全部已注册工作流的名称与描述，供 LLM 编排与前端展示。"""
    return [
        {"name": w["name"], "description": w["description"]}
        for w in _WORKFLOW_REGISTRY.values()
    ]


def run_workflow(name: str, **kwargs):
    """统一执行入口：查注册表并调用对应工作流函数。"""
    item = get_workflow(name)
    return item["func"](**kwargs)
