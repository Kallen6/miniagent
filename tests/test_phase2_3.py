"""阶段 2/3 单元测试：DB 查询工具、工作流闭环、意图占位与 Prompt 角色。"""
import json
import os
import tempfile
import unittest

from sqlalchemy import create_engine, text

from agent.dbase.db_query import MAX_LIMIT, query_database
from agent.llm.intent import detect_intent
from agent.llm.prompts import get_prompt, list_roles, register_prompt
from agent.workflows import list_workflows, run_workflow


class DbQueryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_url = "sqlite:///" + os.path.join(cls.tmpdir.name, "test.db").replace("\\", "/")
        engine = create_engine(cls.db_url)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"))
            conn.execute(text("INSERT INTO users (name, age) VALUES ('alice', 20), ('bob', 30)"))
        engine.dispose()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_query_all(self):
        res = json.loads(query_database(self.db_url, "users"))
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["columns"], ["id", "name", "age"])

    def test_fields_and_filters(self):
        res = json.loads(
            query_database(self.db_url, "users", fields=["name"], filters={"age": 20}, limit=10)
        )
        self.assertEqual(res["columns"], ["name"])
        self.assertEqual(res["rows"], [["alice"]])

    def test_limit_capped(self):
        res = json.loads(query_database(self.db_url, "users", limit=MAX_LIMIT + 100))
        self.assertLessEqual(res["count"], MAX_LIMIT)

    def test_invalid_field(self):
        self.assertIn("错误", query_database(self.db_url, "users", fields=["nope"]))

    def test_invalid_filter_field(self):
        self.assertIn("错误", query_database(self.db_url, "users", filters={"nope": 1}))

    def test_invalid_table(self):
        self.assertIn("错误", query_database(self.db_url, "missing_table"))

    def test_bad_url(self):
        self.assertIn("查询失败", query_database("sqlite:///no_such_dir/x.db", "users"))


class WorkflowTest(unittest.TestCase):
    def test_list_contains_demos(self):
        names = [w["name"] for w in list_workflows()]
        self.assertIn("text_upper", names)
        self.assertIn("text_stats", names)

    def test_run_text_upper(self):
        res = run_workflow("text_upper", text="abc")
        self.assertEqual(res["upper"], "ABC")

    def test_run_text_stats(self):
        res = run_workflow("text_stats", text="hello world\nsecond line")
        self.assertEqual(res["words"], 4)
        self.assertEqual(res["lines"], 2)

    def test_unknown_workflow(self):
        with self.assertRaises(KeyError):
            run_workflow("nope")


class IntentTest(unittest.TestCase):
    def test_placeholder_defaults(self):
        r = detect_intent("帮我查一下用户表")
        self.assertEqual(r.intent, "general_chat")
        self.assertIsNone(r.workflow)
        self.assertEqual(r.confidence, 0.0)


class PromptRoleTest(unittest.TestCase):
    def test_default_role(self):
        self.assertEqual(get_prompt("default"), "你是一个ai助手")

    def test_list_roles(self):
        roles = list_roles()
        self.assertIn("default", roles)
        self.assertIn("data_analyst", roles)

    def test_register_prompt(self):
        register_prompt("tmp_role", "临时角色提示词")
        self.assertEqual(get_prompt("tmp_role"), "临时角色提示词")

    def test_unknown_role(self):
        with self.assertRaises(KeyError):
            get_prompt("nope")


class SystemMsgTest(unittest.TestCase):
    def test_role_switch(self):
        from agent.llm.agent import system_msg

        msg = system_msg(role="data_analyst")
        self.assertEqual(msg["role"], "system")
        self.assertEqual(msg["content"], get_prompt("data_analyst"))

    def test_content_priority(self):
        from agent.llm.agent import system_msg

        self.assertEqual(system_msg(content="abc")["content"], "abc")

    def test_default_compat(self):
        from agent.llm.agent import system_msg

        self.assertEqual(system_msg()["content"], get_prompt("default"))


if __name__ == "__main__":
    unittest.main()
