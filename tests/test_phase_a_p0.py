"""阶段 A P0 测试：工具超时、快慢分流执行器、workflow 慢工具注册。"""
import time
import unittest
from unittest import mock

from agent.agent_tools.build_tools import get_registry, get_tool_meta
from agent.task.runner import run_tool
from agent.workflows import list_workflows


def _sleep_fn(n: float):
    time.sleep(n)
    return "woke"


def _boom_fn():
    raise ValueError("boom")


class RunnerTest(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(run_tool(lambda x: x * 2, {"x": 21}, timeout=5), "42")

    def test_timeout(self):
        result = run_tool(_sleep_fn, {"n": 1.0}, timeout=0.1)
        self.assertIn("timeout", result)

    def test_exception(self):
        result = run_tool(_boom_fn, {}, timeout=5)
        self.assertIn("exception", result)
        self.assertIn("boom", result)


class WorkflowToolTest(unittest.TestCase):
    def test_workflow_registered_as_slow_tool(self):
        registry = get_registry()
        meta = get_tool_meta()
        names = [w["name"] for w in list_workflows()]
        self.assertTrue(names, "应有至少一个工作流")
        for n in names:
            self.assertIn(n, registry)
            self.assertTrue(meta[n]["slow"], f"{n} 应为慢工具")
            self.assertEqual(meta[n]["timeout"], 300.0)


class AgentLoopTimeoutTest(unittest.TestCase):
    def test_slow_tool_timeout_in_loop(self):
        from agent.llm.agent_loop import run_agent

        def _slow(**kwargs):
            time.sleep(1)
            return "never"

        steps = []
        with mock.patch("agent.llm.agent_loop.get_registry", return_value={"_slow": _slow}), \
             mock.patch("agent.llm.agent_loop.get_tool_meta",
                        return_value={"_slow": {"timeout": 0.1, "slow": True}}), \
             mock.patch("agent.llm.agent_loop.stream_llm_res") as fake:
            fake.side_effect = [
                ("", [{"id": "c1", "type": "function",
                       "function": {"name": "_slow", "arguments": "{}"}}], ""),
                ("最终回答", [], ""),
            ]
            result = run_agent(None, [], step_callback=lambda s: steps.append(s))

        self.assertEqual(result, "最终回答")
        types = [s.type for s in steps]
        self.assertIn("tool_call", types)
        self.assertIn("answer", types)
        tool_results = [s for s in steps if s.type == "tool_result"]
        self.assertTrue(tool_results)
        self.assertIn("timeout", tool_results[0].tool_result)


if __name__ == "__main__":
    unittest.main()
