"""受限文件 CRUD 工具：全部经过 sandbox.check_path 校验，默认仅本地会话可见（public=False）。"""
import functools
import json
import os
import shutil
import time
from itertools import islice
from pathlib import Path

from ..agent_tools.build_tools import tool
from .sandbox import SandboxError, check_path, display_path, get_roots

DEFAULT_MAX_READ = 1_048_576    # 1MB
DEFAULT_MAX_WRITE = 524_288     # 512KB
MAX_PAGE_LINES = 1000
MAX_LIST_ENTRIES = 200


def _limit(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


def _limits() -> tuple[int, int]:
    return _limit("AGENT_FS_MAX_READ_BYTES", DEFAULT_MAX_READ), \
        _limit("AGENT_FS_MAX_WRITE_BYTES", DEFAULT_MAX_WRITE)


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:8192]


def guard(fn):
    """把 SandboxError 转成 LLM 可读的错误消息，而非让异常中断多轮循环。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SandboxError as exc:
            return f"错误：{exc}"
    return wrapper


def _read_text(resolved: Path, max_read: int) -> tuple[str | None, str]:
    """读取文本内容；返回 (内容, 错误消息)，成功时错误消息为空串。"""
    if not resolved.is_file():
        return None, f"错误：文件不存在或不是普通文件：{display_path(resolved)}"
    size = resolved.stat().st_size
    if size > max_read:
        return None, f"错误：文件大小 {size} 字节超过读取上限 {max_read} 字节"
    data = resolved.read_bytes()
    if _is_binary(data):
        return None, "错误：疑似二进制文件，不支持读取"
    return data.decode("utf-8", errors="replace"), ""


@tool(
    description="读取沙箱白名单目录内的文本文件，按行号分页返回",
    param_descriptions={
        "path": "文件路径，相对路径基于沙箱根目录解析",
        "offset": "起始行号（从 0 计），默认 0",
        "limit": "最多返回的行数，默认 200，最大 1000",
    },
    timeout=15.0, public=False,
)
@guard
def file_read(path: str, offset: int = 0, limit: int = 200) -> str:
    max_read, _ = _limits()
    resolved = check_path(path)
    text, err = _read_text(resolved, max_read)
    if err:
        return err
    lines = text.splitlines()
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), MAX_PAGE_LINES))
    chunk = lines[offset:offset + limit]
    numbered = "\n".join(f"{offset + i + 1}:{line}" for i, line in enumerate(chunk))
    return json.dumps({
        "path": display_path(resolved),
        "total_lines": len(lines),
        "offset": offset,
        "returned": len(chunk),
        "truncated": offset + limit < len(lines),
        "content": numbered,
    }, ensure_ascii=False)


@tool(
    description="在沙箱白名单目录内创建或写入文本文件（支持覆盖/追加）",
    param_descriptions={
        "path": "目标文件路径，父目录不存在时自动创建",
        "content": "要写入的文本内容（UTF-8）",
        "mode": "写入模式：overwrite 覆盖（默认）/ append 追加",
    },
    timeout=15.0, public=False,
)
@guard
def file_write(path: str, content: str, mode: str = "overwrite") -> str:
    mode = (mode or "overwrite").lower()
    if mode not in ("overwrite", "append"):
        return f"错误：不支持的写入模式 {mode}，可选 overwrite / append"
    _, max_write = _limits()
    resolved = check_path(path, for_write=True)
    data = content.encode("utf-8")
    if mode == "append" and resolved.is_file():
        data = resolved.read_bytes() + data
    if len(data) > max_write:
        return f"错误：写入后大小 {len(data)} 字节超过上限 {max_write} 字节"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append":
        with open(resolved, "ab") as fh:
            fh.write(content.encode("utf-8"))
    else:
        resolved.write_bytes(content.encode("utf-8"))
    return json.dumps({
        "path": display_path(resolved),
        "mode": mode,
        "bytes": len(content.encode("utf-8")),
    }, ensure_ascii=False)


@tool(
    description="精确替换沙箱内文本文件的内容（old_str 必须在文件中唯一匹配）",
    param_descriptions={
        "path": "目标文件路径",
        "old_str": "要被替换的原文片段，必须在文件中恰好出现一次",
        "new_str": "替换后的新内容",
    },
    timeout=15.0, public=False,
)
@guard
def file_edit(path: str, old_str: str, new_str: str) -> str:
    _, max_write = _limits()
    resolved = check_path(path, for_write=True)
    text, err = _read_text(resolved, max_write)
    if err:
        return err
    count = text.count(old_str)
    if count == 0:
        return "错误：未找到待替换内容，请确认 old_str 与文件一致"
    if count > 1:
        return f"错误：old_str 匹配到 {count} 处，请补充上下文使其唯一"
    updated = text.replace(old_str, new_str, 1)
    if len(updated.encode("utf-8")) > max_write:
        return f"错误：编辑后大小超过上限 {max_write} 字节"
    resolved.write_bytes(updated.encode("utf-8"))  # 字节写入，避免 Windows 文本模式换行二次转换
    return json.dumps({"path": display_path(resolved), "replacements": 1}, ensure_ascii=False)


@tool(
    description="删除沙箱内文件或目录（移动到根目录 .trash/ 下，可恢复，不直接物理删除）",
    param_descriptions={"path": "要删除的文件或目录路径"},
    timeout=15.0, public=False,
)
@guard
def file_delete(path: str) -> str:
    resolved = check_path(path, for_write=True)
    if not resolved.exists():
        return f"错误：路径不存在：{display_path(resolved)}"
    trash_root = get_roots()[0] / ".trash"
    rel = display_path(resolved).replace("/", "_")
    dest = trash_root / f"{time.strftime('%Y%m%d%H%M%S')}_{rel}"
    if dest.exists():
        dest = trash_root / f"{dest.name}_{int(time.time())}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(resolved), str(dest))
    return json.dumps({
        "path": display_path(resolved),
        "moved_to": display_path(dest),
    }, ensure_ascii=False)


@tool(
    description="列出沙箱目录内的文件与子目录（支持通配符过滤）",
    param_descriptions={
        "path": "目录路径，默认沙箱根目录",
        "pattern": "glob 通配符，默认 * 列出全部；例如 *.py、data/*.txt",
    },
    timeout=15.0, public=False,
)
@guard
def file_list(path: str = ".", pattern: str = "*") -> str:
    resolved = check_path(path)
    if resolved.is_file():
        pattern = resolved.name
        resolved = resolved.parent
    if not resolved.is_dir():
        return f"错误：路径不是目录：{display_path(resolved)}"
    entries, truncated = [], False
    for item in islice(sorted(resolved.glob(pattern)), MAX_LIST_ENTRIES + 1):
        if item == resolved:
            continue
        if len(entries) >= MAX_LIST_ENTRIES:
            truncated = True
            break
        stat = item.stat()
        entries.append({
            "path": display_path(item),
            "type": "dir" if item.is_dir() else "file",
            "size": stat.st_size,
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        })
    return json.dumps({
        "dir": display_path(resolved),
        "count": len(entries),
        "truncated": truncated,
        "entries": entries,
    }, ensure_ascii=False)
