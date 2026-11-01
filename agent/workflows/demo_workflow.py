"""占位工作流示例：验证注册、发现与执行闭环，CdpTools 网页工作流后续接入。"""
from .registry import workflow


@workflow(description="将文本转换为大写")
def text_upper(text: str) -> dict:
    return {"original": text, "upper": text.upper()}


@workflow(description="统计文本的字符数、单词数与行数")
def text_stats(text: str) -> dict:
    return {
        "chars": len(text),
        "words": len(text.split()),
        "lines": text.count("\n") + 1 if text else 0,
    }
