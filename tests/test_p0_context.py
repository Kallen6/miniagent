"""P0 优化测试：上下文裁剪（trim_messages）与工具结果标准化（normalize_result）。"""
import json
import unittest

from agent.llm.context import trim_messages
from agent.task.runner import MAX_TOOL_RESULT, normalize_result, run_tool


def _sys():
    return {"role": "system", "content": "你是一个ai助手"}


def _tc(cid):
    return {"id": cid, "type": "function", "function": {"name": "query_database", "arguments": "{}"}}


def _assistant_tc(cid):
    return {"role": "assistant", "content": None, "tool_calls": [_tc(cid)]}


def _tool(cid, text="result"):
    return {"role": "tool", "tool_call_id": cid, "content": text}


def assert_pairs_valid(testcase, msgs):
    """每条 tool 消息必须能向前找到携带对应 tool_call_id 的 assistant。"""
    for i, m in enumerate(msgs):
        if m.get("role") == "tool":
            ok = False
            for j in range(i - 1, -1, -1):
                if msgs[j].get("role") == "assistant" and msgs[j].get("tool_calls"):
                    if any(tc["id"] == m["tool_call_id"] for tc in msgs[j]["tool_calls"]):
                        ok = True
                        break
            testcase.assertTrue(ok, f"位置 {i} 的 tool 消息没有配对的 assistant")


class NormalizeResultTest(unittest.TestCase):
    def test_str_passthrough(self):
        self.assertEqual(normalize_result("hello"), "hello")

    def test_dict_to_json(self):
        r = normalize_result({"ok": True, "count": 2, "name": "alice"})
        self.assertEqual(json.loads(r), {"ok": True, "count": 2, "name": "alice"})

    def test_list_to_json(self):
        self.assertEqual(json.loads(normalize_result([1, "a", None])), [1, "a", None])

    def test_other_type(self):
        self.assertEqual(normalize_result(42), "42")

    def test_truncate_long_result(self):
        r = normalize_result("x" * (MAX_TOOL_RESULT + 100))
        self.assertLessEqual(len(r), MAX_TOOL_RESULT + 50)
        self.assertIn("已截断", r)

    def test_run_tool_returns_json(self):
        r = run_tool(lambda: {"flag": True}, {}, timeout=5)
        self.assertEqual(json.loads(r), {"flag": True})


class TrimMessagesTest(unittest.TestCase):
    def test_small_history_unchanged(self):
        msgs = [_sys(), {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "你好"}]
        self.assertEqual(len(trim_messages(msgs)), 3)

    def test_single_message(self):
        msgs = [_sys()]
        self.assertEqual(trim_messages(msgs), msgs)

    def test_trims_old_keeps_system_and_latest(self):
        msgs = [_sys()]
        for _ in range(12):
            msgs.append({"role": "user", "content": "词 " * 1500})
            msgs.append({"role": "assistant", "content": "答 " * 1500})
        result = trim_messages(msgs, max_chars=20000)
        self.assertEqual(result[0]["role"], "system")
        self.assertLess(len(result), len(msgs))
        self.assertEqual(result[-1], msgs[-1])  # 最新消息必须保留
        assert_pairs_valid(self, result)

    def test_tool_pairing_kept(self):
        big = "x" * 4000
        msgs = [
            _sys(),
            {"role": "user", "content": big},
            _assistant_tc("c1"),
            _tool("c1", big),
            _assistant_tc("c2"),
            _tool("c2", big),
            {"role": "assistant", "content": "最终回答"},
        ]
        result = trim_messages(msgs, max_chars=9000)
        self.assertEqual(result[0]["role"], "system")
        self.assertNotEqual(result[1].get("role"), "tool")
        assert_pairs_valid(self, result)
        self.assertEqual(result[-1]["content"], "最终回答")

    def test_start_on_tool_expands_to_assistant(self):
        """起点落在 tool 消息上时，修正逻辑应前移包含配对 assistant。"""
        big_args = "y" * 4000
        msgs = [
            _sys(),
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "query_database", "arguments": big_args}},
            ]},
            _tool("c1", "short"),
        ]
        result = trim_messages(msgs, max_chars=2000)
        self.assertEqual(result[0]["role"], "system")
        assert_pairs_valid(self, result)
        roles = [m["role"] for m in result]
        self.assertIn("assistant", roles)


if __name__ == "__main__":
    unittest.main()
