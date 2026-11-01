"""Prompt 角色库：按角色切换系统提示词，适应不同场景。"""

PROMPTS: dict[str, str] = {
    "default": "你是一个ai助手",
    "data_analyst": "你是一名数据分析助手，擅长解读数据库查询结果，回答保持简洁、结论先行。",
}


def get_prompt(role: str = "default") -> str:
    """按角色取提示词；未知角色抛出含可用角色列表的错误，避免静默用错。"""
    if role not in PROMPTS:
        raise KeyError(f"角色 {role} 未定义，可用角色: {sorted(PROMPTS)}")
    return PROMPTS[role]


def list_roles() -> list[str]:
    """返回全部可用角色名。"""
    return sorted(PROMPTS)


def register_prompt(name: str, prompt: str) -> None:
    """运行时注册或覆盖一个角色的提示词。"""
    PROMPTS[name] = prompt
