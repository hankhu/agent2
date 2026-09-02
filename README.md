# Agent2 — 模块化 Agent 系统框架

一个从零构建的 Python Agent 系统框架，用于深入理解 AI Agent 的核心架构和设计模式。

## 核心特性

| 特性 | 说明 |
|------|------|
| 🧠 **LLM 抽象层** | 统一 OpenAI 兼容接口，支持 OpenAI / DeepSeek / Ollama / vLLM / Qwen 等 |
| 🔧 **工具系统** | `@tool` 装饰器自动生成 JSON Schema，支持同步/异步 |
| 🔄 **ReAct 模式** | Thought → Action → Observation 推理循环 |
| 📋 **Plan-and-Execute** | 先规划后执行，支持动态重规划 |
| 🪞 **自我反思** | ReflectionMixin 添加输出自评和迭代改进 |
| 💾 **记忆系统** | 短期 (WorkingMemory) + 长期 (LongTermMemory/TF-IDF) |
| 👥 **多 Agent 编排** | 顺序/监督者/辩论 三种协作模式 |

## 快速开始

```bash
# 安装
uv pip install -e "."

# 设置 API Key
export AGENT2_API_KEY=sk-...
```

### 最简示例

```python
import asyncio
from agent2.llm import create_llm
from agent2.agent import ReActAgent
from agent2.tools.builtin import python_exec

async def main():
    llm = create_llm("openai", model="gpt-4o-mini")
    agent = ReActAgent("assistant", llm=llm, tools=[python_exec])
    result = await agent.run("What is 2^100?")
    print(result)

asyncio.run(main())
```

## 示例

```bash
uv run examples/01_single_agent.py   # 单 Agent ReAct
uv run examples/02_tool_use.py       # 自定义工具
uv run examples/03_planning.py       # Plan-and-Execute
uv run examples/04_memory.py         # 记忆系统（无需 API Key）
uv run examples/05_multi_agent.py    # 多 Agent 协作
```

## 终端交互界面 (TUI)

Agent2 提供沉浸式终端交互应用，支持多种交互模式：

```bash
uv run -m agent2.app.tui              # 启动 TUI（缺省为 Agent 模式）
uv run -m agent2.app.tui --mode plan  # 以 Plan 模式启动
uv run -m agent2.app.tui --mode ask   # 以 Ask 只读模式启动
```

### 交互模式与斜杠指令

- **Agent 模式（缺省模式）**（`/agent`）：全功能自主智能体，支持读写文件、命令执行等工具调用与人在回路（HITL）确认。
- **Plan 模式**（`/plan`）：
  - 意图分析与任务拆解：分析用户目标并生成结构化子任务列表，明确标注任务间依赖关系与所需上下文。
  - 动态交互调优：支持在 Plan 模式下多轮对话修改与完善计划。
  - 确认后自动派发：用户确认计划（输入 `yes` / `确认` / `ok` 等）后，自动退出 Plan 模式并进入 Agent 模式。
  - DAG 拓扑执行与上下文隔离：依据依赖关系拓扑排序，为各个子任务派发单独的子 agent 独立执行，严格仅传递所需的前序结果与上下文。
  - 结果汇总：待子任务全部完成后统一聚合结果，生成完整最终回答。
- **Ask 模式**（`/ask`）：只读问答模式，**严格禁止所有写和执行操作**（禁用 `file_write`、`shell_exec`、`python_exec` 等），仅开放只读与目录查看工具。

## 配置文件 (`~/.config/agent2/config.json`)

Agent2 支持通过用户级配置文件管理服务商凭据与模型别名。文件路径为 `~/.config/agent2/config.json`（可选）：

```json
{
  "default": "gpt-4o-mini",
  "providers": {
    "openai": {
      "api_key": "sk-..."
    },
    "deepseek": {
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-..."
    },
    "qwen": {
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "sk-..."
    },
    "ollama": {
      "base_url": "http://localhost:11434/v1"
    }
  },
  "models": {
    "gpt-4o-mini": { "provider": "openai" },
    "deepseek": { "provider": "deepseek", "model_id": "deepseek-chat" },
    "deepseek-r1": { "provider": "deepseek", "model_id": "deepseek-reasoner" },
    "qwen": { "provider": "qwen", "model_id": "qwen-plus" },
    "llama3.1": { "provider": "ollama" }
  }
}
```

- **`default`**：默认模型别名或名称（如 `"gpt-4o-mini"`、`"deepseek"`）。
- **`providers`**：服务商端点与 API Key 集中管理，同服务商下的多模型无需重复配置凭据与 base URL。
- **`models`**：具名模型别名映射，只需指定所属 `provider` 即可自动继承连接配置。



## 架构

```
agent2/
├── llm/        # LLM 抽象层 — 统一多提供商接口
├── tools/      # 工具系统 — @tool 装饰器 + Registry
├── agent/      # Agent 核心 — ReAct / Planner / Reflection
├── memory/     # 记忆系统 — Working / LongTerm
├── crew/       # 多 Agent — Sequential / Supervisor / Debate
└── utils/      # 配置 + 日志 + JSON 提取工具
```

## License

MIT
