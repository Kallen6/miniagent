"""Web 对话页：WS 长连接实时推送 AgentStep，HTTP 提供页面与元信息。"""
import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..agent_tools.build_tools import get_tools
from ..llm.agent import create_llm, system_msg, user_msg
from ..llm.agent_loop import run_agent
from ..llm.prompts import list_roles
from ..service.async_api import router as api_router
from ..workflows import list_workflows

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="miniagent", version="0.1.0")
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/roles")
async def roles():
    """可用角色列表，供前端角色切换下拉框。"""
    return {"roles": list_roles()}


@app.get("/workflows")
async def workflows():
    """已注册工作流列表，供 LLM 编排参考与前端展示。"""
    return {"workflows": list_workflows()}


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """聊天长连接：收 {message, role}，逐条推 {type: step|done|error}。

    同角色下沿用会话历史；切换角色即重置历史（system 提示词不同）。
    """
    await ws.accept()
    loop = asyncio.get_running_loop()
    messages: list[dict] = []
    current_role: str | None = None

    try:
        while True:
            data = await ws.receive_json()
            message = str(data.get("message") or "").strip()
            role = str(data.get("role") or "default")
            if not message:
                await ws.send_json({"type": "error", "message": "消息不能为空"})
                continue

            if role != current_role:
                messages = [system_msg(role=role)]
                current_role = role
            messages.append(user_msg(message))

            try:
                client = create_llm()
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"type": "error", "message": f"LLM 客户端初始化失败: {exc}"})
                continue

            queue: asyncio.Queue = asyncio.Queue()

            def enqueue(step) -> None:
                # 工作线程内调用，需转回事件循环线程入队
                loop.call_soon_threadsafe(queue.put_nowait, step.to_dict())

            def worker() -> str:
                try:
                    return run_agent(client, messages, tools=get_tools(), step_callback=enqueue)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)  # 结束哨兵

            async def pump() -> None:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    await ws.send_json({"type": "step", "step": item})

            fut = loop.run_in_executor(None, worker)
            send_task = asyncio.create_task(pump())
            try:
                result = await fut
            except Exception as exc:  # noqa: BLE001
                await send_task
                await ws.send_json({"type": "error", "message": f"agent 执行失败: {exc}"})
                continue
            await send_task
            await ws.send_json({"type": "done", "content": result})
    except WebSocketDisconnect:
        pass
