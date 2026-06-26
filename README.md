# Agent2 — 模块化 Agent 系统框架

一个从零构建的 Python Agent 系统框架，用于深入理解 AI Agent 的核心架构和设计模式。

## 核心特性

| 特性 | 说明 |
|------|------|
| 🧠 **LLM 抽象层** | 统一接口支持 OpenAI / Anthropic / Google / Ollama |
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

# 安装 LLM 提供商 SDK（按需）
uv pip install -e ".[openai]"      # OpenAI
uv pip install -e ".[all-llm]"     # 所有 LLM

# 设置 API Key
export AGENT2_OPENAI_API_KEY=sk-...
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

## 架构

```
agent2/
├── llm/        # LLM 抽象层 — 统一多提供商接口
├── tools/      # 工具系统 — @tool 装饰器 + Registry
├── agent/      # Agent 核心 — ReAct / Planner / Reflection
├── memory/     # 记忆系统 — Working / LongTerm
├── crew/       # 多 Agent — Sequential / Supervisor / Debate
└── utils/      # 配置 + 日志
```

## License

MIT
