"""意图识别接口：本阶段仅定义接口与返回结构，识别逻辑后续接入。"""
from dataclasses import dataclass


@dataclass
class IntentResult:
    """意图识别结果：意图类别、目标工作流、置信度与说明。"""

    intent: str
    workflow: str | None
    confidence: float
    reason: str


def detect_intent(text: str) -> IntentResult:
    """占位实现：尚未接入真实识别逻辑，始终返回通用对话意图。"""
    return IntentResult(
        intent="general_chat",
        workflow=None,
        confidence=0.0,
        reason="意图识别逻辑尚未接入，默认返回通用对话",
    )
