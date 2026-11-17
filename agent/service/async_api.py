"""对外异步服务：提交对话任务立即返回 task_id，结果异步产生、按需查询。

可靠性设计：
- 任务持久化到 SQLite（task_store.py），进程重启后历史任务仍可查询；
- _RUNNING 保存 asyncio.Task 引用，避免 fire-and-forget 任务被垃圾回收；
- asyncio.Semaphore 限制同时执行的任务数，防止提交洪峰打爆线程池与 LLM 配额；
- 取消采用协作式：cancel 端点置位 threading.Event，run_agent 在轮间检查退出；
  运行中的单个工具调用无法强杀（Python 线程限制），与 runner.py 注释一致。

安全：/api/v1 全部路由经 security.require_api_key 依赖（鉴权 + 限流）；
未配置 AGENT_API_KEY 时为开发模式（放行），配置后强制校验。
"""
import asyncio
import logging
import os
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..agent_tools.build_tools import get_tools
from ..llm.agent import create_llm, system_msg, user_msg
from ..llm.agent_loop import AgentCancelled, run_agent
from ..llm.intent import route_to_workflow
from .security import require_api_key
from .task_store import TERMINAL_STATUSES, TaskStore

logger = logging.getLogger("miniagent")

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])

MAX_TASKS = 200       # 历史任务保留上限（仅清理终态任务）
MAX_CONCURRENT = 4    # 同时执行的任务数上限


def _intent_routing_enabled() -> bool:
    """意图路由开关：AGENT_INTENT_ROUTING=1 时启用（默认关闭，避免额外 LLM 往返）。"""
    return os.getenv("AGENT_INTENT_ROUTING", "").strip().lower() in ("1", "true", "yes")


store = TaskStore()
_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
_RUNNING: dict[str, asyncio.Task] = {}          # task_id -> asyncio.Task（持引用防 GC）
_CANCEL_EVENTS: dict[str, threading.Event] = {}  # task_id -> 取消信号


class ChatRequest(BaseModel):
    message: str
    role: str = "default"


async def _execute(task_id: str, payload: ChatRequest, cancel_event: threading.Event) -> None:
    """在信号量限额内执行任务；终态写库，最后清理运行态引用。"""
    store.set_status(task_id, "running")

    def collect(step) -> None:
        store.append_step(task_id, step.to_dict())

    try:
        async with _semaphore:
            if cancel_event.is_set():
                raise AgentCancelled("任务在排队等待时被取消")
            client = create_llm()
            messages = [system_msg(role=payload.role), user_msg(payload.message)]
            tools = get_tools()
            if _intent_routing_enabled():
                # 意图路由（引导而非强制）：命中工作流时缩小工具集，引导 LLM 编排该工作流
                workflow = route_to_workflow(payload.message, client)
                if workflow is not None:
                    tools = [t for t in tools if t["function"]["name"] == workflow]
            result = await asyncio.to_thread(
                run_agent, client, messages, tools, collect,
                cancel_event=cancel_event,
            )
        store.set_status(task_id, "succeeded", result=result)
    except AgentCancelled:
        store.set_status(task_id, "cancelled", error="任务已取消")
    except asyncio.CancelledError:
        cancel_event.set()  # 通知工作线程尽快退出（协作式取消）
        store.set_status(task_id, "cancelled", error="任务已取消")
    except Exception as exc:  # noqa: BLE001
        logger.exception("任务 %s 执行失败", task_id)
        store.set_status(task_id, "failed", error=str(exc))
    finally:
        _RUNNING.pop(task_id, None)
        _CANCEL_EVENTS.pop(task_id, None)
        store.cleanup(keep=MAX_TASKS)


@router.post("/chat")
async def submit_chat(payload: ChatRequest) -> dict:
    """提交一次对话任务，立即返回 task_id；执行步骤持久化留存。"""
    task_id = uuid.uuid4().hex
    store.create(task_id)
    event = threading.Event()
    _CANCEL_EVENTS[task_id] = event
    _RUNNING[task_id] = asyncio.create_task(_execute(task_id, payload, event))
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}")
async def get_task(task_id: str, include_steps: bool = False) -> dict:
    """查询任务状态与结果；include_steps=true 时附带全部执行步骤。"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    data = {k: task[k] for k in ("id", "status", "created", "result", "error")}
    if include_steps:
        data["steps"] = task["steps"]
    return data


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    """取消任务：置位取消信号并中断 asyncio 等待；已结束的任务原样返回。"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    if task["status"] in TERMINAL_STATUSES:
        return {"task_id": task_id, "status": task["status"], "cancelled": False,
                "message": "任务已结束，无需取消"}

    _CANCEL_EVENTS.get(task_id, threading.Event()).set()
    running = _RUNNING.get(task_id)
    if running is not None and not running.done():
        running.cancel()  # 中断 to_thread 等待；线程内由 cancel_event 协作退出
    return {"task_id": task_id, "status": "cancelling", "cancelled": True}
