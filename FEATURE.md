# Agent2 功能清单

> 版本 0.1.3.6 — 模块化 AI Agent 系统框架，用于学习和研究 Agent 核心架构与设计模式。

---

## 1. LLM 抽象层 (`agent2.llm`)

- **统一接口** — `BaseLLM` 抽象类定义 `chat()` / `chat_stream()` 两个核心方法，所有提供商共用同一套消息模型。
- **OpenAI 兼容适配器** — `OpenAILLM` 封装 `openai.AsyncOpenAI`，支持任何 OpenAI-compatible API（OpenAI / DeepSeek / Ollama / vLLM / Qwen 等），自动处理 `/v1` 路径补全。
- **协议自愈与修复** — `_repair_tool_messages()` 自动校验并补齐缺失的 `tool` 响应消息，确保符合 OpenAI 协议规范。
- **流式输出** — `chat_stream()` 支持 SSE 逐 token 流式返回。
- **统一消息模型** — `Message`（system / user / assistant / tool 四种角色）、`ToolCall`、`ToolResult`、`ToolSchema`、`LLMResponse`、`Usage`，全部基于 Pydantic。
- **工厂函数** — `create_llm()` 支持三级解析：用户配置文件 → 内置预设 → 直接模型名，含模糊别名匹配。

## 2. 工具系统 (`agent2.tools`)

- **`@tool` 装饰器** — 将普通 Python 函数（同步/异步）转为 `Tool` 对象，从类型注解自动生成 JSON Schema，支持 `Optional` / `Union` 类型解包。
- **ToolRegistry** — 集中式工具注册表，提供 `register` / `unregister` / `get` / `execute` / `list_schemas` / `copy` 等 API。
- **内置工具**：
  | 工具 | 说明 |
  |------|------|
  | `file_read` / `read_file` | 读取文件内容 |
  | `file_write` / `write_file` | 写入/创建文件 |
  | `list_directory` | 列出目录结构 |
  | `python_exec` | 执行 Python 代码片段 |
  | `shell_exec` | 执行 shell 命令 |
  | `web_search` | 网络搜索 |

## 3. Agent 核心 (`agent2.agent`)

### 3.1 BaseAgent

- 所有 Agent 的公共基类，管理 LLM、ToolRegistry、消息历史、日志。
- **多轮对话** — `chat()` 保持上下文；`run()` 重置后单次执行。
- **状态管理** — `set_rule()`（动态修改 system prompt）、`reset()`（清空历史）、`fork()`（独立克隆含完整状态）。
- **工具调用容错与自愈** — `_execute_tool_calls()` 异常防护确保必然生成 tool result；`_repair_tool_messages()` 恢复时与入参时自动补齐断裂历史。
- **序列化/持久化** — `to_dict()` / `to_json()` / `save()` 序列化；`from_dict()` / `from_json()` / `load()` 反序列化，自动解析 Agent 子类和内置工具并修复历史。
- **安全限制** — `MaxIterationsExceeded` 防止无限循环。

### 3.2 ReActAgent

- 实现 ReAct（Reasoning + Acting）推理循环：**Thought → Action → Observation → 重复**，直至 LLM 给出最终答案。
- 论文参考：Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (2022)。

### 3.3 PlannerAgent

- Plan-and-Execute 模式：先由 LLM 生成结构化执行计划（JSON 数组），再逐步执行。
- 每个步骤内部使用 mini ReAct 循环调用工具。
- **动态重规划** — 可选 `enable_replan`，每步完成后让 LLM 审视剩余计划并修正。
- 最终由 LLM 综合所有步骤结果生成答案。

### 3.4 ReflectionMixin

- Mixin 类，可混入任意 Agent，在输出后进行自我评估（1-10 分）。
- 低于阈值（默认 7 分）时自动带反馈重试，**重试过程使用 Agent 完整推理循环（保留工具能力）**，最多 `max_reflections` 轮。
- JSON 评估结果解析使用 `extract_json` 工具函数，容忍 Markdown 包裹格式。

## 4. 记忆系统 (`agent2.memory`)

### 4.1 WorkingMemory（短期记忆）

- 基于消息历史的滑动窗口，超出 `max_messages` 后自动压缩旧消息为摘要。
- 关键词匹配搜索，同时搜索摘要。
- 提供 `get_messages_for_llm()` 将摘要 + 当前消息拼装为 LLM 输入。

### 4.2 LongTermMemory（长期记忆）

- 基于向量余弦相似度的语义检索。
- **TF-IDF 模式**（默认）— 无外部依赖，纯 Python 实现词频-逆文档频率嵌入。添加文档后自动重算所有向量保证一致性。支持 CJK 字符级分词。
- **OpenAI Embeddings 模式** — 调用 `text-embedding-3-small` 获取高质量嵌入。
- 支持磁盘持久化（JSON 格式保存文档、词表、IDF）。

## 5. 多 Agent 编排 (`agent2.crew`)

### 5.1 SequentialCrew（顺序流水线）

- Agent 按注册顺序依次执行，每个 Agent 接收前序所有 Agent 的累积输出作为上下文。
- 适用场景：研究 → 撰写 → 编辑 → 审查。

### 5.2 SupervisorCrew（监督者模式）

- 监督者 LLM 通过 tool-calling 动态选择工人 Agent 执行子任务。
- 每个工人 Agent 被建模为一个 tool（`delegate_to_{name}`），监督者自行决定调用顺序和参数。
- 多个 worker 任务通过 `asyncio.gather` 并发执行，提升吞吐。
- 支持独立的 `supervisor_llm`，最多 `max_delegations` 次委派。

### 5.3 DebateCrew（辩论模式）

- 所有 Agent 独立回答同一任务，然后经过多轮（`rounds`）互相批评和修正。
- 最终由 `synthesizer_llm` 综合各方观点生成共识答案。
- 适用场景：需要多元视角或高准确性的决策类任务。

## 6. 配置与日志 (`agent2.utils`)

### 6.1 Settings

- 基于 `pydantic-settings`，支持 `AGENT2_` 前缀环境变量配置（API key、base URL、默认模型、温度、最大 token、Agent 迭代上限、verbose 开关、记忆窗口大小）。

### 6.2 AgentLogger

- 基于 `rich` 的结构化日志系统，可视化 Agent 推理循环的每个阶段：
  - 🤖 Start / ✅ Finish（含耗时统计）
  - 💭 Thought / ⚡ Action / 👁️ Observation / 🎯 Final Answer
  - 📝 Plan / ▶ Step Start / ✓ Step Done
  - 🧠 Memory Recall / 💾 Memory Store
  - 📨 Delegate / 💬 Agent Message
- 文件日志写入使用线程锁 (`threading.Lock`) 保证并发安全。

### 6.3 JSON 提取工具 (`utils.json_helpers`)

- `extract_json(text)` — 从 LLM 输出中鲁棒提取 JSON，依次尝试 Markdown 代码块、正则匹配、纯文本解析。
- 供 `planner.py`、`reflection.py` 等模块复用，替代各自脆弱的手写解析逻辑。

## 7. 应用层 (`agent2.app`)

### 7.1 交互式 Chat CLI (`agent2.app.chat`)

- 命令行交互聊天应用，支持：
  - **单轮模式** (`-p`) — 发送消息、执行、退出。
  - **交互模式** — 多轮对话，支持 `-i` 预填首条消息。
  - **模型选择** — `-s` 启动时弹出交互菜单；`--model` 直接指定；支持 Provider 自动推导与紧凑排版。
  - **斜杠命令** — `/model`（切换模型）、`/tools`（查看工具）、`/clear`（清空历史）、`/help`。
  - **纯聊天模式** — `--no-tools` 禁用内置工具。
  - 自动隐藏无 API Key 的远程模型，保留本地/局域网模型。

### 7.2 用户配置文件 (`~/.config/agent2/config.json`)

- **无冗余数据组织**：`providers`（集中配置 endpoint / api_key）与 `models`（模型别名引用所属 provider）分离，配合顶层 `default` 默认模型指定。
- **自动继承与兼容**：支持子模型自动继承服务商凭据，兼容 legacy `llm` 配置。
- `last_model` 文件记忆上次选择的模型。


### 7.3 TUI 界面 (`agent2.app.tui`)

- 基于 Textual 的终端图形化聊天应用：
  - **全扁平极简 UI 风格 (Flat Design)** — 彻底移除冗重圆角与粗框，全屏采用现代扁平单线描边、微妙色块底色与微指示边条（Indicator Bar），布局紧凑优雅。
  - **会话管理模态框 (`SessionSelectScreen` / `/sessions`)** — `/sessions`（或 `/resume`）弹出交互式会话管理面板：
    - `Enter`: 一键恢复选中的历史会话。
    - `e` / `r`: 就地重命名选中会话标题并持久化。
    - `d`: 快捷删除不需要的会话。
    - `Esc`: 关闭面板。
  - **会话快捷重命名 (`/rename`)** — `/rename <new-title>` 快速修改当前会话名称并持久化保存。
  - **动态模型搜索 (`ModelSelectScreen`)** — 支持键入实时模糊过滤 Provider、Model 和 Alias，回车即选。
  - **输入历史导航 (`ChatInput`)** — 方向键 ↑ / ↓ 快速浏览和填充历史用户输入，保留草稿编辑状态。
  - **会话标题智能清洗** — 自动剔除 `<file>`、`<directory>` 等注入的上下文标签，保持会话列表标题整洁。




## 8. 示例 (`examples/`)

| 示例 | 说明 |
|------|------|
| `01_single_agent.py` | 单 Agent ReAct 推理 |
| `02_tool_use.py` | 自定义工具使用 |
| `03_planning.py` | Plan-and-Execute 模式 |
| `04_memory.py` | 记忆系统演示（无需 API Key） |
| `05_multi_agent.py` | 多 Agent 协作 |

## 9. 技术栈

- **Python ≥ 3.13**，uv 管理项目和依赖
- 核心依赖：`pydantic` / `pydantic-settings` / `httpx` / `rich` / `openai`
- 可选依赖：`numpy`（memory）、`textual`（TUI）、`pytest` / `pytest-asyncio` / `mypy`（dev）
- 构建系统：Hatchling
