import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from typing import Callable, Literal

from ..agent_tools.build_tools import get_registry, get_tool_meta
from ..dbase import query_database  # noqa: F401  导入即注册数据库工具
from ..fs import file_ops  # noqa: F401  导入即注册文件 CRUD 工具（沙箱限制见 agent/fs/sandbox.py）
from ..task.runner import run_tool
from ..workflows import tools as workflow_tools  # noqa: F401  导入即把工作流注册为慢工具
from .agent import stream_llm_res
from .context import DEFAULT_MAX_CHARS, trim_messages

logger = logging.getLogger("miniagent")

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


class AgentCancelled(Exception):
    """run_agent 因 cancel_event 置位而协作式取消（线程无法强杀，轮间检查退出）。"""


def _error_result(code: str, message: str, **extra) -> str:
    """构造结构化错误结果，回填给模型促使其修正后重试。"""
    return json.dumps({"error": code, "message": message, **extra}, ensure_ascii=False)


def run_agent(
    client,
    messages: list[dict],
    tools: list[dict] | None = None,
    step_callback: StepCallback | None = None,
    max_rounds: int = 10,
    max_context_chars: int | None = DEFAULT_MAX_CHARS,
    cancel_event: threading.Event | None = None,
    summarizer: Callable[[str], str] | None = None,
) -> str:
    """多轮循环：LLM 输出 → 解析 tool_calls → 执行工具 → 回填结果，直到无工具调用或超限。

    每一步通过 step_callback 向外推送 AgentStep；messages 会在原地追加历史。
    max_context_chars：每轮开始前按字符预算裁剪历史（None 关闭），防止长对话撑爆上下文窗口。
    cancel_event：置位后在下一轮开始时抛出 AgentCancelled 协作式取消（运行中的工具无法强杀）。
    summarizer：可选。裁剪时把被裁旧消息压缩为摘要记忆保留（P2 开关，默认 None 直接丢弃）；
      典型实现：lambda text: get_llm_res(client, [{"role": "system", "content": "总结对话要点"},
      {"role": "user", "content": text}])。
    """
    registry = get_registry()
    tool_meta = get_tool_meta()

    def emit(step: AgentStep) -> None:
        if step_callback:
            step_callback(step)

    def on_reasoning(fragment: str) -> None:
        emit(AgentStep(type="reasoning", content=fragment))

    for round_no in range(max_rounds):
        if cancel_event is not None and cancel_event.is_set():
            logger.info("run_agent 在第 %d 轮前被取消", round_no + 1)
            raise AgentCancelled("任务已取消")

        if max_context_chars is not None:
            messages[:] = trim_messages(messages, max_context_chars, summarizer)
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
                parse_ok = True
            except json.JSONDecodeError as exc:
                args, parse_ok = {}, False  # 解析失败：不执行工具，回填错误让模型修正
                logger.warning("round %d 工具 %s 参数解析失败: %s", round_no + 1, name, exc)

            emit(AgentStep(type="tool_call", tool_name=name, tool_args=args))

            func = registry.get(name)
            if func is None:
                result_str = _error_result("unknown_tool", f"工具 {name} 未注册")
            elif not parse_ok:
                result_str = _error_result(
                    "invalid_json_args",
                    f"工具 {name} 的参数不是合法 JSON，请修正后重试",
                )
            else:
                missing = [
                    k for k in tool_meta.get(name, {}).get("required", [])
                    if k not in args
                ]
                if missing:
                    result_str = _error_result(
                        "missing_required_args",
                        f"缺少必填参数: {', '.join(missing)}",
                        missing=missing,
                    )
                else:
                    t0 = time.monotonic()
                    result_str = run_tool(
                        func,
                        args,
                        timeout=tool_meta.get(name, {}).get("timeout", 60.0),
                        slow=tool_meta.get(name, {}).get("slow", False),
                    )
                    logger.info(
                        "round %d tool=%s cost=%.2fs", round_no + 1, name, time.monotonic() - t0,
                    )

            emit(AgentStep(type="tool_result", tool_name=name, tool_result=result_str))
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

    logger.warning("run_agent 达到最大轮数上限 (%d)", max_rounds)
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            # 最近一轮模型已输出正文（可能伴随未完成的工具调用），直接作为结果
            emit(AgentStep(type="answer", content=msg["content"]))
            return msg["content"]
    return "已达到最大轮数上限，任务未完成；可基于当前进展继续追问让 agent 收尾"


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
