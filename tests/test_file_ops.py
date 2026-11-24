"""文件 CRUD 工具测试：沙箱逃逸拦截 + 黑名单限制 + 正常 CRUD 流程。"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from agent.agent_tools.build_tools import get_registry, get_tool_meta
from agent.fs import SandboxError, check_path, set_roots
from agent.fs.file_ops import file_delete, file_edit, file_list, file_read, file_write


class SandboxBase(unittest.TestCase):
    """每个用例使用独立的临时根目录，并锁定环境变量保证确定性。"""

    def setUp(self):
        self._old_env = {
            k: os.environ.get(k)
            for k in ("AGENT_FS_ROOTS", "AGENT_FS_MAX_READ_BYTES", "AGENT_FS_MAX_WRITE_BYTES")
        }
        self.root = Path(tempfile.mkdtemp(prefix="miniagent_fs_test_"))
        os.environ["AGENT_FS_ROOTS"] = str(self.root)
        os.environ.pop("AGENT_FS_MAX_READ_BYTES", None)
        os.environ.pop("AGENT_FS_MAX_WRITE_BYTES", None)
        set_roots([])

    def tearDown(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        set_roots([])
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def w(self, rel: str, content: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode("utf-8"))  # 字节写入，避免 Windows 文本模式换行转换
        return p


class SandboxTest(SandboxBase):
    def test_relative_path_resolves_inside_root(self):
        self.w("notes/a.txt", "hi")
        self.assertEqual(check_path("notes/a.txt"), (self.root / "notes" / "a.txt").resolve())

    def test_dotdot_escape_rejected(self):
        with self.assertRaises(SandboxError):
            check_path("../outside.txt")

    def test_deep_dotdot_escape_rejected(self):
        self.w("sub/x.txt", "x")
        with self.assertRaises(SandboxError):
            check_path("sub/../../escape.txt")

    def test_absolute_outside_rejected(self):
        outside = self.root.parent / "outside_abs.txt"
        with self.assertRaises(SandboxError):
            check_path(str(outside))

    def test_absolute_inside_allowed(self):
        target = self.root / "in.txt"
        self.assertEqual(check_path(str(target)), target.resolve())

    def test_denied_suffix_rejected(self):
        for name in ("secrets.env", "data.db", "key.pem", "module.pyc"):
            with self.assertRaises(SandboxError, msg=name):
                check_path(name)

    def test_env_variant_prefix_rejected(self):
        with self.assertRaises(SandboxError):
            check_path(".env.local")

    def test_symlink_escape_rejected(self):
        outside_file = self.root.parent / "symlink_outside_target.txt"
        outside_file.write_text("secret", encoding="utf-8")
        self.addCleanup(outside_file.unlink, missing_ok=True)
        link = self.root / "link.txt"
        try:
            os.symlink(outside_file, link)
        except OSError:
            self.skipTest("当前环境无权限创建符号链接")
        with self.assertRaises(SandboxError):
            check_path("link.txt")

    def test_write_flag_accepted(self):
        self.assertEqual(check_path("a.txt", for_write=True), (self.root / "a.txt").resolve())


class RegistrationTest(unittest.TestCase):
    def test_tools_registered_as_private(self):
        registry = get_registry()
        for name in ("file_read", "file_write", "file_edit", "file_delete", "file_list"):
            self.assertIn(name, registry)
            self.assertFalse(get_tool_meta()[name]["public"], name)


class FileOpsTest(SandboxBase):
    def test_write_then_read_roundtrip(self):
        res = json.loads(file_write("docs/hello.txt", "你好\nworld"))
        self.assertEqual(res["bytes"], len("你好\nworld".encode("utf-8")))
        res = json.loads(file_read("docs/hello.txt"))
        self.assertEqual(res["total_lines"], 2)
        self.assertEqual(res["content"], "1:你好\n2:world")
        self.assertFalse(res["truncated"])

    def test_read_pagination(self):
        self.w("big.txt", "\n".join(f"line{i}" for i in range(10)))
        res = json.loads(file_read("big.txt", offset=2, limit=5))
        self.assertEqual(res["returned"], 5)
        self.assertTrue(res["truncated"])
        self.assertIn("3:line2", res["content"])
        self.assertIn("7:line6", res["content"])
        tail = json.loads(file_read("big.txt", offset=8, limit=5))
        self.assertEqual(tail["returned"], 2)
        self.assertFalse(tail["truncated"])

    def test_read_missing_file(self):
        self.assertIn("错误", file_read("nope.txt"))

    def test_read_binary_rejected(self):
        p = self.root / "blob.bin"
        p.write_bytes(b"ok\x00binary")
        self.assertIn("二进制", file_read("blob.bin"))

    def test_read_size_limit(self):
        os.environ["AGENT_FS_MAX_READ_BYTES"] = "10"
        self.w("fat.txt", "x" * 100)
        self.assertIn("超过读取上限", file_read("fat.txt"))

    def test_append_mode(self):
        file_write("log.txt", "a\n")
        file_write("log.txt", "b\n", mode="append")
        self.assertEqual((self.root / "log.txt").read_text(encoding="utf-8"), "a\nb\n")

    def test_write_size_limit(self):
        os.environ["AGENT_FS_MAX_WRITE_BYTES"] = "10"
        self.assertIn("超过上限", file_write("fat.txt", "x" * 100))

    def test_write_outside_rejected(self):
        self.assertIn("错误", file_write("../escape.txt", "boom"))

    def test_write_invalid_mode(self):
        self.assertIn("错误", file_write("a.txt", "x", mode="truncate"))

    def test_edit_unique_replacement(self):
        self.w("code.py", "value = 1\nprint(value)\n")
        res = json.loads(file_edit("code.py", "value = 1", "value = 2"))
        self.assertEqual(res["replacements"], 1)
        self.assertEqual((self.root / "code.py").read_text(encoding="utf-8"), "value = 2\nprint(value)\n")

    def test_edit_not_found(self):
        self.w("a.txt", "hello")
        self.assertIn("未找到", file_edit("a.txt", "xyz", "abc"))

    def test_edit_ambiguous_rejected(self):
        self.w("a.txt", "dup dup")
        self.assertIn("匹配到 2 处", file_edit("a.txt", "dup", "x"))

    def test_delete_moves_to_trash(self):
        self.w("tmp/old.txt", "bye")
        res = json.loads(file_delete("tmp/old.txt"))
        self.assertFalse((self.root / "tmp" / "old.txt").exists())
        trashed = list((self.root / ".trash").rglob("*old.txt"))
        self.assertEqual(len(trashed), 1)
        self.assertIn(".trash", res["moved_to"])

    def test_delete_missing(self):
        self.assertIn("错误", file_delete("ghost.txt"))

    def test_delete_outside_rejected(self):
        self.assertIn("错误", file_delete("../victim.txt"))

    def test_list_entries(self):
        self.w("src/main.py", "print(1)")
        self.w("src/util.py", "pass")
        self.w("src/data.json", "{}")
        res = json.loads(file_list("src", pattern="*.py"))
        names = [e["path"] for e in res["entries"]]
        self.assertEqual(names, ["src/main.py", "src/util.py"])
        self.assertFalse(res["truncated"])

    def test_list_root_all(self):
        self.w("f1.txt", "1")
        (self.root / "subdir").mkdir()
        res = json.loads(file_list("."))
        types = {e["path"]: e["type"] for e in res["entries"]}
        self.assertEqual(types.get("f1.txt"), "file")
        self.assertEqual(types.get("subdir"), "dir")

    def test_list_outside_rejected(self):
        self.assertIn("错误", file_list(".."))


if __name__ == "__main__":
    unittest.main()
