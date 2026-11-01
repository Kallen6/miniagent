"""对外异步服务：提交对话任务立即返回 task_id，结果异步产生、按需查询。

与 Web 层共用同一个 FastAPI 实例（agent.web.app 中 include 本 router）。
"""
import asyncio
import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from ..agent_tools.build_tools import get_tools
from ..llm.agent import create_llm, system_msg, user_msg
from ..llm.agent_loop import run_agent

router = APIRouter(prefix="/api/v1")

MAX_TASKS = 200  # 内存任务表上限，超出时淘汰最早任务
_TASKS: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    role: str = "default"


def _save_task(task_id: str, task: dict) -> None:
    _TASKS[task_id] = task
    while len(_TASKS) > MAX_TASKS:
        _TASKS.pop(next(iter(_TASKS)))


async def _execute(task_id: str, payload: ChatRequest) -> None:
    task = _TASKS[task_id]
    task["status"] = "running"

    def collect(step) -> None:
        task["steps"].append(step.to_dict())

    try:
        client = create_llm()
        messages = [system_msg(role=payload.role), user_msg(payload.message)]
        result = await asyncio.to_thread(run_agent, client, messages, get_tools(), collect)
        task["status"] = "succeeded"
        task["result"] = result
    except Exception as exc:  # noqa: BLE001
        task["status"] = "failed"
        task["error"] = str(exc)


@router.post("/chat")
async def submit_chat(payload: ChatRequest) -> dict:
    """提交一次对话任务，立即返回 task_id；执行步骤在服务端留存。"""
    task_id = uuid.uuid4().hex
    _save_task(task_id, {
        "id": task_id,
        "status": "queued",
        "created": time.time(),
        "result": None,
        "error": None,
        "steps": [],
    })
    asyncio.create_task(_execute(task_id, payload))
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}")
async def get_task(task_id: str, include_steps: bool = False) -> dict:
    """查询任务状态与结果；include_steps=true 时附带全部执行步骤。"""
    task = _TASKS.get(task_id)
    if task is None:
        return {"error": f"任务 {task_id} 不存在"}
    data = {k: task[k] for k in ("id", "status", "created", "result", "error")}
    if include_steps:
        data["steps"] = task["steps"]
    return data
