import json
from dataclasses import dataclass, asdict
from typing import Callable, Literal

from ..agent_tools.build_tools import get_registry
from ..dbase import query_database  # noqa: F401  导入即注册数据库工具
from .agent import stream_llm_res

StepType = Literal["reasoning", "tool_call", "tool_result", "answer"]


@dataclass
class AgentStep:
    """agent 执行过程中的一个步骤，供前端可视化渲染。"""

    type: StepType
    content: str = ""
    tool_name: str = ""
    tool_args: dict | None = None
    tool_result: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


StepCallback = Callable[[AgentStep], None]


def run_agent(
    client,
    messages: list[dict],
    tools: list[dict] | None = None,
    step_callback: StepCallback | None = None,
    max_rounds: int = 10,
) -> str:
    """多轮循环：LLM 输出 → 解析 tool_calls → 执行工具 → 回填结果，直到无工具调用或超限。

    每一步通过 step_callback 向外推送 AgentStep；messages 会在原地追加历史。
    """
    registry = get_registry()

    def emit(step: AgentStep) -> None:
        if step_callback:
            step_callback(step)

    def on_reasoning(fragment: str) -> None:
        emit(AgentStep(type="reasoning", content=fragment))

    for _ in range(max_rounds):
        content, tool_calls, _ = stream_llm_res(client, messages, tools, on_reasoning)

        if not tool_calls:
            messages.append({"role": "assistant", "content": content})
            emit(AgentStep(type="answer", content=content))
            return content

        messages.append({
            "role": "assistant",
            "content": content or None,
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}

            emit(AgentStep(type="tool_call", tool_name=name, tool_args=args))

            func = registry.get(name)
            if func is None:
                result = f"工具 {name} 未注册"
            else:
                try:
                    result = func(**args)
                except Exception as exc:  # noqa: BLE001
                    result = f"工具 {name} 执行异常: {exc}"

            result_str = str(result)
            emit(AgentStep(type="tool_result", tool_name=name, tool_result=result_str))
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

    return "已达到最大轮数上限，任务未完成"


if __name__ == "__main__":
    from .agent import create_llm, system_msg, user_msg

    client = create_llm()
    messages = [system_msg(), user_msg("你好，1+1 等于几？")]

    def show(step: AgentStep) -> None:
        if step.type == "reasoning":
            print(f"[思考] {step.content}", end="")
        elif step.type == "tool_call":
            print(f"\n[调用] {step.tool_name}({step.tool_args})")
        elif step.type == "tool_result":
            print(f"[结果] {step.tool_result}")
        else:
            print(f"\n[回答] {step.content}")

    print(run_agent(client, messages, step_callback=show))
