# Agent2 子系统架构文档

> 本文档将 Agent2 项目源码归纳为 **8 个子系统**，阐述各子系统的职责边界、核心抽象、模块组成及相互依赖关系。

## 目录

- [总览](#总览)
- [子系统一览](#子系统一览)
- [1. LLM 抽象层 (`agent2.llm`)](#1-llm-抽象层-agent2llm)
- [2. 工具系统 (`agent2.tools`)](#2-工具系统-agent2tools)
- [3. Agent 核心 (`agent2.agent`)](#3-agent-核心-agent2agent)
- [4. 记忆系统 (`agent2.memory`)](#4-记忆系统-agent2memory)
- [5. 多 Agent 编排 (`agent2.crew`)](#5-多-agent-编排-agent2crew)
- [6. Context 与 Skills (`agent2.context`)](#6-context-与-skills-agent2context)
- [7. MCP 工具桥接 (`agent2.mcp`)](#7-mcp-工具桥接-agent2mcp)
- [8. 应用层 (`agent2.app` / `agent2.app.tui` / `agent2.utils`)](#8-应用层-agent2app--agent2apptui--agent2utils)
- [子系统依赖关系](#子系统依赖关系)
- [双包发布架构](#双包发布架构)

---

## 总览

```
agent2/
├── llm/        ← ① LLM 抽象层
├── tools/      ← ② 工具系统
├── agent/      ← ③ Agent 核心
├── memory/     ← ④ 记忆系统
├── crew/       ← ⑤ 多 Agent 编排
├── context.py  ← ⑥ Context / Skills
├── mcp.py      ← ⑦ MCP 工具桥接
├── app/        ← ⑧ 应用层 (CLI / Chat / TUI / Config / Approval)
└── utils/      ← ⑧ 应用层 (Settings / Logger / JSON Helpers)
```

---

## 子系统一览

| # | 子系统 | 包路径 | 核心职责 | 关键抽象 |
|---|--------|--------|----------|----------|
| 1 | LLM 抽象层 | `agent2.llm` | 统一多 LLM 提供商接口、费用追踪、TPS 计量 | `BaseLLM` / `OpenAILLM` / `Message` / `LLMResponse` |
| 2 | 工具系统 | `agent2.tools` | `@tool` 装饰器自动生成 Schema、工具注册与执行 | `Tool` / `ToolRegistry` / `ToolSchema` |
| 3 | Agent 核心 | `agent2.agent` | ReAct / Plan-and-Execute / 自我反思 三种推理范式 | `BaseAgent` / `ReActAgent` / `PlannerAgent` / `ReflectionMixin` |
| 4 | 记忆系统 | `agent2.memory` | 短期对话窗口 + 长期语义检索 | `WorkingMemory` / `LongTermMemory` |
| 5 | 多 Agent 编排 | `agent2.crew` | 顺序 / 监督者 / 辩论 三种多 Agent 协作模式 | `SequentialCrew` / `SupervisorCrew` / `DebateCrew` |
| 6 | Context / Skills | `agent2.context` | Rules 与 Skills 的发现、解析、注入 | `Context` / `SkillInfo` / `load_context()` |
| 7 | MCP 桥接 | `agent2.mcp` | 外部 MCP 服务器工具虚拟化 | `MCPManager` / `MCPServerConfig` |
| 8 | 应用层 | `agent2.app` / `agent2.utils` | CLI / TUI / 配置 / 审批 / 日志 | `Agent2App` / `ApprovalHandler` / `Settings` |

---

## 1. LLM 抽象层 (`agent2.llm`)

### 职责

统一封装多个 LLM 提供商（OpenAI / DeepSeek / Ollama / vLLM / Qwen / 任何 OpenAI 兼容接口），对上层提供标准化的 `chat()` / `chat_stream()` 接口，并内置费用计算与吞吐量计量。

### 设计原则

- **单协议策略**：以 OpenAI Chat Completions API 作为通用协议，任何兼容提供商无需编写新的 Adapter 子类。
- **内部领域模型解耦**：Agent 核心仅与 `Message` / `ToolSchema` / `LLMResponse` 交互，与 API wire format 完全隔离。
- **自愈式工具调用序列**：`_repair_tool_messages()` 自动修复孤立的 tool_call，避免 400 错误。

### 模块组成

| 模块 | 职责 |
|------|------|
| [`message.py`](src/agent2/llm/message.py) | 基础领域模型：`Role`、`Message`、`ToolCall`、`ToolResult`、`ToolSchema`、`ToolParameter`、`Usage`、`LLMResponse` |
| [`base.py`](src/agent2/llm/base.py) | 抽象基类 `BaseLLM`：定义 `chat()` / `chat_stream()` 接口，内置计时、TPS、费用累计 |
| [`openai.py`](src/agent2/llm/openai.py) | `OpenAILLM(BaseLLM)`：AsyncOpenAI 适配器，消息/工具转换、流式输出、推理模型特殊处理、历史修复 |
| [`pricing.py`](src/agent2/llm/pricing.py) | `ModelPricing`：按前缀匹配主流模型定价，`guess_pricing()` 自动推断 |
| [`__init__.py`](src/agent2/llm/__init__.py) | 工厂函数 `create_llm()`：从配置文件/预设/模型名 构建 `OpenAILLM` 实例 |

### 外部依赖

`openai` (AsyncOpenAI)、`pydantic`、`httpx`

---

## 2. 工具系统 (`agent2.tools`)

### 职责

提供可扩展的工具定义、注册和执行框架。通过 `@tool` 装饰器将普通 Python 函数自动转为 LLM 可调用的工具（含 JSON Schema），并提供一组内置工具覆盖文件操作、代码执行、Shell 命令和 Web 搜索。

### 设计原则

- **内省驱动 Schema 生成**：自动分析函数签名 + 类型注解 + docstring → JSON Schema。
- **同步/异步透明**：同步函数自动通过 `asyncio.to_thread` 异步化。
- **审批级别标注**：每个工具携带 `approval_level` 属性，与审批系统联动。
- **防崩溃执行**：工具执行异常被捕获为结构化错误字符串，不会中断 Agent 循环。

### 模块组成

| 模块 | 职责 |
|------|------|
| [`base.py`](src/agent2/tools/base.py) | `@tool` 装饰器、`Tool` 封装类、`_extract_params()` 参数内省、`_python_type_to_json()` 类型映射 |
| [`registry.py`](src/agent2/tools/registry.py) | `ToolRegistry`：工具目录管理、名称查找、Schema 导出、执行分发、`copy()` 克隆 |
| [`builtin/file_ops.py`](src/agent2/tools/builtin/file_ops.py) | `file_read`（10K 截断）、`file_write`（自动建目录）、`list_directory`（可视化树形列表） |
| [`builtin/shell_exec.py`](src/agent2/tools/builtin/shell_exec.py) | `shell_exec`：异步子进程执行，进程组管理 + SIGKILL 超时保护 |
| [`builtin/python_exec.py`](src/agent2/tools/builtin/python_exec.py) | `python_exec`：受限命名空间内执行 Python 代码，输出截断 |
| [`builtin/web_search.py`](src/agent2/tools/builtin/web_search.py) | `web_search`：DuckDuckGo Instant Answer API 搜索 |

### 工具生命周期

```
定义函数 → @tool 装饰 → 内省签名 → 生成 ToolSchema
  → 注册到 ToolRegistry → LLM 接收 ToolSchema[]
  → LLM 返回 ToolCall → Registry.execute() → 审批检查
  → 执行函数 → ToolResult → 回到 Agent 循环
```

---

## 3. Agent 核心 (`agent2.agent`)

### 职责

实现三种 AI Agent 执行范式——**ReAct**、**Plan-and-Execute**、**自我反思**——构建于共享的 `BaseAgent` 抽象之上。

### 设计模式

- **模板方法**：`BaseAgent` 管理对话生命周期，子类实现 `_run_loop()`。
- **策略模式**：`ReActAgent` 与 `PlannerAgent` 提供不同的推理算法。
- **Mixin 模式**：`ReflectionMixin` 通过多重继承添加自我评价能力。

### 类继承关系

```
                    BaseAgent (base.py)
                   ╱          ╲
          ReActAgent          PlannerAgent
         (react.py)          (planner.py)
               ╲              ╱
            ReflectionMixin (reflection.py)
            (可组合到任一 Agent)
```

### 模块组成

| 模块 | 职责 |
|------|------|
| [`base.py`](src/agent2/agent/base.py) | `BaseAgent`：LLM 交互、工具注册与执行、上下文窗口压缩、系统提示构建、记忆集成、`on_tool_call` 审批钩子、会话序列化 (`fork`/`rewind`/`compact`/`save`/`load`) |
| [`react.py`](src/agent2/agent/react.py) | `ReActAgent`：Thought → Action → Observation 迭代循环；`run_stream()` 流式输出 |
| [`planner.py`](src/agent2/agent/planner.py) | `PlannerAgent`：计划生成（JSON 数组）→ 逐步执行 → 动态重规划 → 结果综合 |
| [`reflection.py`](src/agent2/agent/reflection.py) | `ReflectionMixin`：后处理自评（打分 + 反馈）→ 不合格则迭代改进 |

### 关键机制

- **上下文窗口自管理**：`_maybe_compact()` 在 Token 使用超过阈值时自动压缩历史。
- **流式输出**：`ReActAgent.run_stream()` 支持逐 Token 输出，工具调用在流中透明处理。
- **多态序列化**：`to_dict()` / `from_dict()` 支持通过 `_resolve_agent_class()` 动态解析子类。

---

## 4. 记忆系统 (`agent2.memory`)

### 职责

提供双层认知架构：短期操作上下文（对话滑动窗口）+ 持久化语义检索（TF-IDF 或 OpenAI 向量）。

### 模块组成

| 模块 | 职责 |
|------|------|
| [`base.py`](src/agent2/memory/base.py) | `BaseMemory` 抽象基类：`add()` / `search()` / `clear()` / `get_context()` 统一接口；`MemoryItem` 数据模型 |
| [`working.py`](src/agent2/memory/working.py) | `WorkingMemory`：滑动窗口对话管理，超过 `max_messages` 时自动压缩旧消息为摘要；关键词重叠检索 |
| [`longterm.py`](src/agent2/memory/longterm.py) | `LongTermMemory`：零依赖 TF-IDF 向量化（支持 CJK 分词） / 可选 OpenAI 嵌入；余弦相似度检索；JSON 持久化 |

### 架构要点

- **无外部向量数据库依赖**：纯 Python TF-IDF + 余弦相似度即可工作。
- **多语言分词**：`_tokenize()` 同时处理 ASCII 词 (`\w+`) 和 CJK 汉字（Unicode 范围逐字拆分）。
- **统一 Prompt 注入协议**：`BaseMemory.get_context()` 将检索结果格式化为编号文本块，可直接注入 Agent 系统提示。

---

## 5. 多 Agent 编排 (`agent2.crew`)

### 职责

将多个 Agent 组织为协作团队，支持三种编排拓扑。

### 模块组成

| 模块 | 模式 | 职责 |
|------|------|------|
| [`base.py`](src/agent2/crew/base.py) | — | `BaseCrew` 抽象基类：模板方法 `run()` → `_orchestrate()`，内置日志计时 |
| [`sequential.py`](src/agent2/crew/sequential.py) | 管道式 | `SequentialCrew`：严格线性执行，前序 Agent 输出作为后续 Agent 的上下文输入 |
| [`supervisor.py`](src/agent2/crew/supervisor.py) | 监督者式 | `SupervisorCrew`：中央 LLM 将 Worker Agent 建模为 ToolSchema，动态分派任务；`asyncio.gather` 支持并发执行 |
| [`debate.py`](src/agent2/crew/debate.py) | 辩论式 | `DebateCrew`：独立回答 → 多轮交叉评审 → 综合者 LLM 汇总共识 |

### 协作模式对比

| 维度 | Sequential | Supervisor | Debate |
|------|-----------|------------|--------|
| 拓扑 | 线性管道 | 星型（中央调度） | 全连接网状 |
| 并发 | 否 | 是 (`asyncio.gather`) | 否（轮次制） |
| 适用场景 | 多阶段流水线（规划→编码→审查） | 复杂任务动态分配 | 决策评审、架构设计 |

---

## 6. Context 与 Skills (`agent2.context`)

### 职责

发现、解析、聚合系统提示规则（Rules）和结构化技能包（Skills），注入 Agent 系统提示。

### 核心抽象

| 类/函数 | 职责 |
|---------|------|
| `Context` | 聚合 rules 文本 + skills 元数据，`build_system_prompt()` 渲染为 XML 标签注入 |
| `SkillInfo` | 技能数据容器：`name` / `description` / `path` / `content` / `body` / `source` |
| `load_rules()` | 扫描 `~/.config/agent2/rules`、`~/.agent2/rules`、`<cwd>/.agent2/rules` + 配置内联规则 |
| `parse_skill_markdown()` | 零依赖 YAML frontmatter 解析器（支持多行块标量 `>` / `|`） |
| `discover_skills()` | 多优先级路径搜索：builtin → 用户全局 → 项目级，高优先级按名覆盖低优先级 |
| `load_context()` | 统一入口，返回完整 `Context` 对象 |

### 搜索路径优先级（升序覆盖）

```
builtin skills → ~/.config/agent2/skills → ~/.claude/skills
  → ~/.agent2/skills → .claude/ → .agents/ → .agent2/
```

---

## 7. MCP 工具桥接 (`agent2.mcp`)

### 职责

作为 Model Context Protocol (MCP) 客户端，连接外部 MCP 服务器，将远程工具虚拟化为本地 `Tool` 实例，Agent 和 Crew 可透明调用。

### 核心抽象

| 类/函数 | 职责 |
|---------|------|
| `MCPServerConfig` | Pydantic 配置模型：传输类型（`stdio` / `sse` / `http` / `streamable_http`）、命令参数、环境变量、`always_allow` 安全白名单 |
| `_make_mcp_tool()` | 工厂函数：MCP JSON Schema → `ToolSchema` + `ToolParameter` → 本地 `Tool` 包装 |
| `MCPManager` | 生命周期管理：`connect()` / `connect_server()` / `call_tool()` / `disconnect_server()` / `close()` |

### 关键设计

- **传输无关**：支持 stdio 子进程、SSE 长连接、Streamable HTTP（自动降级）三种传输方式。
- **AnyIO 兼容**：`_start_server_task()` 通过 `asyncio.Queue` + `asyncio.Event` 确保上下文管理器的 enter/exit 在同一 Task 中执行。
- **自动重连**：`call_tool()` 在传输断开时自动重连。

---

## 8. 应用层 (`agent2.app` / `agent2.app.tui` / `agent2.utils`)

### 职责

提供从命令行到沉浸式终端 UI 的完整用户交互层，以及底层配置、日志和 JSON 解析工具。

### 8.1 CLI 与 Chat 入口

| 模块 | 职责 |
|------|------|
| [`app/cli.py`](src/agent2/app/cli.py) | `argparse` CLI：`--model` / `--planner` / `--max-iterations`，支持单次执行和交互 REPL |
| [`app/chat.py`](src/agent2/app/chat.py) | Rich 格式化流式聊天：多行输入、工具调用面板渲染、审批集成 |

### 8.2 配置与安全

| 模块 | 职责 |
|------|------|
| [`app/config.py`](src/agent2/app/config.py) | `~/.config/agent2/config.json` 管理：原子写入 + `.bak` 备份容灾 |
| [`app/approval.py`](src/agent2/app/approval.py) | 四级审批作用域：`ONCE` / `TOOL` / `SESSION` / `ALWAYS`；`yolo_mode` / `allow_all_mode` |
| [`app/common.py`](src/agent2/app/common.py) | 共享常量（`APP_NAME`、`COMPACT_TOKEN_RATIO`） |

### 8.3 TUI 终端界面

基于 [Textual](https://textual.textualize.io/) 框架的沉浸式终端应用。

#### 入口与核心

| 模块 | 职责 |
|------|------|
| [`tui/__init__.py`](src/agent2/app/tui/__init__.py) | 入口函数 `main()`：解析 `--mode` 参数 |
| [`tui/app.py`](src/agent2/app/tui/app.py) | `Agent2App(App)`：应用生命周期、屏幕路由、全局快捷键、MCP 优雅关闭 |

#### 屏幕 (Screens)

| 屏幕 | 职责 |
|------|------|
| [`screens/chat.py`](src/agent2/app/tui/screens/chat.py) | **主屏幕**：斜杠命令路由、流式 Agent 执行、审批流程、Plan 模式集成 |
| [`screens/model_select.py`](src/agent2/app/tui/screens/model_select.py) | 模型切换选择器 |
| [`screens/session_select.py`](src/agent2/app/tui/screens/session_select.py) | 会话列表加载/预览/删除 |
| [`screens/skill_select.py`](src/agent2/app/tui/screens/skill_select.py) | 技能浏览、搜索、重载、调用 |
| [`screens/help.py`](src/agent2/app/tui/screens/help.py) | 快捷键与命令参考 |

#### 组件 (Widgets)

| 组件 | 职责 |
|------|------|
| `InputArea` | 多行输入、文件路径自动补全、历史记录 |
| `MessageList` | 消息滚动容器：Markdown 渲染、代码高亮、流式追加 |
| `StatusBar` | 底栏：模型名 / 模式 / Token 用量 / 费用 / TPS / 延迟 / 会话计时 |
| `NavBar` | 顶部导航：模式标签页 + 会话名 |
| `ToolCard` | 可折叠工具调用卡片：参数 / 结果 / 耗时 / 时间戳 |
| `DiffView` | 文件变更差异对比 |
| `ConfirmModal` | 工具审批确认对话框（作用域选择） |
| `ShortcutHelp` | 内联快捷键面板 |
| `WelcomeBanner` | 启动欢迎页 |

#### 业务逻辑

| 模块 | 职责 |
|------|------|
| [`tui/planner.py`](src/agent2/app/tui/planner.py) | `TUIPlanner`：Plan 模式编排——意图分析 → 计划生成 → 用户确认 → DAG 拓扑执行 → 结果聚合 |
| [`tui/session.py`](src/agent2/app/tui/session.py) | `SessionManager`：会话 JSON 持久化、自动保存、预览列表 |
| [`tui/file_completion.py`](src/agent2/app/tui/file_completion.py) | `FileCompleter`：输入框文件路径自动补全 |
| [`tui/styles.py`](src/agent2/app/tui/styles.py) | TCSS 样式常量集中管理 |

### 8.4 工具模块 (`agent2.utils`)

| 模块 | 职责 |
|------|------|
| [`utils/config.py`](src/agent2/utils/config.py) | `Settings(BaseSettings)`：Pydantic 运行时配置，`AGENT2_` 环境变量前缀 |
| [`utils/logging.py`](src/agent2/utils/logging.py) | `AgentLogger`：结构化 Agent 事件日志，Rich 格式化输出 |
| [`utils/json_helpers.py`](src/agent2/utils/json_helpers.py) | `extract_json()`：多策略 JSON 提取（直接解析 → code block → 贪婪括号匹配） |

---

## 子系统依赖关系

```
                        ┌──────────────────────────────────┐
                        │  ⑧ 应用层 (CLI / TUI / Config)   │
                        └───────┬──────────┬───────────────┘
                                │          │
                   ┌────────────▼──┐  ┌────▼────────────┐
                   │ ⑥ Context     │  │ ⑦ MCP 桥接      │
                   │ (Rules/Skills)│  │ (远程工具虚拟化)  │
                   └────────┬──────┘  └────┬────────────┘
                            │              │
                   ┌────────▼──────────────▼────────────┐
                   │     ③ Agent 核心                    │
                   │  (ReAct / Planner / Reflection)    │
                   └──┬──────────┬──────────┬───────────┘
                      │          │          │
              ┌───────▼───┐ ┌───▼────┐ ┌───▼───────┐
              │ ① LLM     │ │② 工具  │ │ ④ 记忆    │
              │ 抽象层    │ │ 系统   │ │ 系统      │
              └───────────┘ └────────┘ └───────────┘
                      ▲          ▲          ▲
                      └──────────┼──────────┘
                                 │
                   ┌─────────────▼─────────────────────┐
                   │ ⑤ 多 Agent 编排 (Crew)             │
                   │ (Sequential / Supervisor / Debate) │
                   └───────────────────────────────────┘
```

**依赖方向总结**：

| 子系统 | 直接依赖 |
|--------|----------|
| ① LLM 抽象层 | `utils/config`（全局设置） |
| ② 工具系统 | ① LLM（`ToolSchema` 等模型） |
| ③ Agent 核心 | ①②④ |
| ④ 记忆系统 | ① LLM（`Message` 模型）、`utils/config` |
| ⑤ 多 Agent 编排 | ①③ |
| ⑥ Context / Skills | `app/config`（配置目录） |
| ⑦ MCP 桥接 | ①② |
| ⑧ 应用层 | ①②③④⑤⑥⑦（全部） |

---

## 双包发布架构

Agent2 采用双包发布，类似 Ansible / LangChain / Jupyter 模式：

| 包名 | PyPI 发布名 | 内容 | 适用场景 |
|------|------------|------|----------|
| `agent2-core` | [`agent2-core`](src/agent2/) | 核心 SDK（不含 TUI），排除 `src/agent2/app/tui` | 云端容器、自动化脚本、SDK 集成 |
| `agent2` | [`agent2`](packages/agent2/) | 仅包含 TUI 代码 `src/agent2/app/tui`，依赖 `agent2-core` | 终端交互用户 |

通过 `uv workspace` 管理，`agent2` 包在构建时仅包含 TUI 目录，安装时自动拉取 `agent2-core` 作为依赖。
