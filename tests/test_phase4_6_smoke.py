"""阶段 4-6 冒烟测试：真实启动服务，验证页面、路由、异步任务与 WS 链路。

运行：python tests/test_phase4_6_smoke.py（自动起停服务，无需真实 API Key）
"""
import json
import subprocess
import sys
import time
import urllib.request

HOST = "127.0.0.1"
PORT = 8123
BASE = f"http://{HOST}:{PORT}"


def wait_health(timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("服务启动超时")


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.load(r)


def post_json(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def test_ws():
    """WS 链路：发一条消息，收到 step 帧直至 done/error（取决于密钥是否有效）。"""
    from websocket import create_connection

    ws = create_connection(f"ws://{HOST}:{PORT}/ws/chat", timeout=60)
    try:
        ws.send(json.dumps({"message": "1+1 等于几", "role": "default"}))
        types, deadline = [], time.time() + 120
        while time.time() < deadline:
            frame = json.loads(ws.recv())
            types.append(frame["type"] if frame["type"] != "step" else f"step:{frame['step']['type']}")
            if frame["type"] in ("done", "error"):
                break
        print("      ws frames:", types[:4], "...", types[-3:])
        assert "done" in types or "error" in types, "WS 未收到终止帧"
    finally:
        ws.close()


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agent.web.app:app",
         "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
    )
    try:
        wait_health()
        print("[1/5] health ok")

        with urllib.request.urlopen(BASE + "/", timeout=5) as r:
            html = r.read().decode()
        assert "miniagent" in html
        print("[2/5] index page ok")

        roles = get_json("/roles")["roles"]
        assert "default" in roles and "data_analyst" in roles
        names = [w["name"] for w in get_json("/workflows")["workflows"]]
        assert "text_upper" in names
        print(f"[3/5] roles & workflows ok: {roles} / {names}")

        resp = post_json("/api/v1/chat", {"message": "1+1 等于几", "role": "default"})
        task = {}
        for _ in range(120):
            task = get_json(f"/api/v1/task/{resp['task_id']}?include_steps=true")
            if task["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.5)
        assert task["status"] == "succeeded" or bool(task.get("error"))
        print(f"[4/5] async task ok: status={task['status']} steps={len(task.get('steps', []))}")

        test_ws()
        print("[5/5] websocket ok")
        print("SMOKE OK")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
