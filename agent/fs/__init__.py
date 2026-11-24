"""文件系统工具层：路径沙箱校验 + 受限 CRUD 工具。

为后续 skills / 插件提供统一的文件访问底座：
skills 清单读取、插件文件操作均应复用 sandbox.check_path，保证限制不可绕过。
"""
from .sandbox import SandboxError, check_path, get_roots, set_roots

__all__ = ["SandboxError", "check_path", "get_roots", "set_roots"]
