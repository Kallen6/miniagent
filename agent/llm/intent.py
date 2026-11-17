"""意图识别：将用户消息分类，置信度足够时路由到已注册工作流。

detect_intent(text, client=None)：
- client=None → 占位实现（不调用 LLM，恒返回通用对话），保持向后兼容；
- 传入 LLM client → 真实分类（候选工作流 + JSON 输出），失败自动回退占位。

route_to_workflow(text, client, threshold=0.7)：路由决策入口，
仅当 workflow 名称有效且 confidence 达阈值时返回 workflow 名，否则 None。
"""
import json
import logging
import re
from dataclasses import dataclass

from ..workflows import list_workflows
from .agent import get_llm_res

logger = logging.getLogger("miniagent")

_INTENT_PROMPT = """你是意图分类器。根据用户消息判断最合适的处理方式。
候选工作流（名称: 描述）：
{candidates}

若无合适的工作流，intent 填 general_chat、workflow 填 null。
只输出一个 JSON 对象，不要输出其他内容，格式：
{{"intent": "<general_chat|workflow>", "workflow": "<工作流名或null>", "confidence": <0-1 之间的小数>, "reason": "<一句话说明>"}}"""


@dataclass
class IntentResult:
    """意图识别结果：意图类别、目标工作流、置信度与说明。"""

    intent: str
    workflow: str | None
    confidence: float
    reason: str


def _placeholder() -> IntentResult:
    return IntentResult(
        intent="general_chat",
        workflow=None,
        confidence=0.0,
        reason="意图识别未启用（未提供 LLM 客户端），默认返回通用对话",
    )


def _extract_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("LLM 输出中未找到 JSON 对象")
    return json.loads(match.group(0))


def detect_intent(text: str, client=None) -> IntentResult:
    """识别用户消息意图；client 为 None 时返回占位结果（不调用 LLM）。"""
    if client is None:
        return _placeholder()
    try:
        candidates = "\n".join(
            f"- {w['name']}: {w['description'] or '(无描述)'}" for w in list_workflows()
        ) or "(无已注册工作流)"
        raw = get_llm_res(client, [
            {"role": "system", "content": _INTENT_PROMPT.format(candidates=candidates)},
            {"role": "user", "content": text},
        ])
        data = _extract_json(raw or "")
        return IntentResult(
            intent=str(data.get("intent") or "general_chat"),
            workflow=str(data["workflow"]) if data.get("workflow") else None,
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0)))),
            reason=str(data.get("reason") or ""),
        )
    except Exception as exc:  # noqa: BLE001  识别失败不影响主链路
        logger.warning("意图识别失败，回退通用对话: %s", exc)
        return _placeholder()


def route_to_workflow(text: str, client, threshold: float = 0.7) -> str | None:
    """路由决策：命中已注册工作流且置信度达阈值时返回工作流名，否则 None。"""
    result = detect_intent(text, client)
    names = {w["name"] for w in list_workflows()}
    if result.workflow in names and result.confidence >= threshold:
        logger.info(
            "意图路由命中 workflow=%s confidence=%.2f reason=%s",
            result.workflow, result.confidence, result.reason,
        )
        return result.workflow
    return None
