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
