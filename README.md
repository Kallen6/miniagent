# miniagent

两个独立的小项目放在一个仓库里：

| 目录 | 说明 |
|---|---|
| `agent/` | 基于 OpenAI SDK 的轻量 function-calling Agent（接入 DeepSeek） |
| `CdpTools/` | 基于 Chrome DevTools Protocol 的网页元素拾取 + 流程编排 + 多进程执行工具 |

```
miniagent/
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
```

## 环境要求

- Python 3.12（仓库自带的 `miniagt/` 是 3.12.10）
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

在 `agent/.env` 中填写（该文件已被 `.gitignore` 忽略，不要提交）：

```ini
API_KEY=sk-xxxxxxxxxxxxxxxx
DS_URL=https://api.deepseek.com
```

### 运行

```bash
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

### 当前进度

- [x] 工具 Schema 自动生成与注册
- [x] 命令执行工具
- [x] LLM 客户端与单轮对话
- [ ] `agent_loop()`：多轮对话 + 工具回调的循环（尚未实现）
- [ ] 流式输出

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
- `agent/.env` 含真实密钥，**不要提交**，分享时只给 `agent/.env.example`（只写键名）；
- 元素库 JSON 里可能包含页面 URL、业务数据，提交前检查或脱敏。
