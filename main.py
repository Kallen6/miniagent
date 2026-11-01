"""miniagent 统一入口：启动 Web 对话页与对外异步服务。

运行后访问 http://127.0.0.1:8000
"""
import uvicorn

if __name__ == "__main__":
    # 显式指定 WS 实现，避免 auto 探测失败时静默禁用 WebSocket（握手 404）
    uvicorn.run("agent.web.app:app", host="127.0.0.1", port=8008, ws="websockets-sansio")
