# Agent2 架构设计

> 从零构建的模块化 Agent 系统，核心目标：**可理解、可组合、可扩展**。

---

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                     Application Layer                   │
│              app.chat (CLI)  /  app.tui (TUI)           │
├─────────────────────────────────────────────────────────┤
│                   Orchestration Layer                    │
│         crew.Sequential / Supervisor / Debate           │
├─────────────────────────────────────────────────────────┤
│                      Agent Layer                        │
│     BaseAgent ← ReActAgent / PlannerAgent               │
│                   ↕ ReflectionMixin                     │
├──────────────┬──────────────┬───────────────────────────┤
│  LLM Layer   │  Tool Layer  │     Memory Layer          │
│  BaseLLM     │  @tool       │  WorkingMemory            │
│  OpenAILLM   │  ToolRegistry│  LongTermMemory           │
│  Message     │  builtin/*   │  BaseMemory               │
├──────────────┴──────────────┴───────────────────────────┤
│                    Foundation Layer                      │
│              utils.config  /  utils.logging              │
└─────────────────────────────────────────────────────────┘
```

**设计原则：自底向上依赖，每层只依赖下层，不反向依赖。**

---

## 2. 核心设计模式

### 2.1 适配器模式 — LLM 抽象

```
BaseLLM (ABC)
  ├── chat(messages, tools) → LLMResponse
  └── chat_stream(messages, tools) → AsyncIterator[str]
        │
        ▼
OpenAILLM ── 封装 openai.AsyncOpenAI
```

- **一个适配器覆盖所有 OpenAI 兼容服务**。不需要为 DeepSeek、Ollama、vLLM 等分别写适配器，只需切换 `base_url` + `api_key`。
- 消息格式在内部用统一的 `Message` 模型表示，只在 `OpenAILLM` 的边界处做格式转换（`_to_oai_message` / `_from_oai_response`）。
- 新增提供商只需新建 `BaseLLM` 子类，不影响上层 Agent 代码。

### 2.2 装饰器 + 自省 — 工具系统

```python
@tool(description="Add two numbers")
def add(a: int, b: int) -> int:
    return a + b
```

- `@tool` 装饰器通过 `inspect.signature()` + `get_type_hints()` 自省函数签名，自动生成 `ToolSchema`（含参数名、类型、是否必填、默认值）。
- 装饰后的对象是 `Tool` 实例，既可当工具注册给 Agent，也可直接 `await add(a=1, b=2)` 调用。
- 同步函数自动通过 `asyncio.to_thread()` 在线程池执行，避免阻塞事件循环。

### 2.3 模板方法模式 — Agent 架构

```
BaseAgent (ABC)
  ├── chat(msg) → str        # 公共入口，管理消息历史
  ├── run(task) → str         # reset + chat
  ├── _run_loop() → str       # 抽象方法，子类实现推理循环
  └── _execute_tool_calls()   # 共享工具执行逻辑
        │
        ├── ReActAgent._run_loop()     # Thought → Action → Observation 循环
        └── PlannerAgent._run_loop()   # Plan → Execute → Replan → Synthesise
```

- `chat()` 负责通用逻辑（初始化 system message、追加 user message、异常处理、记录 assistant 回复）。
- `_run_loop()` 是子类唯一需要实现的抽象方法，专注推理策略。
- `_execute_tool_calls()` 是所有 Agent 共享的工具执行管线。

### 2.4 Mixin 模式 — 横切关注点

```python
class MyReflectiveAgent(ReflectionMixin, ReActAgent):
    pass
```

- `ReflectionMixin` 通过 `super().chat()` 调用被混入类的 `chat()` 获取初始结果，再追加反思循环。
- 可与任意 Agent 类组合，不修改原有代码——真正的开闭原则。

### 2.5 策略模式 — 多 Agent 编排

```
BaseCrew (ABC)
  ├── run(task) → str              # 公共入口
  └── _orchestrate(task) → str     # 抽象编排策略
        │
        ├── SequentialCrew   → 流水线：A → B → C
        ├── SupervisorCrew   → 监督者通过 tool-calling 委派
        └── DebateCrew       → 多轮辩论 + 综合
```

- Agent 对自己是否在 Crew 中运行完全无感知，保持了 Agent 和编排逻辑的解耦。
- `SupervisorCrew` 将工人 Agent 包装为 `ToolSchema`，复用 LLM 的原生 tool-calling 能力做调度——不需要额外的路由/分类逻辑。

### 2.6 工厂模式 — LLM 创建

```
create_llm("deepseek")
  1. 查用户配置文件 ~/.config/agent2/config.json → models["deepseek"]
  2. 查内置预设（openai / ollama）
  3. 作为模型名直接传入 OpenAILLM(model="deepseek")
```

三级 fallback + 模糊匹配，对外只暴露一个函数。

### 2.7 门面与安全沙箱模式 — TUI 交互模式架构

```
User Input
    │
    ▼
ChatScreen (Dispatcher)
    ├── /plan  ──▶ Planner (意图解析 + DAG 任务拆解 + 交互调整)
    ├── /ask   ──▶ Ask Sandbox (只读 System Prompt + Schema 裁剪 + 拦截兜底)
    └── /agent ──▶ Default Autonomous Agent (全功能工具 + HITL 审批)
```

- **门面分发**：`ChatScreen` 集中管理交互状态机，根据当前交互模式将用户意图路由至相应的推理或调度管线。
- **只读沙箱双重防护**：在 Ask 模式下，同时在提示词注入、LLM Tool Schema 列表和运行时工具拦截三层设防，严格确保零文件修改与零进程执行风险。

### 2.8 上下文与技能加载模式 — Context / Skills

```
~/.config/agent2/rules/*.md  ─┐
~/.agent2/rules/*.md         ─┼─▶ load_rules() ─▶ Context.rules_text
<project>/.agent2/rules/*.md ─┘

~/.agent2/skills/<name>/SKILL.md      ─┐
~/.claude/skills/<name>/SKILL.md      ─┼─▶ discover_skills() ─▶ Context.skills
<project>/.agents/skills/<name>/SKILL.md ─┘        │
                                                   ▼
                                    Context.build_system_prompt(base)
                                                   │
                                                   ▼
                                          <rules> / <skills> 注入 system prompt
```

- **Rules 与 Skills 分层注入**：Rules 是短文本约束，Skills 是完整 `SKILL.md` 指令包；两者统一由 `Context` 聚合后注入 system prompt。
- **发现优先级**：全局目录先扫描、项目目录后扫描，同名 Skill 由后扫描目录覆盖，便于项目级定制。
- **按需调用**：除自动注入外，TUI / CLI 均支持 `/skills` 浏览与 `/<skill_name>` 动态调用，避免所有技能内容无条件占据上下文。

### 2.9 MCP 工具桥接模式

```
config.json: mcp_servers
        │
        ▼
   MCPManager.connect()
        │  stdio / SSE
        ▼
   MCP ClientSession ── list_tools() ──▶ MCP tool schema
        │
        ▼
   _make_mcp_tool() ──▶ agent2 Tool 实例
        │
        ▼
   ToolRegistry / Agent 透明调用
```

- **协议适配层**：MCP server 的 `inputSchema` 被转换为 agent2 `ToolSchema`，MCP 返回的 content blocks 合并为字符串结果。
- **生命周期管理**：`MCPManager` 持有 stdio transport 与 `ClientSession` 的 context manager，`close()` 逆序清理，避免子进程泄漏。
- **可选依赖**：`mcp` 作为 optional dependency，未安装时 MCP 功能静默降级，不影响核心 Agent 运行。

### 2.10 多级工具审批作用域模式

```
is_tool_approved(tool)
    ├── conversation_approved  (内存 Set)
    ├── <project>/.agent2/approvals.json
    └── ~/.config/agent2/approvals.json
```

- **四级审批语义**：`once`（仅本次）、`conversation`（当前会话内存）、`project`（项目级文件）、`always`（全局文件）。
- **确认卡即状态机**：`ConfirmCard` 从“批准/拒绝”扩展为五档按钮，并映射 `1/y`、`2/c`、`3/p`、`4/a`、`n/Esc` 快捷键。
- **自动审批开关**：YOLO / Allow-all 可在审批检查前短路，YOLO 额外注入自主决策 system prompt。

---

## 3. 数据流

### 3.1 ReAct Agent 单次执行

```
User Input
    │
    ▼
BaseAgent.chat()
    ├── 追加 system + user message 到 _messages
    ▼
ReActAgent._run_loop()
    │
    ├──▶ LLM.chat(_messages, tools) ──▶ LLMResponse
    │       │
    │       ├── has_tool_calls? ──Yes──▶ _execute_tool_calls()
    │       │                               ├── ToolRegistry.execute()
    │       │                               └── 追加 tool result 到 _messages
    │       │                               └── continue loop ───┐
    │       │                                                     │
    │       └── No (final answer) ──▶ return content              │
    │                                                             │
    └──◀──────────────────────────────────────────────────────────┘
```

### 3.2 PlannerAgent 执行流

```
User Input
    │
    ▼
_generate_plan()  ──▶ LLM 生成 JSON 步骤列表
    │
    ▼
for each step:
    _execute_step()  ──▶ 独立消息上下文 + mini ReAct 循环
    │
    ├── _maybe_replan()  ──▶ LLM 决定是否修正剩余步骤
    ▼
_synthesise()  ──▶ LLM 综合所有步骤结果
```

### 3.3 SupervisorCrew 委派流

```
User Task
    │
    ▼
Supervisor LLM.chat(messages, agent_tools)
    │
    ├── tool_call: delegate_to_researcher(task=...)
    │       │
    │       ▼
    │   researcher.run(task) ──▶ result
    │       │
    │       ▼
    │   追加 tool result 到 supervisor messages
    │       │
    │       └── continue loop ──▶ Supervisor LLM 再次决策
    │
    └── no tool_call ──▶ Final Answer
```

### 3.4 TUI Plan 模式 DAG 调度与 Sub-Agent 隔离执行流

```
User Goal (Plan 模式)
    │
    ▼
LLM generate_plan() ──▶ 提取任务依赖与上下文需求，输出结构化 DAG Plan
    │
    ▼
用户交互调优 / 确认 ("yes" / "确认")
    │
    ▼
退出 Plan 模式，切入 Agent 模式
    │
    ▼
topological_sort_tasks() ──▶ Kahn 算法拓扑排序为有序任务列表
    │
    ▼
for task in ordered_tasks:
    │  1. 抽取声明的特定上下文 (context_needed)
    │  2. 提取前序依赖任务输出 (dependencies results)
    │  3. 构造隔离 Prompt (杜绝全量历史上下文污染)
    │
    ▼
派发独立 SubAgent.run(isolated_prompt)
    │
    ▼
汇总所有子任务执行结果
    │
    ▼
synthesize_plan_results() ──▶ LLM 综合生成统一最终答复
    │
    ▼
成对原子记录 (User Goal, Final Answer) 并持久化
```

---

## 4. 状态管理设计

### 4.1 对话历史

- `_messages: list[Message]` 是 Agent 的核心状态，完整保留所有角色的消息（含 tool call 和 tool result）。
- `chat()` 保持历史实现多轮对话；`run()` 每次 `reset()` 实现单次执行语义。
- `PlannerAgent._execute_step()` 使用**独立的消息列表**，避免步骤间上下文干扰。

### 4.2 Agent 克隆

- `fork()` 通过浅拷贝 Agent + 深拷贝 `_messages` + 复制 `ToolRegistry`，产生独立副本。
- 适用于并行探索、A/B 测试不同策略。

### 4.3 序列化

- `to_dict()` 序列化：Agent 类型名、配置、消息历史、工具名列表、子类扩展状态（`_get_extra_state()`）。
- `from_dict()` 反序列化：按类型名解析子类、从 builtin 模块自动恢复工具实例，并执行工具消息自愈。

### 4.4 工具调用完整性保护 (Tool Call Repair Protocol)

- OpenAI 规范约束：如果 Assistant 发起包含 `tool_calls` 的消息，其后续消息中必须且仅能紧跟对应 `tool_call_id` 的 Tool 消息。
- 系统在 `BaseAgent.chat()`、`BaseAgent.from_dict()` 以及 `OpenAILLM._repair_tool_messages()` 中内置自愈机制：检测并自动补齐因异常、取消或旧存档缺失的 Tool 响应，杜绝 API 400 校验错误。

### 4.5 TUI 模式状态机与上下文隔离

- **模式生命周期**：`ChatScreen` 与 `Agent2App` 协同维护当前活动模式。在 Plan 模式下保持临时未确认计划草稿 (`_pending_plan`)；用户确认后状态机原子转换回缺省 Agent 模式。
- **子任务执行上下文隔离**：每个子任务派发时采用专职 `SubAgent` 实例，不共享主 Agent 的多轮对话上下文 `_messages`，仅显式透传其依赖项结果，从根本上防止多步骤任务导致的上下文过载与噪声干扰。

### 4.6 对话回退与分叉 (Rewind & Fork)

- **回退 (Rewind)**：`rewind(turns)` 按轮次移除最近的 user→assistant 完整对话，`rewind_to(index)` 精确截断到任意历史消息位置。TUI 层在此基础上实现 `/rewind` 命令（回退最近一轮）和消息级 Point Rewind（点击任意消息的 ⏪ 按钮回退到该处）。
- **分叉 (Fork)**：在 `fork()` 克隆完整 Agent 状态的基础上，TUI 层实现 `/fork` 命令（克隆完整会话）和消息级 Point Fork（从任意历史节点创建新 session 分支）。
- **UI 交互**：消息选中态（高亮色块背景与操作按钮栏，无边框描边）+ 上下文操作按钮（Rewind / Retry / Fork），Escape 取消选择。

### 4.7 TUI 扁平无边框设计与下拉选择器 (Flat Borderless Design & Dropdown)

- **全无边框设计原则**：移除所有 UI 容器、卡片及输入框的实线边框（`border: none`），仅通过背景明暗对比建立视觉层级；清除组件间 padding/margin 产生无缝贴合的现代极简排版。
- **底部状态栏与流式布局**：取消固定 dock 顶层，将状态栏调整至视窗最下方单行，位于输入区域之下，使用竖向流式布局与 `#messages` (1fr) 协同工作，彻底消除 dock 区域层叠冲突。
- **下拉式模型选择器**：选用 Textual `Select[str]` 组件实现紧凑 drop-down menu，具备即打即搜能力并兼容自定义模型文本输入，大幅精简模态尺寸。

### 4.8 极简 Copilot CLI 风格 TUI 视窗与模型/Host 智能解析

- **现代极简多视窗体系**：
  - **顶部标签栏 (`TopTabBar`)**：`Current`、`Sessions`、`Skills` 紧凑水平并排排列，支持鼠标交互、快捷键（`F1`–`F3`）以及 `Tab` / `Shift+Tab` 即时循环切换上一/下一个面板。
  - **全屏模态选择系统**：`SessionSelectScreen`、`SkillSelectScreen` 与 `ModelSelectScreen` 统一对齐 Copilot CLI 风格，具备顶栏状态联动、Tip 引导条目、全屏饱和亮蓝高光选条（`#1f6feb`）以及实时多维关键词过滤。
- **智能提供商解析与 Host 优雅降级**：
  - `resolve_provider_or_host(provider, base_url)` 建立自底向上的提供商识别链路：
    1. 显式有效 `provider` 优先；
    2. 若缺省或为通用占位符，检查 `base_url` 是否匹配已知提供商（OpenAI, DeepSeek, Anthropic, SiliconFlow, Ollama 等）；
    3. 若无法确定，提取 `base_url` 的网络 host（包含非标准端口，如 `localhost:11434` 或内网 IP）；
    4. 针对 Rich Markup 语法对方括号进行严格转义（`\[provider]`），防止样式标签解析吞没。
- **输入上下文双状态栏架构**：
  - `ContextBar`（输入框正上方）：聚合当前工作路径、请求 Spinner 耗时、Token 用量与模型提供商标注。
  - `StatusBar`（终端底行）：轻量展示全局快捷键引导与模式徽标（`AGENT` / `PLAN` / `ASK` / `YOLO` / `ALLOW-ALL`）。

### 4.9 Token 用量状态持久化与 Plan 子任务聚合

- **Session 级 usage**：`SessionManager.save()` 持久化 `usage` 字段；`restore_agent()` 恢复时优先读取已保存 usage，旧会话则按消息内容估算，并强制覆盖当前 LLM 计数器。
- **模型切换保留**：`Agent2App.switch_model()` 在创建新 LLM 实例后回填 `total_usage` / `last_usage`。
- **Plan 子任务聚合**：`_run_plan_execution()` 为每个 subtask 创建独立 sub-agent，并在 `finally` 中将 `subagent.llm.total_usage` 累加到父会话，失败或取消的子任务也已消耗的 Token 同样计入。
- **实时同步**：`on_thought_received()`、`on_tool_call_completed()` 及三个 worker 的 `finally` 均调用 `_sync_status_bar()`，保证长任务期间与异常路径下 `ContextBar` 的 Token 计数不归零。

---

### 4.10 内联快捷键面板与统一面板导航 (Inline Shortcut Help & Panel Navigation)

- **内联帮助取代独立模态**：帮助信息由独立 `HelpScreen` 模态迁移为常驻 `ShortcutHelp` 内联面板（`widgets/shortcut_help.py`），紧贴输入框上方渲染；空输入时 `?` 即时切换显隐，开始输入或切换面板时自动收起。
- **统一的面板切换语义**：顶栏精简为 `Current` / `Sessions` / `Skills` 三档，`Tab` / `Shift+Tab` 在输入框、消息区与顶栏标签间统一映射为「立即切换上一/下一个顶层面板」，`TopTabBar.cycle_tab(direction)` 双向循环并广播 `TabSelected`；当输入框补全浮层可见时 `Tab` / `Shift+Tab` 改为候选循环（见 4.11）。
- **状态同步单一来源**：`StatusBar.active_tab` 响应式属性作为当前面板的唯一真源，底部提示行据此渲染 Chat / Sessions / Skills 三套按键提示，避免多组件状态不一致。
- **两段式破坏性操作确认**：会话删除采用 `Ctrl+X`（armed）→ `X`（confirm）两段式交互，armed 期间任意其它键或 `Esc` 取消，降低误删风险。

---

### 4.11 请求级性能指标与面板导航健壮性 (Request Timing & Panel Navigation Robustness)

- **计时埋点下沉到 LLM 基类**：`BaseLLM` 提供 `_begin_request()` / `_end_request(usage)` 钩子，在抽象层统一维护 `last_request_duration`、`last_request_started_at` / `last_request_finished_at`、`total_generation_time` 与 `last_tps`，子类（`OpenAILLM`）只需在请求前后各调用一次，避免各提供商重复实现；`_end_request` 可重复调用且仅首次结算。
- **TPS 计算与回退**：优先采用 provider 记录的 `last_tps = completion_tokens / duration`；对不含计时元数据的自定义/测试 LLM，`ChatScreen._update_tps_from_run()` 回退为 `total_usage.completion_tokens` 增量 / 墙钟时长。
- **慢操作回落 (Long-Operation Fallback)**：以 `LONG_OPERATION_SECONDS = 5.0` 为阈值，`ChatScreen._record_long_operation()` 记录耗时 ≥5s 的工具调用与 LLM 请求，并在 `StatusBar` / `ContextBar` 以 `↳ <操作> 6.3s (started HH:MM:SS)` 呈现；通过 `_last_long_operation_started_at` 去重，仅保留最新一次。
- **指标生命周期**：`_reset_session_metrics()` 在新建/切换会话时统一归零计时器、TPS 与慢操作读数，避免跨会话指标残留。
- **面板导航健壮性**：各选择视窗不再以 `screen_stack[-2]` 猜测宿主，而是逆序扫描屏幕栈中持有对应 `_open_*_dialog` 方法的 `ChatScreen`，并以 `call_next()` 延后压栈；`ChatScreen._on_screen_resume` 在任意模态退出后将顶栏高亮复位为 `Current`，保证多层模态往返后视图与顶栏状态一致。

---

## 5. 配置层次设计

```
优先级（高 → 低）：
  代码参数 > 环境变量 (AGENT2_*) > 配置文件 (~/.config/agent2/config.json) > 内置默认值
```

- **Settings**（`pydantic-settings`）：环境变量自动绑定，单例模式。
- **AppConfig**（`pydantic.BaseModel`）：
  - **服务商与模型正交解耦**：采用 `providers`（管理端点与凭据）与 `models`（模型别名与参数）分离的无冗余数据组织方式。
  - **继承与自愈**：同一 Provider 下的多个 Model 自动继承 `base_url` 与 `api_key`；兼容旧版 `llm` 配置。
  - **Agent 行为配置**：`max_iterations`（默认 50，兼容 `max_turns` / `max_rounds`）、`rules` inline 规则、`mcp_servers` MCP 服务器。
- **Provider 推导**：从 base_url 智能提取服务商标识（deepseek / nvidia / siliconflow / localhost 等）。
- **last_model**：文件持久化上次选择，提升交互体验。


---

## 6. 日志与工具函数设计

- 不使用 Python `logging` 模块，而是自建基于 `rich` 的结构化日志——因为 Agent 推理过程的日志需要**语义化展示**（Thought / Action / Observation 用不同颜色和面板区分），标准 logging 的 level-based 方式不适合。
- 通过 `verbose` 开关控制是否输出，而非 log level。
- 每个 Agent / Crew 持有独立的 `AgentLogger` 实例，互不干扰。
- 文件日志写入使用 `threading.Lock` 保证多协程/多线程下的并发安全。
- `utils.json_helpers.extract_json()` 提供从 LLM 输出中鲁棒提取 JSON 的共享工具函数，供 `planner.py`、`reflection.py` 等模块复用。
