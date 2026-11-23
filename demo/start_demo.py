"""演示入口：加载演示工具与工作流后启动服务（与 main.py 相同配置）。

用法（项目根目录执行）：
    python demo/start_demo.py
启动后访问 http://127.0.0.1:8008 ，演示台词见 demo/README.md。
"""
import logging
import sys
from pathlib import Path

# 保证从任意工作目录启动都能 import agent 包与 demo 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from demo import demo_tools  # noqa: F401  导入即注册演示工具与工作流

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run("agent.web.app:app", host="127.0.0.1", port=8008, ws="websockets-sansio")
