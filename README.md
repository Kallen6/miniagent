# miniagent

两个独立的小项目放在一个仓库里：

| 目录 | 说明 |
|---|---|
<<<<<<< HEAD
| `agent/` | 基于 OpenAI SDK 的轻量 function-calling Agent（接入 DeepSeek，不使用 langchain） |
=======
| `agent/` | 基于 OpenAI SDK 的轻量 function-calling Agent（接入 DeepSeek） |
>>>>>>> d586de25e2659d1a5a2e2f8131cb8c73f7cef26b
| `CdpTools/` | 基于 Chrome DevTools Protocol 的网页元素拾取 + 流程编排 + 多进程执行工具 |

```
miniagent/
<<<<<<< HEAD
├── agent/                  # Agent 主体（Python 包，相对导入）
│   ├── agent_tools/
│   │   ├── build_tools.py      # @tool 装饰器 + Schema 自动生成 + 工具注册
│   │   └── command_exec.py     # 执行 shell 命令并打印结果
│   ├── dbase/
│   │   └── db_query.py         # SQLAlchemy 通用查询工具（db_url/表/字段/过滤传参）
│   ├── workflows/
│   │   ├── registry.py         # @workflow 注册 + run_workflow 调度
│   │   └── demo_workflow.py    # 占位工作流示例
│   ├── llm/
│   │   ├── agent.py            # LLM 客户端、流式调用、system_msg(role)
│   │   ├── agent_loop.py       # AgentStep + run_agent 多轮循环
│   │   ├── intent.py           # 意图识别接口（占位）
│   │   └── prompts.py          # Prompt 角色库
│   ├── web/
│   │   ├── app.py              # FastAPI：WS /ws/chat + 静态聊天页
│   │   └── static/             # 前端页面（原生 HTML/JS/CSS）
│   ├── service/
│   │   └── async_api.py        # 对外异步接口 /api/v1/*
│   ├── .env                    # 密钥（已被 git 忽略，不入仓）
│   └── .env.example            # 密钥模板（只写键名）
├── tests/                  # 单元测试（阶段 2/3）与服务冒烟测试（阶段 4-6）
├── mkd/                    # 各阶段落地总结文档
├── main.py                 # 统一入口：python main.py
├── CdpTools/               # CDP 工具（详见 CdpTools/README.md）
└── requirements.txt        # 全项目依赖，分组管理
=======
├── agent/                  # Agent 主体
│   ├── main.py             # 入口：LLM 客户端 + 对话
│   ├── build_tools.py      # @tool 装饰器 + Schema 自动生成 + 工具注册
│   ├── command_exec.py     # 执行 shell 命令并打印结果
│   └── .env                # 密钥（已被 git 忽略，不入仓）
├── CdpTools/               # CDP 工具（详见 CdpTools/README.md）
│   ├── capture/            # 元素捕获器（PyQt5 桌面程序）
│   ├── cdp_flow/           # 流程编排库 Browser / Tab / Element
│   ├── utils/              # log() / setup() 日志工具
│   └── examples/           # 可运行示例
├── requirements.txt        # 全项目依赖，分组管理
├── .gitignore
└── miniagt/                # Python 虚拟环境（已被 git 忽略，不入仓）
>>>>>>> d586de25e2659d1a5a2e2f8131cb8c73f7cef26b
```

## 环境要求

<<<<<<< HEAD
- Python 3.12
=======
- Python 3.12（仓库自带的 `miniagt/` 是 3.12.10）
>>>>>>> d586de25e2659d1a5a2e2f8131cb8c73f7cef26b
- `CdpTools` 的捕获器需要图形界面，浏览器需 Chrome / Edge

## 安装

```bash
# Windows
python -m venv miniagt
miniagt\Scripts\activate
pip install -r requirements.txt

# macOS / Linux
python3 -m venv miniagt
source miniagt/bin/activate
pip install -r requirements.txt
```

## agent：函数调用型 Agent

### 配置密钥

<<<<<<< HEAD
复制 `agent/.env.example` 为 `agent/.env` 并填写（该文件已被 `.gitignore` 忽略，不要提交）：
=======
在 `agent/.env` 中填写（该文件已被 `.gitignore` 忽略，不要提交）：
>>>>>>> d586de25e2659d1a5a2e2f8131cb8c73f7cef26b

```ini
API_KEY=sk-xxxxxxxxxxxxxxxx
DS_URL=https://api.deepseek.com
```

### 运行

```bash
<<<<<<< HEAD
python main.py
```

启动后访问 <http://127.0.0.1:8000>：网页内可切换角色、对话，并实时查看 agent 的思考、工具调用与执行结果。

### 模块一览

| 模块 | 作用 |
|---|---|
| `agent_tools/build_tools.py` | `@tool` 装饰器：从类型注解自动生成 function-calling Schema 并注册；`get_tools()` / `get_registry()` |
| `agent_tools/command_exec.py` | `exec_cmd(cmd)` 执行 shell 命令 |
| `dbase/db_query.py` | `query_database(db_url, table, fields, filters, limit)` 通用查询，`@tool` 注册，标识符校验 + 参数绑定 + 行数限量 |
| `workflows/` | `@workflow` 注册短固定工作流，`run_workflow(name, **kwargs)` 统一调度 |
| `llm/agent_loop.py` | `run_agent()` 多轮循环：流式输出 → 解析 tool_calls → 执行 → 回填；`AgentStep` 步骤经 `step_callback` 推送 |
| `llm/prompts.py` | 角色库 `get_prompt(role)` / `list_roles()` / `register_prompt()` |
| `llm/intent.py` | `detect_intent(text)` 意图识别接口（当前占位，恒返回通用对话） |
| `web/app.py` | 聊天页 + `WS /ws/chat` + `GET /roles`、`/workflows` |
| `service/async_api.py` | `POST /api/v1/chat` 提交任务、`GET /api/v1/task/{id}` 查询 |

### 对外接口

```bash
# 提交一次对话任务（异步）
curl -X POST http://127.0.0.1:8000/api/v1/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "1+1 等于几", "role": "default"}'
# → {"task_id": "...", "status": "queued"}

# 查询结果；include_steps=true 附带全部执行步骤
curl http://127.0.0.1:8000/api/v1/task/<task_id>?include_steps=true
```

WebSocket：连接 `ws://127.0.0.1:8000/ws/chat`，发送 `{"message": "...", "role": "default"}`，逐条接收 `{"type": "step", "step": {...}}`，最终收到 `{"type": "done", "content": "..."}`（或 `{"type": "error", ...}`）。步骤 `step.type` 为 `reasoning / tool_call / tool_result / answer`。

### 测试

```bash
python -m unittest tests.test_phase2_3 -v        # DB/工作流/意图/Prompt 单元测试
python tests/test_phase4_6_smoke.py              # 服务冒烟测试（自动起停）
```
=======
cd agent
python main.py
```

`main.py` 里用 `load_dotenv()` 读取 `.env`，它从**当前工作目录**向上查找，所以要在 `agent/` 目录下运行，否则读不到密钥。

### 三个模块

| 文件 | 作用 |
|---|---|
| `build_tools.py` | `@tool` 装饰器：从函数签名和类型注解自动生成 OpenAI function-calling 的 JSON Schema，并自动注册到工具表；`get_tools()` 返回 Schema 列表，`get_registry()` 返回 `{名称: 函数}` |
| `command_exec.py` | `exec_cmd(cmd)` 执行 shell 命令，打印 `[exit]` / `[stdout]` / `[stderr]` |
| `main.py` | `create_llm()` 用 `API_KEY` / `DS_URL` 建客户端；`get_llm_res()` 调用 `deepseek-flash`（开启思考模式） |

### 自定义工具

```python
from build_tools import tool, get_tools, get_registry
from command_exec import exec_cmd

@tool(
    description="执行一条 shell 命令",
    param_descriptions={"command": "要执行的命令，例如 ipconfig"},
)
def run_command(command: str) -> str:
    exec_cmd(command)
    return "done"

print(get_tools())      # 交给 LLM 的 tools 参数
print(get_registry())   # 名称 → 可执行函数，回调时用
```

参数类型会按注解映射成 JSON Schema 类型（`str` → `string`、`int` → `integer`、`bool` → `boolean` …），没有默认值的参数标记为 `required`。
>>>>>>> d586de25e2659d1a5a2e2f8131cb8c73f7cef26b

### 当前进度

- [x] 工具 Schema 自动生成与注册
- [x] 命令执行工具
- [x] LLM 客户端与单轮对话
<<<<<<< HEAD
- [x] `run_agent()`：多轮对话 + 工具回调 + 流式思考可视化
- [x] 通用数据库查询工具（`agent/dbase`）
- [x] 工作流注册与占位示例（`agent/workflows`）
- [x] Prompt 角色库与 `system_msg(role)` 切换
- [x] Web 可视化对话页（`agent/web`）
- [x] 对外异步服务接口（`agent/service`）
- [ ] 意图识别接入真实模型（接口已占位）
=======
- [ ] `agent_loop()`：多轮对话 + 工具回调的循环（尚未实现）
- [ ] 流式输出
>>>>>>> d586de25e2659d1a5a2e2f8131cb8c73f7cef26b

## CdpTools

基于 CDP 做网页自动化，不写 CSS/XPath、不依赖 Selenium：用捕获器在浏览器里点选元素，存成 JSON 元素库，脚本里按「分组 + 元素名」操作元素。

```bash
python CdpTools/capture/element_capture_qt.py   # 1. 捕获元素，保存为元素库 JSON
python CdpTools/examples/run_parallel.py --list # 2. 查看示例任务
```

```python
from cdp_flow import Browser

browser = Browser.launch(port=9222, library="CdpTools/examples/demo_lib.json")
tab = browser.new_tab("https://example.com/")
tab.group("demo").element("search_input").input_text("hello")
```

完整说明（元素库格式、API 速查、多进程规则、常见问题）见 [`CdpTools/README.md`](CdpTools/README.md)。

## 注意事项

- `miniagt/` 是虚拟环境，**不要提交**；
<<<<<<< HEAD
- `agent/.env` 含真实密钥，**不要提交**，分享时只给 `agent/.env.example`；
=======
- `agent/.env` 含真实密钥，**不要提交**，分享时只给 `agent/.env.example`（只写键名）；
>>>>>>> d586de25e2659d1a5a2e2f8131cb8c73f7cef26b
- 元素库 JSON 里可能包含页面 URL、业务数据，提交前检查或脱敏。
