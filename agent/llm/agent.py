import logging
import os
import time
from pathlib import Path

import openai
from openai import OpenAI
from dotenv import load_dotenv

from ..agent_tools.build_tools import get_registry
from .prompts import get_prompt

# 显式指向 agent/.env，保证从任意工作目录运行都能读到密钥
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "deepseek-flash"

logger = logging.getLogger("miniagent")

# LLM 调用重试：最多 3 次尝试，指数退避 1s/2s/4s；仅对可重试错误（网络/限流/5xx）
MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.0


def _retryable(exc: Exception) -> bool:
    """仅对幂等可重试的错误退避重试：连接错误、限流、5xx、超时。"""
    if isinstance(exc, openai.APIConnectionError):
        return True
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and getattr(exc, "status_code", 0) >= 500:
        return True
    return isinstance(exc, TimeoutError)


def _log_usage(tag: str, usage) -> None:
    if usage is None:
        return
    logger.info(
        "%s usage: prompt=%s completion=%s total=%s",
        tag,
        getattr(usage, "prompt_tokens", "?"),
        getattr(usage, "completion_tokens", "?"),
        getattr(usage, "total_tokens", "?"),
    )


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
    last_exc: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools,
                stream=stream,
                stream_options={"include_usage": True} if stream else None,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
            )
        except Exception as exc:  # noqa: BLE001  按 _retryable 判定是否退避重试
            if not _retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            last_exc = exc
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "LLM 调用失败（%s: %s），%.1fs 后进行第 %d/%d 次重试",
                type(exc).__name__, exc, delay, attempt + 1, MAX_ATTEMPTS - 1,
            )
            time.sleep(delay)
    raise last_exc  # 理论不可达，保险起见


def get_llm_res(client: OpenAI, messages: list[dict], tools: list[dict] | None = None) -> str:
    """单轮非流式问答，返回文本内容。"""
    response = _create(client, messages, tools, stream=False)
    _log_usage("llm", getattr(response, "usage", None))
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
    usage = None

    for chunk in response:
        u = getattr(chunk, "usage", None)
        if u is not None:  # include_usage 时最后一个 chunk 带 usage 且 choices 为空
            usage = u
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
    _log_usage("stream_llm", usage)
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
