"""任务执行层：工具的快慢分流执行器与任务抽象（为后续 MQ 替换预留）。"""
from .runner import run_tool

__all__ = ["run_tool"]
