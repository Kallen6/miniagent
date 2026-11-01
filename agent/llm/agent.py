import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from ..agent_tools.build_tools import get_registry
from .prompts import get_prompt

# 显式指向 agent/.env，保证从任意工作目录运行都能读到密钥
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "deepseek-flash"


def system_msg(content: str | None = None, role: str = "default") -> dict[str, str]:
    """显式 content 优先；未传 content 时按 role 从角色库取提示词。"""
    if content is None:
        content = get_prompt(role)
    return {"role": "system", "content": content}


def user_msg(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def assistant_msg(content: str) -> dict[str, str]:
    return {"role": "assistant", "content": content}


def tool_msg(tool_call_id: str, content: str) -> dict[str, str]:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def create_llm() -> OpenAI:
    return OpenAI(api_key=os.getenv("API_KEY"), base_url=os.getenv("DS_URL"))


def _create(client: OpenAI, messages: list[dict], tools: list[dict] | None, stream: bool):
    return client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        stream=stream,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )


def get_llm_res(client: OpenAI, messages: list[dict], tools: list[dict] | None = None) -> str:
    """单轮非流式问答，返回文本内容。"""
    response = _create(client, messages, tools, stream=False)
    return response.choices[0].message.content


def stream_llm_res(
    client: OpenAI,
    messages: list[dict],
    tools: list[dict] | None = None,
    on_reasoning=None,
) -> tuple[str, list[dict], str]:
    """流式调用，返回 (content, tool_calls, reasoning)；思考片段经 on_reasoning 逐块回调。"""
    response = _create(client, messages, tools, stream=True)

    reasoning_parts: list[str] = []
    content_parts: list[str] = []
    tool_calls_acc: dict[int, dict] = {}

    for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        rc = getattr(delta, "reasoning_content", None)
        if rc:
            reasoning_parts.append(rc)
            if on_reasoning:
                on_reasoning(rc)

        c = getattr(delta, "content", None)
        if c:
            content_parts.append(c)

        tcs = getattr(delta, "tool_calls", None)
        if tcs:
            for tc in tcs:
                item = tool_calls_acc.setdefault(tc.index, {"id": None, "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    item["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        item["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        item["arguments"] += fn.arguments

    content = "".join(content_parts)
    reasoning = "".join(reasoning_parts)
    tool_calls = [
        {
            "id": tool_calls_acc[i]["id"],
            "type": "function",
            "function": {"name": tool_calls_acc[i]["name"], "arguments": tool_calls_acc[i]["arguments"]},
        }
        for i in sorted(tool_calls_acc)
    ]
    return content, tool_calls, reasoning


if __name__ == "__main__":
    print(get_registry())
