"""工作流层：注册、发现与统一执行。"""
from .registry import get_workflow, list_workflows, run_workflow, workflow
from . import demo_workflow  # noqa: F401  导入示例工作流以触发注册

__all__ = ["workflow", "get_workflow", "list_workflows", "run_workflow"]
