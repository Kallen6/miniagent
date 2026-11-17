"""工具执行器：快/慢工具分流到独立线程池，带超时等待。

设计要点：
- 与 Web/API 层的默认 asyncio executor 隔离，避免慢工作流挤占对话请求；
- 快池（DB 查询等）与慢池（workflow 等长任务）分开限流，互不影响；
- 超时只表示"放弃等待"。Python 线程无法被强制终止，后台线程会运行至自然结束；
  需要可强杀的长任务请改用子进程（如 CdpTools 的一任务一进程模型）。
- 结果标准化（P0）：dict/list 序列化为合法 JSON；所有结果限长，防止稀释上下文。
"""
import json
from concurrent.futures import ThreadPoolExecutor

FAST_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool-fast")
SLOW_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool-slow")

DEFAULT_TIMEOUT = 60.0
MAX_TOOL_RESULT = 6000  # 工具结果字符上限，超出截断


def normalize_result(result) -> str:
    """统一工具结果为字符串：dict/list 转 JSON，超长截断。"""
    if isinstance(result, str):
        text = result
    elif isinstance(result, (dict, list)):
        try:
            text = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001  不可序列化的极端情况退化为 repr
            text = str(result)
    else:
        text = str(result)

    if len(text) > MAX_TOOL_RESULT:
        text = text[:MAX_TOOL_RESULT] + f"…[结果超长已截断，原始 {len(text)} 字符]"
    return text


def run_tool(func, args: dict, timeout: float = DEFAULT_TIMEOUT, slow: bool = False) -> str:
    """在对应线程池执行工具并等待，返回标准化结果字符串；超时/异常返回结构化 JSON 错误。"""
    pool = SLOW_EXECUTOR if slow else FAST_EXECUTOR
    future = pool.submit(func, **args)
    try:
        return normalize_result(future.result(timeout=timeout))
    except TimeoutError:
        return normalize_result(json.dumps(
            {"error": "timeout", "message": f"工具执行超过 {timeout:.0f}s，已中止等待"},
            ensure_ascii=False,
        ))
    except Exception as exc:  # noqa: BLE001
        return normalize_result(json.dumps(
            {"error": "exception", "message": str(exc)},
            ensure_ascii=False,
        ))
