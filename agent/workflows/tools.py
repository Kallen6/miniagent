"""把已注册的短固定工作流包装为慢工具，供 agent 通过 function-calling 编排。

导入本模块即触发注册：每个 workflow 按其函数签名生成工具 Schema，
并标记为慢工具（走独立慢池 + 长超时），避免长工作流阻塞快工具与对话线程。
"""
from ..agent_tools.build_tools import tool
from .registry import get_workflow, list_workflows

WORKFLOW_TOOL_TIMEOUT = 300.0  # 秒，工作流按长任务处理


def _register_workflow_tools() -> None:
    for item in list_workflows():
        name = item["name"]
        func = get_workflow(name)["func"]
        tool(
            description=item["description"] or f"执行固定工作流 {name}",
            timeout=WORKFLOW_TOOL_TIMEOUT,
            slow=True,
        )(func)


_register_workflow_tools()
