"""P1 优化测试：任务持久化、取消、鉴权限流、工具可见性、循环健壮性、LLM 重试判定。"""
import asyncio
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from agent.llm.agent_loop import AgentCancelled, run_agent
from agent.service import security
from agent.service.task_store import TaskStore


class TaskStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TaskStore(os.path.join(self.tmp.name, "tasks.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_create_and_get(self):
        self.store.create("t1")
        task = self.store.get("t1")
        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["steps"], [])
        self.assertIsNone(task["result"])

    def test_get_missing(self):
        self.assertIsNone(self.store.get("nope"))

    def test_status_transition_and_result(self):
        self.store.create("t2")
        self.store.set_status("t2", "running")
        self.assertEqual(self.store.get("t2")["status"], "running")
        self.store.set_status("t2", "succeeded", result="答案")
        task = self.store.get("t2")
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["result"], "答案")

    def test_append_step(self):
        self.store.create("t3")
        self.store.append_step("t3", {"type": "reasoning", "content": "想"})
        self.store.append_step("t3", {"type": "answer", "content": "答"})
        self.assertEqual(
            [s["type"] for s in self.store.get("t3")["steps"]],
            ["reasoning", "answer"],
        )

    def test_cleanup_keeps_running_and_recent(self):
        # 3 条终态旧任务 + 1 条 running 任务；keep=2 时 running 必须保留
        for tid in ("old1", "old2", "old3", "live"):
            self.store.create(tid)
        for tid in ("old1", "old2", "old3"):
            self.store.set_status(tid, "succeeded", result=tid)
        self.store.set_status("live", "running")
        self.store.cleanup(keep=2)
        self.assertIsNotNone(self.store.get("live"))
        self.assertIsNotNone(self.store.get("old3"))  # 保留最近 2 条终态
        self.assertIsNone(self.store.get("old1"))     # 最旧的被清理


class AgentLoopRobustnessTest(unittest.TestCase):
    """JSON 参数错误回填、必填校验、取消、max_rounds 收尾。"""

    def _run(self, side_effects, **kwargs):
        steps = []
        with mock.patch("agent.llm.agent_loop.get_registry",
                        return_value=kwargs.pop("registry", {})), \
             mock.patch("agent.llm.agent_loop.get_tool_meta",
                        return_value=kwargs.pop("tool_meta", {})), \
             mock.patch("agent.llm.agent_loop.stream_llm_res") as fake:
            fake.side_effect = side_effects
            result = run_agent(None, [], step_callback=lambda s: steps.append(s), **kwargs)
        return result, steps

    def test_invalid_json_args_backfilled(self):
        bad = [{"id": "c1", "type": "function",
                "function": {"name": "_t", "arguments": "{bad json"}}]
        result, steps = self._run([
            ("", bad, ""),
            ("最终回答", [], ""),
        ], registry={"_t": lambda: "x"})
        self.assertEqual(result, "最终回答")
        results = [s.tool_result for s in steps if s.type == "tool_result"]
        self.assertIn("invalid_json_args", results[0])

    def test_missing_required_args_rejected(self):
        tc = [{"id": "c1", "type": "function",
               "function": {"name": "_t", "arguments": "{}"}}]
        result, steps = self._run([
            ("", tc, ""),
            ("最终回答", [], ""),
        ], registry={"_t": lambda x: "x"}, tool_meta={"_t": {"timeout": 5, "slow": False, "required": ["x"]}})
        self.assertEqual(result, "最终回答")
        self.assertIn("missing_required_args", steps[1].tool_result)

    def test_cancel_event_raises(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(AgentCancelled):
            run_agent(None, [], cancel_event=event)

    def test_max_rounds_returns_last_content(self):
        tc = [{"id": "c1", "type": "function",
               "function": {"name": "_t", "arguments": "{}"}}]
        result, _ = self._run([("部分进展说明", tc, "")],
                              registry={"_t": lambda: "x"}, max_rounds=1)
        self.assertEqual(result, "部分进展说明")

    def test_max_rounds_default_message(self):
        tc = [{"id": "c1", "type": "function",
               "function": {"name": "_t", "arguments": "{}"}}]
        result, _ = self._run([("", tc, "")], registry={"_t": lambda: "x"}, max_rounds=1)
        self.assertIn("最大轮数上限", result)


class ToolVisibilityTest(unittest.TestCase):
    def test_private_tool_filtered(self):
        from agent.agent_tools.build_tools import get_tools, tool

        @tool(description="内部工具", public=False)
        def _private_helper() -> str:
            return "secret"

        try:
            names = [s["function"]["name"] for s in get_tools(include_private=False)]
            self.assertNotIn("_private_helper", names)
            names_all = [s["function"]["name"] for s in get_tools(include_private=True)]
            self.assertIn("_private_helper", names_all)
        finally:
            # 清理注册表，避免影响其他用例
            from agent.agent_tools import build_tools
            build_tools._TOOL_SCHEMAS[:] = [
                s for s in build_tools._TOOL_SCHEMAS if s["function"]["name"] != "_private_helper"
            ]
            build_tools._TOOL_REGISTRY.pop("_private_helper", None)
            build_tools._TOOL_META.pop("_private_helper", None)


class SecurityTest(unittest.TestCase):
    def setUp(self):
        self._orig_key = security._configured_key

    def tearDown(self):
        security._configured_key = self._orig_key

    def _call(self, key=None, host="1.2.3.4"):
        request = mock.MagicMock()
        request.client.host = host
        return asyncio.run(security.require_api_key(request, key=key))

    def test_no_key_configured_passes(self):
        security._configured_key = None
        self._call(key=None)  # 不抛异常即通过

    def test_wrong_key_401(self):
        security._configured_key = "secret"
        with self.assertRaises(Exception) as ctx:
            self._call(key="wrong")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_correct_key_passes(self):
        security._configured_key = "secret"
        self._call(key="secret")

    def test_token_bucket_exhausts(self):
        bucket = security.TokenBucket(rate_per_min=6, capacity=2)  # 每秒 0.1 补充
        self.assertTrue(bucket.try_acquire("k"))
        self.assertTrue(bucket.try_acquire("k"))
        self.assertFalse(bucket.try_acquire("k"))

    def test_ws_check_rejects_bad_key(self):
        security._configured_key = "secret"
        ws = mock.MagicMock()
        ws.headers = {}
        ws.query_params = {}
        self.assertIsNone(security.ws_check(ws))

    def test_ws_check_accepts_query_key(self):
        security._configured_key = "secret"
        security._bucket = security.TokenBucket(rate_per_min=60, capacity=10)
        ws = mock.MagicMock()
        ws.headers = {}
        ws.query_params = {"api_key": "secret"}
        ws.client.host = "1.2.3.4"
        self.assertIsNotNone(security.ws_check(ws))


class LlmRetryTest(unittest.TestCase):
    def test_retryable_classification(self):
        import openai

        self.assertTrue(security)  # 占位引用，真实断言在下方
        from agent.llm.agent import _retryable

        conn = openai.APIConnectionError(request=mock.MagicMock())
        rate = openai.RateLimitError("限流", response=mock.MagicMock(status_code=429), body=None)
        err500 = openai.APIStatusError("服务器错误", response=mock.MagicMock(status_code=500), body=None)
        err400 = openai.APIStatusError("参数错误", response=mock.MagicMock(status_code=400), body=None)

        self.assertTrue(_retryable(conn))
        self.assertTrue(_retryable(rate))
        self.assertTrue(_retryable(err500))
        self.assertFalse(_retryable(err400))
        self.assertFalse(_retryable(ValueError("x")))


if __name__ == "__main__":
    unittest.main()
