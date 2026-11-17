"""上下文长度管理：按字符预算裁剪历史消息，保证结构合法。

规则：
- 第一条 system 消息（角色提示词）永远保留；
- assistant(tool_calls) 与其后对应的 role=tool 结果不可拆散，否则 API 会拒绝；
- 从尾部保留最新消息，预算内尽量多留；正确性优先于精确预算（边界配对可轻微超出）。
- summarize_fn 提供时，被裁掉的旧消息先压缩为一条摘要记忆再丢弃（P2，默认关闭）。
"""
from collections.abc import Callable

DEFAULT_MAX_CHARS = 30000  # messages 总内容字符预算
_MAX_SUMMARY_INPUT = 8000  # 交给摘要函数的原文上限，防止摘要调用自身超上下文


def _msg_size(msg: dict) -> int:
    size = len(msg.get("content") or "")
    for tc in msg.get("tool_calls") or []:
        size += len(tc["function"]["arguments"])
    return size


def _render_evicted(evicted: list[dict]) -> str:
    """把被裁消息拼为摘要输入文本（role: content），超长截断。"""
    lines = []
    for m in evicted:
        text = (m.get("content") or "").strip()
        if text:
            lines.append(f"{m.get('role', '?')}: {text}")
    out = "\n".join(lines)
    return out[:_MAX_SUMMARY_INPUT]


def trim_messages(
    messages: list[dict],
    max_chars: int = DEFAULT_MAX_CHARS,
    summarize_fn: Callable[[str], str] | None = None,
) -> list[dict]:
    """返回裁剪后的新列表；未超预算时原样返回。调用方需自行替换（如 messages[:] = ...）。

    summarize_fn：接收被裁旧消息的文本，返回摘要。提供时被裁内容压缩为一条
    system 记忆插入保留区开头；摘要失败则退回直接丢弃（与不传时一致）。
    """
    if len(messages) <= 1:
        return messages
    if sum(_msg_size(m) for m in messages) <= max_chars:
        return messages

    # 从尾部累计，找最小保留起点（跳过 system[0]，它不计入预算）
    start, acc = len(messages), 0
    for i in range(len(messages) - 1, 0, -1):
        size = _msg_size(messages[i])
        if acc + size > max_chars:
            break
        acc += size
        start = i
    start = max(start, 1)

    # 边界修正：保留区不能以 role=tool 开头，否则对应 assistant 被裁掉、配对撕裂
    while start > 1 and messages[start].get("role") == "tool":
        j = start - 1
        while j > 0 and messages[j].get("role") == "tool":
            j -= 1
        if j > 0 and messages[j].get("role") == "assistant":
            start = j  # 把配对的 assistant 一并纳入保留区
            break
        break  # 找不到配对 assistant（异常序列），不再修正

    kept = [messages[0]] + messages[start:]

    if summarize_fn is not None and start > 1:
        try:
            summary = summarize_fn(_render_evicted(messages[1:start])).strip()
        except Exception:  # noqa: BLE001  摘要失败退回直接丢弃
            summary = ""
        if summary:
            kept.insert(1, {"role": "system", "content": f"[早前对话摘要]\n{summary}"})

    return kept
