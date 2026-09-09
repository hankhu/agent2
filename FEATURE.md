# Agent2 功能清单

> 版本 0.1.3.13 — 模块化 AI Agent 系统框架，用于学习和研究 Agent 核心架构与设计模式。

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
- **对话回退** — `rewind(turns)` 按轮次回退对话历史并返回被移除消息；`rewind_to(index, inclusive)` 精确回退到指定消息索引。
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
  - **斜杠命令** — `/model`（切换模型）、`/tools`（查看工具）、`/skills`（浏览/调用技能）、`/yolo`、`/allow-all`、`/clear`（清空历史）、`/help`。
  - **纯聊天模式** — `--no-tools` 禁用内置工具。
  - 自动隐藏无 API Key 的远程模型，保留本地/局域网模型。

### 7.2 用户配置文件 (`~/.config/agent2/config.json`)

- **无冗余数据组织**：`providers`（集中配置 endpoint / api_key）与 `models`（模型别名引用所属 provider）分离，配合顶层 `default` 默认模型指定。
- **自动继承与兼容**：支持子模型自动继承服务商凭据，兼容 legacy `llm` 配置。
- **全局配置项**：支持设置 `max_iterations` 最大轮数（默认 `50`，别名 `max_turns`）。
- **Context 与 MCP 配置**：支持 `rules` inline 规则列表与 `mcp_servers` MCP 服务器配置。
- `last_model` 文件记忆上次选择的模型。


### 7.3 TUI 界面 (`agent2.app.tui`)

- 基于 Textual 的终端图形化交互界面：
  - **三大多模态交互模式 (Interaction Modes)**：
    - **Agent 模式（缺省）** (`/agent`)：全功能自主模式，支持读写文件、Shell 执行与人在回路（HITL）审批。
    - **Plan 模式** (`/plan`)：
      - 深度分析用户意图，生成结构化任务计划列表（包含任务 ID、描述、前序依赖关系与所需特定上下文）。
      - 支持交互式多轮对话调整优化任务计划。
      - 用户确认计划后（回复 `yes` / `确认` / `ok`），自动退出 Plan 模式并进入缺省 Agent 模式。
      - **DAG 拓扑排序调度**：根据子任务间的依赖图以拓扑序列安全推进。
      - **独立 Sub-Agent 与上下文隔离**：为每个子任务派发独立 sub-agent，仅透传该子任务声明需要的上下文与依赖任务输出，避免冗余历史污染。
      - **聚合总结**：子任务全量完成后，由 LLM 综合所有执行结果生成最终回答。
    - **Ask 模式** (`/ask`)：
      - 只读问答与代码分析模式，**严格禁用所有写和执行操作**（禁用 `file_write`、`shell_exec`、`python_exec` 等）。
      - 并在 Tool Schema 注入与 Agent 执行拦截层面做双重安全防护。
  - **Copilot CLI 风格现代极简布局**：
    - **顶部导航栏 (`TopTabBar`)** — 水平排列 `Current`、`Sessions`、`Skills`、`Help` 紧凑标签，支持鼠标直达、快捷键（`F1`–`F4`）以及输入框为空时按 `Tab` 键循环切换。
    - **极简欢迎横幅 (`WelcomeBanner`)** — 空会话呈现居中 ASCII Mascot 图标、免责声明与动态轮播的 Tip 指引卡片，并在 `/clear` 后优雅恢复。
    - **独立帮助模态浮层 (`HelpScreen`)** — 集中展示运行模式、按键绑定、斜杠命令与上下文注入语法，支持 `?` / `/help` 快捷打开。
    - **双层状态栏 (`ContextBar` + `StatusBar`)** — 紧贴输入框上方的 `ContextBar` 呈现工作目录、执行 Spinner、Token 用量与模型提供商；底端单行 `StatusBar` 呈现导航指引与模式徽标（`[AGENT]` / `[PLAN]` / `[ASK]`）。
  - **模型提供商与 Host 智能识别** — 自动解析底层 LLM 提供商标签（如 `[deepseek] deepseek-chat`）；对于私有代理、内网网关或局域网 IP，智能选用 `base_url` 的 host（如 `[localhost:11434] llama3.1`）并完成 Rich Markup 括号转义。
  - **现代全屏交互视窗**：
    - **会话管理视窗 (`SessionSelectScreen` / `/sessions`)** — 全屏极简设计，支持实时关键词过滤搜索、全宽亮蓝高光选框、`↑`/`↓` 键盘导航、`e` 重命名、`d` 删除会话、`Enter` 恢复会话；右侧预览面板展示会话转录并支持按预览内容过滤。
    - **Skills 管理视窗 (`SkillSelectScreen` / `/skills`)** — 全屏选择器，支持技能实时过滤、`↑`/`↓` 导航、`r` 重载、`Enter` 调用；顶栏 `Skills` 标签对应 `F3`。
    - **模型选择视窗 (`ModelSelectScreen` / `/model`)** — 全屏极简设计，提供顶栏联动、模型分组、全宽亮蓝高光条、即打即搜与自定义模型 identifier 直达。
  - **斜杠命令菜单快速确认** — 输入 `/` 弹出命令自动补全菜单时，按 `Enter` 键直接等同于 `Tab` 键完成补全填充。
  - **全扁平极简无边框 UI 风格 (Flat Borderless Design)** — 彻底移除所有界面边框线（`border: none`）与不必要的内衬距/外边距，全屏采用现代无边框贴合、极简色块底色与零间距边缘平铺。
  - **会话快捷重命名 (`/rename`)** — `/rename <new-title>` 快速修改当前会话名称并持久化保存。
  - **用户消息即时挂载渲染** — 消息提交后立即在 DOM 中挂载并刷新贴底渲染，免除等待模型网络请求响应的停顿感。
  - **流式嵌入确认卡片 (`ConfirmCard` / HITL 审批)** — 工具审批从独立弹层改为自然嵌入消息流的紧凑卡片，支持多级审批作用域：
    - 工具名称与参数单行紧凑排版，配合清晰颜色区分。
    - 审批选项：`[1/y] Approve once`、`[c] In conversation`、`[p] In project`、`[a] Always approve`、`[n] Reject`。
    - 支持 `Left` / `Right`（或 `h` / `l`）方向键循环切换焦点，支持 `1/y`、`2/c`、`3/p`、`4/a`、`n` / `Esc` 快捷键。
    - conversation / project / global 三级授权持久化到 `.agent2/approvals.json` 或 `~/.config/agent2/approvals.json`。
    - 审批完成后自动转换为历史状态徽标（`✓ Approved once` / `✓ Approved in project` / `✓ Always approved` / `✗ Rejected`），并将输入焦点归还输入框。
  - **工具执行结果面板折叠与快捷切换 (`ToolCard` / `Ctrl+O`)**：
    - 工具卡片标题自动显示操作摘要（shell command 首行 / python 首行 / 文件路径 / web query 等），运行中显示 `⏳` 且禁止折叠。
    - 工具执行结果面板（Result Panel）默认折叠展示（`collapsed=True`），成功结果保持紧凑，错误结果额外显示 `❌ Error` 状态行。
    - 全局快捷键 `Ctrl+O` 一键批量展开 / 收起所有工具执行结果面板。
  - **Token 用量持久化与实时同步** — 会话保存 `usage`；恢复会话、切换模型、Plan 子任务聚合均保留 Token 计数；Thought / Tool 完成事件实时刷新 `ContextBar`，取消或异常时也会同步。
  - **YOLO / Allow-all 模式** — `/yolo` 自动批准所有操作并注入自主决策系统提示；`/allow-all` 仅自动批准；状态栏显示 `YOLO` / `ALLOW-ALL` 徽标。
  - **对话回退与分叉 (`/rewind` / `/fork`)** — `/rewind` 回退最近一轮对话并将用户输入填回输入框；`/fork [title]` 克隆当前完整会话为新 session 继续对话。
  - **消息级 Point Rewind / Fork / Retry 交互** — 点击或焦点选中任意历史消息，显示 `⏪ Rewind`、`🔄 Retry` 和 `🍴 Fork` 操作按钮。在 UserMessage 上回退/重试/分叉到该消息之前；在 AssistantMessage 上回退/重试/分叉到该回复处。Escape 取消选择。
  - **指令重试与继续 (`/retry` / `/continue`)** — `/retry` 重发最后一轮用户提问；`/continue` 一键唤醒 Agent 继续完成未完任务。
  - **平滑贴底自动滚动 (Sticky Scroll)** — 未主动向上翻看时新消息自动滚到底部，翻看历史时不强制拉回，滚回底部自动恢复贴底。
  - **代码块与大段文字折叠 (Collapsible Folding)** — 助手消息中代码块（>=4行）与大段文字（>=8行/400字符）自动折叠为 Collapsible；`file_write` Diff 预览（>=6行）折叠展示；`Ctrl+O` 一键切换展开/收起。
  - **最大轮数限制无缝继续** — ReAct loop 达到 `max_iterations` 时触发 HITL 继续审批弹窗，确认后追加轮数无缝继续执行；达到上限停止后提供 `▶ Continue` 按钮。
  - **输入历史导航 (`ChatInput`)** — 方向键 ↑ / ↓ 快速浏览和填充历史用户输入，保留草稿编辑状态。
  - **会话标题智能清洗** — 自动剔除 `<file>`、`<directory>` 等注入的上下文标签，保持会话列表标题整洁。




## 8. Context、Skills 与 MCP 集成

### 8.1 Context 与 Rules (`agent2.context`)

- 自动发现并加载全局/项目 Rules 文件（`.md` / `.txt`），以及 `config.json` 中的 inline rules。
- `Context.build_system_prompt()` 将规则以 `<rules>` 标签注入 Agent 的 system prompt。
- 搜索路径：`~/.config/agent2/rules`、`~/.agent2/rules`、`<cwd>/.agent2/rules`。

### 8.2 Skills (`agent2.context` + `agent2.app.tui.screens.skill_select`)

- 遵循 Agent Skills 规范，从 `SKILL.md` YAML frontmatter 解析 `name` / `description`，支持折叠多行描述与无 frontmatter 回退。
- 多目录优先级：全局 `~/.config/agent2/skills`、`~/.claude/skills`、`~/.agent2/skills`；项目 `.claude/skills`、`.agents/skills`、`.agent2/skills`，同名技能后扫描目录覆盖。
- 支持 `/skills` 浏览/重载、动态 `/<skill_name> [prompt]` 调用、斜杠命令补全；TUI 提供 `SkillSelectScreen` 全屏选择器（`F3`）。

### 8.3 MCP (Model Context Protocol) (`agent2.mcp`)

- `MCPManager` 通过 stdio 连接外部 MCP server，动态发现 tools 并包装为 agent2 `Tool`。
- `config.json` 的 `mcp_servers` 可配置多个 server（`command` / `args` / `env` / `url`）。
- 可选依赖：`uv pip install agent2[mcp]`（`mcp>=1.0`）。

### 8.4 多级工具审批作用域 (`agent2.app.approval`)

- conversation / project / global 三级审批持久化。
- ConfirmCard 提供 `Approve once`、`In conversation`、`In project`、`Always approve`、`Reject` 五档选择。
- 项目级授权写入 `<project>/.agent2/approvals.json`，全局授权写入 `~/.config/agent2/approvals.json`。

### 8.5 YOLO / Allow-all 模式

- `/yolo on|off|show`：自动批准所有操作，并向 system prompt 注入自主决策指令。
- `/allow-all on|off|show`：仅自动批准所有操作，不改变 system prompt。
- 状态栏显示 `YOLO` / `ALLOW-ALL` 徽标；TUI 与 Chat CLI 均支持。

## 9. 示例 (`examples/`)

| 示例 | 说明 |
|------|------|
| `01_single_agent.py` | 单 Agent ReAct 推理 |
| `02_tool_use.py` | 自定义工具使用 |
| `03_planning.py` | Plan-and-Execute 模式 |
| `04_memory.py` | 记忆系统演示（无需 API Key） |
| `05_multi_agent.py` | 多 Agent 协作 |

## 10. 技术栈

- **Python ≥ 3.13**，uv 管理项目和依赖
- 核心依赖：`pydantic` / `pydantic-settings` / `httpx` / `rich` / `openai`
- 可选依赖：`numpy`（memory）、`mcp`（MCP 工具集成）、`textual`（TUI）、`pytest` / `pytest-asyncio` / `mypy`（dev）
- 构建系统：Hatchling
