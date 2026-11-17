"""服务安全：API Key 鉴权 + 内存令牌桶限流。

鉴权规则：
- agent/.env 配置了 AGENT_API_KEY 时，/api/v1 与 /ws/chat 必须携带该 key：
  HTTP 用 X-API-Key 请求头；WebSocket 支持请求头或 ?api_key= 查询参数
  （浏览器原生 WebSocket 无法自定义请求头）；
- 未配置时本地放行（开发模式，保持既有用法向后兼容）。

限流规则：
- 内存令牌桶，单进程部署下足够，不引入 redis；
- 按调用方身份限流：携带合法 key 时按 key 计，否则按客户端 IP 计；
- 默认容量 20、每分钟补充 20 个（可用 AGENT_RATE_LIMIT_PER_MIN 调整）。
"""
import logging
import os
import threading
import time

from fastapi import HTTPException, Request, Security, WebSocket, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger("miniagent")

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_DEFAULT_RATE_PER_MIN = 20.0


class TokenBucket:
    """按 key 的令牌桶：突发容量 capacity，按 rate_per_min 匀速补充。"""

    def __init__(self, rate_per_min: float, capacity: int):
        self._rate = rate_per_min / 60.0  # 每秒补充数
        self._capacity = float(capacity)
        self._tokens: dict[str, tuple[float, float]] = {}  # key -> (余量, 上次时间)
        self._lock = threading.Lock()

    def try_acquire(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._tokens.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._rate)
            if tokens >= 1.0:
                self._tokens[key] = (tokens - 1.0, now)
                return True
            self._tokens[key] = (tokens, now)
            return False


def _rate_per_min() -> float:
    try:
        return float(os.getenv("AGENT_RATE_LIMIT_PER_MIN") or _DEFAULT_RATE_PER_MIN)
    except ValueError:
        return _DEFAULT_RATE_PER_MIN


_bucket = TokenBucket(_rate_per_min(), int(_rate_per_min()))
_configured_key = (os.getenv("AGENT_API_KEY") or "").strip() or None

if _configured_key:
    logger.info("已启用 API Key 鉴权（AGENT_API_KEY）")
else:
    logger.warning("AGENT_API_KEY 未配置，鉴权关闭（开发模式，仅限本地使用）")


def _identity(key: str | None, fallback: str | None) -> str:
    return f"key:{key}" if key else f"ip:{fallback or 'unknown'}"


async def require_api_key(
    request: Request,
    key: str | None = Security(_API_KEY_HEADER),
) -> None:
    """FastAPI 依赖：鉴权 + 限流，失败分别抛 401 / 429。"""
    expected = _configured_key
    if expected is None:
        ident = _identity(None, request.client.host if request.client else None)
    elif key == expected:
        ident = _identity(key, None)
    else:
        logger.warning("鉴权失败：来自 %s 的无效 API Key", request.client.host if request.client else "?")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效的 API Key")

    if not _bucket.try_acquire(ident):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "请求过于频繁，请稍后再试")


def ws_check(ws: WebSocket) -> str | None:
    """WS 握手检查：鉴权 + 握手限流。通过返回限流身份，拒绝返回 None。"""
    expected = _configured_key
    key = ws.headers.get("x-api-key") or ws.query_params.get("api_key")
    if expected is None:
        ident = _identity(None, ws.client.host if ws.client else None)
    elif key == expected:
        ident = _identity(key, None)
    else:
        return None
    return ident if _bucket.try_acquire(ident) else None


def ws_rate_ok(ident: str) -> bool:
    """WS 每条消息的限流检查（握手身份复用）。"""
    return _bucket.try_acquire(ident)
