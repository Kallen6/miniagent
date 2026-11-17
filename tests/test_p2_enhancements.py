"""P2 优化测试：上下文摘要压缩与意图识别真实实现（占位兼容）。"""
import json
import unittest
from unittest import mock

from agent.llm.context import trim_messages
from agent.llm.intent import detect_intent, route_to_workflow


def _sys():
    return {"role": "system", "content": "你是一个ai助手"}


class TrimSummarizeTest(unittest.TestCase):
    def _big_history(self):
        msgs = [_sys()]
        for i in range(6):
            msgs.append({"role": "user", "content": f"问题{i} " + "词 " * 1200})
            msgs.append({"role": "assistant", "content": f"答案{i} " + "句 " * 1200})
        return msgs

    def test_summary_inserted_after_system(self):
        msgs = self._big_history()
        result = trim_messages(msgs, max_chars=15000, summarize_fn=lambda text: "用户讨论了A与B")
        self.assertEqual(result[0]["role"], "system")
        self.assertIn("[早前对话摘要]", result[1]["content"])
        self.assertIn("A与B", result[1]["content"])
        self.assertLessEqual(len(result), len(msgs))

    def test_summarizer_receives_evicted_text(self):
        received = {}

        def fake_summarize(text):
            received["text"] = text
            return "摘要"

        result = trim_messages(self._big_history(), max_chars=15000, summarize_fn=fake_summarize)
        self.assertIn("问题0", received["text"])
        self.assertIn("摘要", result[1]["content"])

    def test_summarizer_failure_falls_back(self):
        def boom(_):
            raise RuntimeError("llm down")

        msgs = self._big_history()
        result = trim_messages(msgs, max_chars=15000, summarize_fn=boom)
        self.assertEqual(result[0]["role"], "system")
        self.assertNotIn("摘要", json.dumps(result, ensure_ascii=False))
        self.assertLess(len(result), len(msgs))

    def test_no_summarizer_keeps_old_behavior(self):
        msgs = self._big_history()
        self.assertEqual(trim_messages(msgs, max_chars=15000),
                         trim_messages(msgs, max_chars=15000, summarize_fn=None))

    def test_summary_capped_input(self):
        seen = []

        def fake_summarize(text):
            seen.append(len(text))
            return "s"

        trim_messages(self._big_history(), max_chars=15000, summarize_fn=fake_summarize)
        self.assertLessEqual(seen[0], 8000)


class IntentTest(unittest.TestCase):
    def test_placeholder_without_client(self):
        r = detect_intent("帮我查一下用户表")
        self.assertEqual(r.intent, "general_chat")
        self.assertIsNone(r.workflow)
        self.assertEqual(r.confidence, 0.0)

    def test_real_classification(self):
        client = object()
        with mock.patch("agent.llm.intent.get_llm_res") as fake:
            fake.return_value = json.dumps({
                "intent": "workflow", "workflow": "text_upper",
                "confidence": 0.9, "reason": "大写转换请求",
            })
            r = detect_intent("把ABC变成大写", client)
        self.assertEqual(r.workflow, "text_upper")
        self.assertAlmostEqual(r.confidence, 0.9)

    def test_real_classification_extracts_json_from_prose(self):
        with mock.patch("agent.llm.intent.get_llm_res") as fake:
            fake.return_value = '好的，结果如下：{"intent": "general_chat", "workflow": null, "confidence": 0.1, "reason": "闲聊"}'
            r = detect_intent("你好", object())
        self.assertEqual(r.intent, "general_chat")
        self.assertIsNone(r.workflow)

    def test_real_classification_failure_falls_back(self):
        with mock.patch("agent.llm.intent.get_llm_res", side_effect=RuntimeError("boom")):
            r = detect_intent("随便", object())
        self.assertEqual(r.intent, "general_chat")
        self.assertEqual(r.confidence, 0.0)

    def test_route_hit(self):
        with mock.patch("agent.llm.intent.get_llm_res") as fake:
            fake.return_value = json.dumps({
                "intent": "workflow", "workflow": "text_upper", "confidence": 0.95, "reason": "",
            })
            self.assertEqual(route_to_workflow("转大写", object()), "text_upper")

    def test_route_below_threshold(self):
        with mock.patch("agent.llm.intent.get_llm_res") as fake:
            fake.return_value = json.dumps({
                "intent": "workflow", "workflow": "text_upper", "confidence": 0.5, "reason": "",
            })
            self.assertIsNone(route_to_workflow("转大写", object()))

    def test_route_unknown_workflow(self):
        with mock.patch("agent.llm.intent.get_llm_res") as fake:
            fake.return_value = json.dumps({
                "intent": "workflow", "workflow": "no_such_flow", "confidence": 0.99, "reason": "",
            })
            self.assertIsNone(route_to_workflow("x", object()))


if __name__ == "__main__":
    unittest.main()
