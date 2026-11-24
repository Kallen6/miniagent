"""路径安全沙箱：文件 CRUD 与未来 skills/插件的文件访问共用此校验。

策略：
- 白名单根目录：AGENT_FS_ROOTS（分号分隔多个）；未配置时默认 agent/data/workspace
- 相对路径一律解析到第一个根目录下；绝对路径必须在任一根目录内
- resolve() 跟随符号链接，链接逃逸出白名单即拒绝；跨盘符路径 is_relative_to 必然为 False
- 扩展名/文件名黑名单拦截 .env、.db、密钥等敏感文件
"""
import os
from pathlib import Path

# 项目根目录（agent/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROOT = PROJECT_ROOT / "agent" / "data" / "workspace"

# 禁止读写的敏感文件
DENIED_SUFFIXES = (
    ".env", ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo",
    ".key", ".pem", ".crt", ".cer", ".pfx", ".p12",
)
DENIED_NAME_PREFIXES = (".env",)  # 拦截 .env.local 等变体

# 编程式追加的根目录（skills/插件运行时注入用），叠加在 env 配置之上
_extra_roots: list[Path] = []


class SandboxError(Exception):
    """路径不在沙箱白名单内，或命中文件名限制。"""


def set_roots(paths) -> None:
    """编程式设置附加根目录（覆盖式追加；传空列表清空）。仅供测试与 skills/插件注入。"""
    global _extra_roots
    _extra_roots = [Path(p) for p in (paths or [])]


def get_roots() -> list[Path]:
    """返回当前生效的沙箱根目录（已 resolve、去重）。相对配置基于项目根目录解析。"""
    env = (os.getenv("AGENT_FS_ROOTS") or "").strip()
    parts = [p.strip() for p in env.split(";") if p.strip()]
    if not parts:
        parts = [str(DEFAULT_ROOT)]
    raw = [Path(p) for p in parts] + _extra_roots
    roots, seen = [], set()
    for r in raw:
        rp = (r if r.is_absolute() else PROJECT_ROOT / r).resolve()
        if rp not in seen:
            seen.add(rp)
            roots.append(rp)
    return roots


def check_path(path: str, for_write: bool = False) -> Path:
    """校验路径并返回 resolve 后的绝对路径；非法即抛 SandboxError。

    for_write 保留参数：未来支持按根目录配置只读策略（读工具不传、写工具必须传）。
    """
    if path is None or not str(path).strip():
        raise SandboxError("路径为空")
    p = Path(str(path))
    roots = get_roots()
    # 相对路径解析到第一个根目录；绝对路径直接参与白名单判定
    target = p if p.is_absolute() else roots[0] / p
    resolved = target.resolve()
    if not any(resolved.is_relative_to(root) for root in roots):
        raise SandboxError(f"路径不在允许的沙箱目录内：{path}")
    name = resolved.name.lower()
    if name.endswith(DENIED_SUFFIXES) or name.startswith(DENIED_NAME_PREFIXES):
        raise SandboxError(f"禁止访问敏感文件：{resolved.name}")
    return resolved


def display_path(resolved: Path) -> str:
    """返回相对其所属根目录的展示路径（跨根目录兜底返回绝对路径）。"""
    for root in get_roots():
        if resolved.is_relative_to(root):
            return resolved.relative_to(root).as_posix()
    return str(resolved)
