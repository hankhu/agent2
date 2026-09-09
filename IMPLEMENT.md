# Agent2 实现要点

> 值得关注的实现细节、技巧和权衡取舍。

---

## 1. LLM 层

### 1.1 懒初始化 AsyncOpenAI 客户端

```python
# openai.py
def _get_client(self) -> Any:
    if self._client is None:
        ...
        self._client = AsyncOpenAI(**kwargs)
    return self._client
```

- `AsyncOpenAI` 实例在首次 `chat()` 时才创建，而非构造函数中。
- 好处：构造 `OpenAILLM` 不需要网络连接，不会因缺少 API key 而抛异常；方便测试和序列化。

### 1.2 base_url 自动补全 `/v1`

```python
if not any(v in base_url for v in ("/v1", "/v2", "/v3", "/v4")) and not base_url.endswith("/openai"):
    base_url = base_url.rstrip("/") + "/v1"
```

- 用户经常忘记加 `/v1` 后缀，框架自动处理。
- 排除已有版本路径和 Azure 风格 `/openai` 后缀的情况。

### 1.3 tool_call arguments 的健壮解析

```python
args = tc.function.arguments
if isinstance(args, str):
    try:
        args = json.loads(args)
    except json.JSONDecodeError:
        args = {"raw": args}  # 降级为原始字符串
```

- OpenAI 返回的 arguments 可能是 JSON 字符串或已解析的 dict。
- JSON 解析失败时不抛异常，而是包装为 `{"raw": ...}` 继续运行。

### 1.4 create_llm 模糊匹配

```python
for candidate in (cfg_key_l, cfg_model_l):
    if candidate and (candidate == key or candidate in key):
        if len(candidate) > best_len:
            best_len = len(candidate)
            best_entry = cfg_entry
```

- 允许用户用 `"小米Mimo-v2.5"` 匹配配置中的 `"mimo-v2.5"`——子串包含即可，取最长匹配避免歧义。

### 1.5 OpenAI Tool 消息配对与自动修复

```python
@staticmethod
def _repair_tool_messages(messages: list[Message]) -> list[Message]:
    # 扫描 assistant 消息中的 tool_calls
    # 若后续未紧随对应的 tool 消息，则自动补齐合成的错误结果消息
```

- OpenAI 规范要求每个 `tool_call_id` 必须紧随一条 `role="tool"` 的响应消息，否则接口会直接返回 400 Bad Request。
- 当用户在工具执行中途强制中断、连接断开或加载异常历史时，`OpenAILLM` 与 `BaseAgent` 自动检测缺失的 `tool_call_id` 并插入 `Tool execution did not return a result.` 错误消息，保证发往 API 的上下文结构严格合法。

---


## 2. 工具系统

### 2.1 类型注解 → JSON Schema 映射

```python
_TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
```

- 只映射 JSON Schema 的基础类型，泛型容器（`list[X]`、`dict[X, Y]`）通过 `get_origin()` 判断。
- `Optional[X]` / `Union[X, None]` / `X | None` 自动解包为内层类型。
- 不支持的类型统一降级为 `"string"`，保证不崩溃。

### 2.2 同步函数异步化

```python
if self._is_async:
    result = await self.func(**kwargs)
else:
    result = await asyncio.to_thread(self.func, **kwargs)
```

- 同步工具函数被包装到 `asyncio.to_thread()` 中执行，不阻塞事件循环。
- 构造时通过 `inspect.iscoroutinefunction()` 判断，运行时零开销分发。

### 2.3 工具执行错误不中断 Agent

```python
try:
    result = await self.func(**kwargs)
    return str(result)
except Exception as e:
    return f"Error executing tool '{self.name}': {type(e).__name__}: {e}"
```

- 工具异常被捕获并转为错误文本返回给 LLM，而非向上传播。
- 让 LLM 有机会根据错误信息调整策略（换工具、修改参数等）。

---

## 3. Agent 层

### 3.1 ReAct 循环的终止条件

```python
if response.has_tool_calls:
    ...  # 执行工具，continue
# No tool calls → final answer
return response.content or ""
```

- **无 tool_call = 最终答案**——这是 ReAct 模式的核心约定。
- 不依赖特殊 token 或关键词判断结束，完全由 LLM 的行为（是否发起 tool call）决定。

### 3.2 PlannerAgent 步骤隔离

```python
async def _execute_step(self, ...):
    messages = [
        Message.system(system),
        Message.user(f"Execute step {step_number}: {step_description}"),
    ]
    # 独立的消息列表，不共享 self._messages
```

- 每个步骤使用独立的消息上下文，包含：当前步骤描述、完整计划概览、前序步骤结果摘要。
- 防止步骤间消息积累导致 context window 溢出或上下文污染。

### 3.3 前序结果注入避免重复调用

```python
_EXECUTOR_PROMPT = """...
IMPORTANT — Avoid redundant tool calls:
- Read the previous step results above carefully before calling any tool.
- If the data you need is already present in a previous result, use that value directly.
- Do NOT call a tool again for data that has already been fetched.
..."""
```

- 前序步骤的结果（截断到 2000 字符）被注入到 executor prompt 中。
- 配合显式指令，减少 LLM 发起重复工具调用。

### 3.4 计划解析的 fallback

```python
try:
    plan = extract_json(content)  # 容忍 markdown 代码块、正则提取
except json.JSONDecodeError:
    return [line.strip() for line in content.strip().split("\n") if line.strip()]
```

- 使用共享的 `extract_json()` 工具函数（`utils.json_helpers`），依次尝试 Markdown 代码块提取、正则匹配 JSON 数组/对象、纯文本解析。
- 最终 fallback 到按行切分，确保即使 LLM 输出格式不完美也能提取出计划步骤。

### 3.5 ReflectionMixin 的 super() 链

```python
class ReflectionMixin:
    async def chat(self, msg):
        result = await super().chat(msg)  # 调用被混入类的 chat()
        ...
    async def _retry_with_feedback(self, task, previous, feedback):
        return await super().chat(retry_prompt)  # 重试也走完整推理循环
```

- 利用 Python MRO（Method Resolution Order），`super().chat()` 沿着 MRO 链调用实际 Agent 类的 `chat()`。
- **重试时同样通过 `super().chat()` 发起完整推理循环**，保留工具调用能力（而非退化为裸 `llm.chat()`）。
- `ReflectionMixin` 必须在继承顺序中排在 Agent 类之前：`class X(ReflectionMixin, ReActAgent)`。
- JSON 评估解析使用 `extract_json()`，解析失败时返回 `passed=False` 并附带警告日志（不再静默假设通过）。

### 3.6 序列化 hook 机制

```python
# BaseAgent
def _get_extra_state(self) -> dict[str, Any]:
    return {}

# PlannerAgent
def _get_extra_state(self) -> dict[str, Any]:
    return {"enable_replan": self.enable_replan, "max_step_iterations": self.max_step_iterations}
```

- 基类提供空 hook，子类覆盖以序列化自己的额外状态。
- 反序列化时 `from_dict()` 先构造对象再调用 `_load_extra_state()` 恢复。

### 3.7 工具自动恢复

```python
import agent2.tools.builtin as builtin_module
for attr_name in dir(builtin_module):
    val = getattr(builtin_module, attr_name)
    if isinstance(val, Tool) and val.name in tool_names:
        resolved_tools.append(val)
```

- 反序列化时，按保存的工具名列表从 `builtin` 模块中自动查找并恢复 `Tool` 实例。
- 不序列化工具函数本身——工具是代码，不是数据。

### 3.8 工具执行防御性包装与消息闭环

```python
# BaseAgent._execute_tool_calls / TUIReActAgent._execute_tool_calls
try:
    output = await self.tool_registry.execute(tc.name, **tc.arguments)
except Exception as exc:
    output = f"Error executing {tc.name}: {exc}"
    is_error = True
```

- 在 Agent 的工具执行管线中，对每个 `tool_call` 实行全量异常捕获。即使底层工具注册表或执行过程发生非预期异常，也会将错误捕获并封装为 `Message.tool(tc.id, output, is_error=True)`，保证 `tool_call_id` 与 tool message 严格一一对应，杜绝上下文不完整导致的崩溃。

---


## 4. 记忆系统

### 4.1 WorkingMemory 压缩策略

```python
async def _compress(self):
    keep_count = self.max_messages // 2
    old_messages = self._messages[:-keep_count]
    self._messages = self._messages[-keep_count:]
    # 摘要：提取每条消息前 100 字符
```

- 保留最近一半消息，旧消息提取内容首 100 字符拼接为摘要。
- 这是**提取式摘要**，不调用 LLM——在实际生产中可替换为 LLM 生成式摘要。

### 4.2 TF-IDF 纯 Python 实现

```python
def _embed_tfidf(self, text):
    words = self._tokenize(text)
    tf = Counter(words)
    vector = [0.0] * len(self._vocab)
    for word, count in tf.items():
        vector[self._vocab[word]] = (count / total) * self._idf.get(word, 1.0)
    return vector
```

- **零外部依赖**的嵌入方案——不需要 numpy、transformers 或 API 调用。
- 词表动态增长：新词出现时自动扩展 `_vocab`。
- 每次 `add()` 后重建 IDF（`_rebuild_idf`）并通过 `_recompute_tfidf_vectors()` 更新所有已有文档的嵌入向量，保证新老文档向量标准一致。
- 分词器支持 CJK 字符级切分（`[\u4e00-\u9fff]|\w+`），无需额外分词库。
- 向量长度不固定，`_cosine_similarity` 中用零填充对齐。

### 4.3 余弦相似度的零填充

```python
max_len = max(len(a), len(b))
a = a + [0.0] * (max_len - len(a))
b = b + [0.0] * (max_len - len(b))
```

- 因为词表会随新文档增长，查询向量可能与文档向量长度不同。
- 用零填充对齐——`_recompute_tfidf_vectors()` 已确保所有文档向量使用同一 IDF 权重。

### 4.4 持久化格式

- 整个记忆状态（文档列表含嵌入向量 + 词表 + IDF 字典）序列化为单个 JSON 文件。
- 加载时容错：JSON 解析失败则静默忽略，不阻塞启动。

---

## 5. 多 Agent 编排

### 5.1 SupervisorCrew 将 Agent 建模为 Tool

```python
ToolSchema(
    name=f"delegate_to_{agent.name}",
    description=f"Delegate a sub-task to the '{agent.name}' agent. ...",
    parameters=[ToolParameter(name="task", type="string", required=True)],
)
```

- 每个工人 Agent 变成 Supervisor LLM 可调用的 "tool"。
- 复用 LLM 原生的 function calling 能力做路由，不需要额外的分类器或规则引擎。
- Supervisor 的 system prompt 中注入各 Agent 的角色描述（截取 system_prompt 前 100/200 字符）。
- 当 Supervisor 同时委派多个 worker 时，通过 `asyncio.gather` 并发执行，避免不必要的串行等待。

### 5.2 DebateCrew 的批评轮次

```python
for round_num in range(1, self.rounds + 1):
    for agent in self.agents:
        others_views = ...  # 排除自身的其他 Agent 观点
        critique_prompt = f"...Consider the other perspectives. Critique them..."
        result = await agent.run(critique_prompt)
```

- 每轮每个 Agent 看到其他所有 Agent 的最新回答，进行批评和修正。
- 使用 `agent.run()`（而非 `chat()`），每轮重置上下文，避免多轮积累导致 context 膨胀。

---

## 6. 应用层

### 6.1 模型可见性过滤

```python
def _visible_model(item):
    if item.get("api_key") or settings.api_key:
        return True
    return _is_local_or_lan(item.get("base_url"))
```

- 远程模型没有 API key 时自动隐藏——避免用户选中后因认证失败而困惑。
- 本地/局域网地址（localhost、10.x、192.168.x、172.16-31.x、`.local`）始终显示，因为它们通常不需要 key。

### 6.2 模型选择的模糊匹配

- 支持数字序号、精确名称、子串匹配（双向：输入包含配置名 或 配置名包含输入）。
- 适配中文用户习惯：`"小米Mimo"` 可匹配配置中的 `"mimo-v2.5"`。

### 6.3 斜杠命令与聊天的分离

```python
if user_input.startswith("/"):
    ...  # 处理命令，continue
await agent.chat(user_input)  # 非命令才发给 Agent
```

- `/model`、`/tools`、`/clear`、`/help` 等命令在应用层处理，不进入 Agent 的消息历史。
- `/model` 切换时重新调用 `create_llm()` 创建新 LLM 实例并赋值给 Agent，不重置对话历史。

### 6.4 URL 服务商智能推导 (`_provider_from_url`)

```python
def _provider_from_url(url: str | None) -> str:
    # 提取域名或主机名：https://api.deepseek.com/v1 -> deepseek
    # http://localhost:11434/v1 -> localhost
```

- 自动解析 base_url 的 host 与二级域名，识别 `deepseek`、`nvidia`、`siliconflow`、`localhost` 等，简化终端列表显示，替代冗长难读的完整 URL。

### 6.5 会话标题清洗与正则提取 (`_extract_title`)

```python
text = re.sub(r"<file\b[^>]*>.*?</file>", " ", text, flags=re.S)
text = re.sub(r"<directory\b[^>]*>.*?</directory>", " ", text, flags=re.S)
text = re.sub(r"#(?:file|dir)\s+\S+", " ", text)
```

- 在保存或展示会话时，自动剥离首条消息中注入的文件/目录大段 XML/Markdown 上下文，压缩空白字符并截取至 60 字符，生成干净利落的人类可读会话标题。

### 6.6 TUI 输入历史与草稿状态机 (`ChatInput`)

```python
# input_area.py
# ↑: 向上回溯历史；首次触发保存当前输入的 _draft
# ↓: 向下浏览历史；到底部时自动恢复 _draft
```

- `ChatInput` 拦截 `_on_key` 事件，在未处于补全列表时响应 `Up` / `Down` 键。
- 自动过滤斜杠命令（`/model` 等）避免历史污染；回车发送时追加历史并重置草稿指针。

### 6.7 TUI 交互式模态选择器 (`SessionSelectScreen` / `ModelSelectScreen`)

- **SessionSelectScreen**：模态弹窗表格展示所有已存会话（序号、标题、ID 前缀、保存时间）。支持 `Enter` 恢复会话、`e`/`r` 就地编辑会话标题、`d` 快捷删除会话，以及 `Esc` 退出管理。
- **ModelSelectScreen 动态过滤**：挂载搜索框并监听 `Input.Changed` 事件，用户键入关键词时实时重建表格数据源，支持按序号或模型名称快速回车选择。


### 6.8 无冗余配置架构与服务商继承 (`AppConfig.resolve_model`)

```python
# config.py
# 1. providers 管理公共端点与凭据 (base_url / api_key)
# 2. models 仅定义模型别名并指向所属 provider
# 3. resolve_model 自动合并 provider 属性与 model 定制参数
```

- 将服务商基础设施（`providers`）与具体模型（`models`）解耦，彻底消除在每个模型中重复配置 `base_url` 与 `api_key` 的冗余。
- 在 `AppConfig._normalize_legacy_config` 中内置向后兼容转换，支持平滑迁移旧版 `llm` 配置。

### 6.9 会话重命名与标题保留机制 (`SessionManager.rename` / `/rename`)

```python
# session.py
# 1. /rename <title> 显式更新当前 app.session_title 并实时回写磁盘
# 2. SessionManager.save() 优先保留已重命名的标题，防止后续自动保存回退覆盖
```

- 允许用户在 TUI 界面随时通过 `/rename <new-title>` 为会话指定语义化标题。
- `SessionManager.save()` 在保存时若未显式传入新标题，会优先保留磁盘既有标题，确保重命名在后续多轮对话自动持久化时不被覆盖。

### 6.10 TUI 扁平化视觉体系 (`styles.py`)

- **结构去厚重**：将全量 `border: round` 与 `border: thick` 移除，代之以细致的单线边框（`solid`）、微妙背景灰阶层级（`$panel` / `$surface-darken-1`）与彩色左指示条（`border-left: solid`）。
- **组件扁平化**：
  - `UserMessage` / `AssistantMessage`: 采用轻量底色与单侧状态指示条，去除厚重气泡边框。
  - `ToolCard` / `DiffView`: 扁平卡片背景与左侧警戒/重点边条，紧凑美观。
  - 模态面板 (`ModelSelectScreen` / `SessionSelectScreen` / `ConfirmModal`): 统一扁平化边框与无外边距紧凑布局。

### 6.11 TUI 三大多模态交互模式与只读沙箱双重防护 (`TUIReActAgent.mode`)

- **模式定义与无缝切换**：支持 Agent（`/agent`）、Plan（`/plan`）、Ask（`/ask`）三种交互模式，可通过 CLI `--mode <mode>` 指定初始模式或在聊天中使用斜杠命令随时切换。
- **Ask 模式双重安全沙箱**：
  1. *Schema 级过滤*：在 `_run_loop()` 中，向 LLM 声明工具时仅透传 `SAFE_TOOLS`（`file_read`, `read_file`, `list_directory`, `web_search`），从源头上隐藏写和执行工具（如 `file_write`, `shell_exec`, `python_exec` 等）。
  2. *运行时拦截兜底*：在 `_execute_tool_calls()` 中硬性校验工具名称，若命中非只读工具直接注入错误观察（`is_error=True`），杜绝 LLM 幻觉生成越权调用。
  3. *动态切换系统提示词*：进入 Ask 模式自动应用只读专用 System Prompt，切回 Agent 模式自动复原。

### 6.12 Plan 模式 DAG 任务拆解、拓扑调度与 Sub-Agent 上下文隔离 (`planner.py` / `screens/chat.py`)

- **意图分析与结构化生成**：`generate_plan()` 引导 LLM 输出包含任务 ID、依赖列表 (`dependencies`) 与特定上下文需求 (`context_needed`) 的标准 JSON，并通过 `format_plan_markdown()` 格式化为直观的 Markdown 表格。
- **动态调优与确认状态机**：支持在 Plan 模式下多轮对话修改计划；`is_plan_confirmation()` 智能识别确认词（如 `yes`、`确认`、`ok`、`同意`、`开始` 等），确认后平滑退出 Plan 模式并进入 Agent 模式执行。
- **Kahn 算法拓扑排序 (`topological_sort_tasks`)**：根据依赖图解析任务拓扑序列；具备自愈降级保护，检测到环路或孤岛时安全回退至原始任务列表。
- **Sub-Agent 隔离派发与防污染执行**：针对每个子任务动态构建独立的 `TUIReActAgent`，**仅向其 prompt 注入所声明需要的上下文及前序依赖任务的产出**，杜绝全量历史上下文膨胀与长上下文注意力干扰。
- **最终结果归纳与消息原子配对**：各子任务执行完毕后，调用 `synthesize_plan_results()` 统一生成最终回答，并在主会话消息历史中成对追加 `(Message.user(original_goal), Message.assistant(final_answer))`，保障会话存档与后续多轮对话的上下文结构规范。

### 6.13 顶部状态栏模式徽标 (Mode Badge) 响应式渲染 (`StatusBar`)

- `StatusBar` 定义 reactive `mode` 字段；`ChatScreen._sync_status_bar()` 实时向状态栏同步当前模式。
- 渲染器使用 Rich 颜色标签呈现醒目徽标：`[AGENT]`（绿色）、`[PLAN]`（黄色）、`[ASK]`（青色），使用户时刻清晰感知当前上下文所处的操作模式与安全权限级别。

### 6.14 流式嵌入确认卡片 (`ConfirmCard`) 与工具执行结果控制 (`ToolCard` / `Ctrl+O`)

- **流式嵌入与卡片化 (`ConfirmCard`)**：
  - 将工具审批从阻断式弹层重构为嵌入 `MessageList` 消息流的轻量卡片，自然随历史消息滚动。
  - 单行紧凑显示提示标题、高亮工具名与彩色参数键值（`key='value'`）。
  - 支持 `file_write` 下方直接内联彩色 Diff 预览。
  - 挂载即自动获得焦点（聚焦在 `[y] Approve`），支持 `Left` / `Right`（`h` / `l`）循环切换按钮焦点，支持 `y` / `n` / `a` / `Esc` 全套单键快捷操作。
  - 按钮采用透明底色（`background: transparent`），仅以绿色/红色/黄色高亮文字，极简无多余边距。
  - 审批完成后，按钮栏原子替换为 `✓ Approved` / `✗ Rejected` / `✓ Always Allowed` 状态标识，焦点自动交还输入框 `#chat-input`。
- **工具执行结果面板（Result Panel）默认折叠与快捷切换**：
  - `ToolCard` 中的工具执行结果面板（`.tool-result`）统一默认呈折叠状态（`collapsed=True`），边距紧凑化（`padding: 0 1; margin: 0;`），避免大量工具输出占用过多屏幕空间。
  - `ChatScreen` 注册全局快捷键 `Ctrl+O`（`action_toggle_tool_results`），一键批量展开或收起所有工具执行结果面板。

### 6.15 消息级 Point Rewind / Fork 与 SelectableMessage 体系 (`message_list.py` / `screens/chat.py`)

- **`SelectableMessage` 基类**：`UserMessage` 和 `AssistantMessage` 继承自 `SelectableMessage(Vertical)`，支持 `can_focus=True`、点击/焦点触发 `select()` 排他选中、挂载 `⏪ Rewind` 和 `🍴 Fork` 操作按钮。
- **事件解耦**：按钮点击通过 `RewindRequested` / `ForkRequested` 自定义 Textual `Message` 事件冒泡至 `ChatScreen`，事件携带 `message_widget` 引用与 `message_index` 索引。
- **索引解析容错 (`_resolve_message_index`)**：优先使用挂载时记录的 `message_index`；若索引失效（历史被修改），退化为按内容反向匹配 `agent._messages`，保证健壮性。
- **Rewind 语义区分**：UserMessage 上 Rewind 移除该消息及之后所有消息（`rewind_to(idx, inclusive=False)`），并将用户文本填入输入框；AssistantMessage 上 Rewind 保留该回复（`rewind_to(idx, inclusive=True)`），截断后续对话。
- **Fork 语义区分**：UserMessage 上 Fork 截取该消息之前的历史创建新 session；AssistantMessage 上 Fork 截取到该回复（含）的历史创建新 session。
- **选中态样式**：选中消息高亮背景 + `border-left: double` 双线指示条；`.message-actions` 按钮栏默认 `display: none`，选中或 `focus-within` 时 `display: block`。

### 6.16 /retry 重试、平滑贴底滚动、代码块/长文折叠与多轮继续 (`screens/chat.py` / `widgets/message_list.py` / `app.py`)

- **`/retry` 与消息级重试**：
  - `UserMessage` / `AssistantMessage` 增加 `🔄 Retry` 操作按钮，触发 `RetryRequested` 事件。
  - 在 `UserMessage` 上重试：回退到该消息之前（`rewind_to(idx, inclusive=False)`），重新向 agent 发送该提问。
  - 在 `AssistantMessage` 上重试：向前查找对应的前序用户提问（`Role.USER`），回退到该提问之前并重新生成。
  - `/retry` 指令：快速对最后一轮对话执行相同回退与重新执行。
- **平滑贴底滚动 (Sticky Scroll)**：
  - `MessageList` 继承自 `ScrollableContainer`，初始化调用 `self.anchor(True)`。
  - 当 `not self._anchor_released or self.is_vertical_scroll_end` 时，收到新消息平滑滚至最底端。
  - 用户向上翻看历史时，保持当前阅读视窗；用户滚回底部或提交新输入时，自动重置贴底锚点。
- **代码块与大段文字折叠**：
  - `AssistantMessage` 通过正则 `_split_markdown_segments` 分解段落：超过 4 行的代码块折叠为 `📦 Code (lang, N lines)`；超过 8 行或 400 字符的大段文本折叠为 `📄 Text (N lines) — 摘要…`。短小段落直接呈为 `Markdown`。
  - `ConfirmCard` 中 `file_write` 生成的 Diff 预览超过 6 行时包装为 `Collapsible` 折叠展示。
  - `Ctrl+O` 快捷键扩展为一键批量切换消息列表内所有折叠块（工具结果、代码、文字）。
- **最大轮数限制继续执行**：
  - `TUIReActAgent._run_loop` 循环中每当 `iteration % self.max_iterations == 0` 时，向 `approval_callback` 派发 `tool_name="max_iterations"` 审批；
  - `ConfirmCard` 识别该工具名并呈现：`⚠ 最大轮数限制：已执行 X 轮对话，是否允许继续执行？`，支持 `[y] 继续`、`[n] 停止`、`[a] 始终允许`。
  - 同意后追加轮数无缝继续；拒绝后抛出 `MaxIterationsExceeded` 结束并生成总结；已结束的任务可通过 `▶ Continue` 按钮或 `/continue` 指令继续唤醒。

### 6.17 TUI 全面扁平化无边框设计、Drop-down Menu 下拉选择器与底部状态栏 (`styles.py` / `screens/model_select.py` / `screens/chat.py`)

- **全面无边框与零衬距设计**：
  - `styles.py` 彻底移除 `border`、`border-top`、`border-bottom` 及 `border-left` 线条（统一为 `border: none;`），依托背景灰度色阶（`$surface-darken-1`、`$panel` 35%、`$panel` 65% 等）清晰分层。
  - 清理 `#input-area` 与 `#chat-input` 的 margin 与 padding，使输入框平铺满屏底；清除 `#messages` 与弹窗内部多余边距，消除组件与主窗口间的缝隙。
- **Textual `Select[str]` 下拉式模型选择器**：
  - `ModelSelectScreen` 废弃多列 `DataTable` 表格，改用轻量紧凑的 `Select[str]` 组件，弹出时直接聚焦。
  - 按 Enter 展开下拉选项，支持上下键导航与即打即搜（type-to-search），选取后触发 `Select.Changed` 自动生效并关闭；保留 `#model-input` 兼容手动输入任意模型标识。
- **底部状态栏流式布局**：
  - `StatusBar` 从顶层 dock 迁移至界面最底行，处于 `#input-area` 之下。
  - 弃用容易引发层叠计算冲突的 `dock: bottom`，采用垂直布局自然流式排列（`#messages` 1fr + `#input-area` auto + `StatusBar` 1），保证状态栏始终严丝合缝紧固在终端最后一行。
- **用户消息即时挂载渲染**：
  - `ChatScreen._mount_and_render_user_message` 在发送网络请求前立即完成用户消息的 DOM 挂载和贴底刷新，杜绝网络通信阶段的视窗迟滞。

### 6.18 Copilot CLI 风格极简 TUI、顶栏导航与提供商/Host 智能解析 (`nav_bar.py` / `model_select.py` / `session_select.py` / `status_bar.py` / `chat.py`)

- **TopTabBar 标签导航与键盘流**：
  - `TopTabBar` 封装 `Current`、`Sessions`、`Help` 标签，通过 `layout: horizontal` 配合 `width: auto` 消除弹性挤压。
  - `ChatInput` 监听按键：在输入框无文本时按 `Tab` 触发 `CycleTabRequested` 自动轮转标签；`F1`/`F2`/`F3` 或鼠标点击支持快速直达。
- **全屏模态选择器与 Rich 方括号转义**：
  - `ModelSelectScreen` 与 `SessionSelectScreen` 统一使用全屏无边框深色背景（`#0d1117`），选条高亮采用饱和蓝（`#1f6feb`）。
  - 模型与会话均支持即打即搜实时过滤，并在列表渲染中对 Rich Markup 的方括号进行转义（`\\[provider]`），杜绝因 Rich 样式标签误匹配导致提供商名称丢失的问题。
- **智能识别模型提供商与 Host 降级** (`agent2/app/chat.py`)：
  - 实现 `extract_host(url)` 提取带端口的 authority（如 `localhost:11434`、`api.deepseek.com`）。
  - 实现 `resolve_provider_or_host(provider, base_url)`：显式 provider 优先；若为通用占位符（如 `config.models` / `default`）则嗅探 URL 是否属于知名服务商；若仍未知则安全回退到 base_url host。
- **双状态栏协同**：
  - `ContextBar` 与 `StatusBar` 共同维护 `provider` 响应式属性，通过 `_sync_status_bar` 统一从底层 `OpenAILLM` 读取并刷新。
  - 封装统一的 `_set_busy` 管理机制，彻底消除发送 `?` 或 `help` 时引起的卡在 `processing...` 异常。

### 6.19 Context / Rules / Skills 发现与 SKILL.md 解析 (`context.py`)

- **分层发现策略**：
  - Rules：`~/.config/agent2/rules` → `~/.agent2/rules` → `<cwd>/.agent2/rules`，支持 `.md` / `.txt` 与 `config.json` 的 `rules` inline 列表。
  - Skills：按优先级从低到高扫描 `~/.config/agent2/skills`、`~/.claude/skills`、`~/.agent2/skills`、`.claude/skills`、`.agents/skills`、`.agent2/skills`，同名 Skill 由后扫描目录覆盖。
- **手写 frontmatter 解析器**：`parse_skill_markdown()` 不依赖 PyYAML，按行解析 `name` / `description`，支持 `>` / `>`- 折叠与 `|` / `|-` 字面量块；无 frontmatter 时从正文首个标题或首行回退。
- **按需注入与调用**：`Context.build_system_prompt()` 将规则包进 `<rules>`、技能包进 `<skills>`；`Context.get_skill()` 提供大小写不敏感查找；TUI/CLI 通过 `discover_skills()` 实现 `/skills` 与 `/<skill_name>` 动态调用。

### 6.20 MCP 工具桥接与生命周期管理 (`mcp.py`)

- **动态导入可选依赖**：`MCPManager.connect()` 内部 `from mcp import ClientSession, StdioServerParameters`，未安装时记录 warning 并返回空工具列表，核心功能不受影响。
- **手动管理 context manager**：为保持 stdio 连接长期存活，使用 `transport_ctx.__aenter__()` / `session_ctx.__aenter__()`，并把 `__aexit__` 存入 `_cleanup_fns`，`close()` 逆序调用，确保子进程与连接可靠释放。
- **Schema 与结果转换**：`_make_mcp_tool()` 把 MCP `inputSchema.properties` 转为 `ToolParameter`，用 `Tool.__new__` 构造异步 Tool；`_call()` 合并 MCP 返回的 content blocks 为字符串。
- **配置接入**：`AppConfig.mcp_servers` 在 `build_tui_agent()` / `_build_agent()` 启动时通过 `MCPServerConfig.model_validate()` 实例化，与内置工具合并注册。

### 6.21 多级审批作用域与持久化 (`app/approval.py` / `confirm_modal.py`)

- **作用域语义**：
  - `once` / `approve_once`：仅当前执行，不写入任何文件；
  - `conversation` / `approve_conversation`：加入内存 `_auto_approved`；
  - `project` / `approve_project`：加入内存并写入 `<project>/.agent2/approvals.json`；
  - `always` / `approve_always`：加入内存并写入 `~/.config/agent2/approvals.json`。
- **项目根定位**：`find_project_root()` 从 cwd 向上查找 `.agent2` / `.git` / `pyproject.toml`，避免审批文件污染用户主目录。
- **确认卡状态机**：按钮与快捷键 `1/y`、`2/c`、`3/p`、`4/a`、`n/Esc` 映射到五个决策；`submit_decision()` 统一渲染 `✓ Approved once` / `✓ Approved in project` / `✓ Always approved` / `✗ Rejected` 徽标。
- **Agent 侧短路**：`TUIReActAgent._execute_tool_calls()` 先查 `allow_all` / `yolo` / `SAFE_TOOLS` / `is_tool_approved()`，已授权工具不再弹窗。

### 6.22 YOLO / Allow-all 与最大迭代配置 (`app.py` / `config.py` / `base.py`)

- **YOLO system prompt 注入**：`set_yolo(True)` 在基础 system prompt 后追加 `YOLO_INSTRUCTION`，关闭时精确移除，避免重复追加。
- **自动审批短路**：`is_approved = allow_all or yolo or safe_tool or is_tool_approved(...)`；`allow_all` 只跳过审批，不改变 LLM 行为。
- **配置优先级**：`BaseAgent.__init__` 依次判断显式 `max_iterations`、`AGENT2_AGENT_MAX_ITERATIONS` 环境变量、`config.json.max_iterations`，最后回退默认值 50。
- **旧字段迁移**：`AppConfig` 的 `model_validator(mode="before")` 把 `max_turns` / `max_rounds` 自动映射为 `max_iterations`，保持向后兼容。

### 6.23 Token 用量持久化、实时刷新与 Plan 子任务聚合 (`session.py` / `app.py` / `screens/chat.py`)

- **保存与恢复**：`SessionManager.save()` 写入顶层 `usage`，并支持从 `agent_data["extra"]["usage"]` 回退；`restore_agent()` 优先读取已保存 usage，旧会话无数据时 `_estimate_session_usage()` 按消息内容估算。
- **防止跨会话泄漏**：恢复时无论当前 LLM 计数器为何值都强制覆盖；空会话恢复为 `Usage()`。
- **模型切换保留**：`switch_model()` 保存旧 `total_usage` / `last_usage`，创建新 LLM 后回填。
- **Plan 子任务聚合**：每个 subtask 使用独立 sub-agent；`try/finally` 包裹 `subagent.run()`，即使子任务异常或取消，也把 `subagent.llm.total_usage` 累加到父会话并刷新状态栏。
- **实时同步**：`on_thought_received()`、`on_tool_call_completed()` 立即调用 `_sync_status_bar()`；`_run_agent()` / `_run_plan_generation()` / `_run_plan_execution()` 的 `finally` 兜底。
- **ToolCard 标题与折叠**：`ToolTitle` 运行中显示 `⏳` 并拦截点击/折叠，完成后通过 `_get_result_title()` 生成 `Result: <命令首行 / 路径 / query>` 摘要；错误时额外挂载 `❌ Error` 状态行。


---

### 6.24 内联快捷键面板、Tab 即时切面板与两段式删除 (`shortcut_help.py` / `input_area.py` / `nav_bar.py` / `status_bar.py` / `session_select.py`)

- **内联快捷键面板**：`ShortcutHelp(Static)` 默认 `display: none`，通过 `.visible` 类切换；`toggle_help()` 返回当前可见状态供调用方联动收起补全。
- **空输入即时快捷键**：`ChatInput.on_key` 在 `not show_completion and not text.strip()` 时拦截 `?` / `？` / `+` / `＋`，分别 post `ShortcutsRequested` / `SessionsRequested`；`MessageList` / `TopTabBar.TabItem` 的 type-to-focus 分支做同样判断并直接调用 `screen` 的 action，避免字符先入输入框。
- **Tab 专用于切面板**：`ChatInput` 的 `tab` 一律 post `CycleTabRequested`（不再用于补全接受）；补全导航仅保留 `↑` / `↓` / `Esc`。`TabItem` 拦截 `tab` / `shift+tab` 调用 `TopTabBar.cycle_tab(±1)`。
- **动态底部提示**：`StatusBar.active_tab` 响应式属性；`render()` 依据 `sessions` / `skills` / 其它分支渲染不同的按键提示行。
- **两段式删除**：`SessionSearchInput` 将 `ctrl+x` 映射为 `DeleteArmRequested`，armed 态下 `x` / `X` / `shift+x` 映射为 `DeleteRequested`；`SessionSelectScreen._delete_armed` 控制 armed 状态并实时更新 `#session-hint` 文案。
- **Rich Markup 转义**：`session.py` 预览与 `tool_card.py` 标题统一使用 `rich.markup.escape`，防止用户内容中的方括号破坏样式解析。

---

## 7. 异步设计

- **全链路 async/await**：从 `agent.chat()` → `_run_loop()` → `llm.chat()` → `tool.execute()` 全部异步。
- 同步工具函数通过 `asyncio.to_thread()` 桥接，不阻塞事件循环。
- CLI 入口用 `asyncio.run()` 驱动，保持单一事件循环。
- `BaseLLM.chat_stream()` 默认实现退化为非流式（yield 完整响应），子类可覆盖实现真正的流式。

---

## 8. 错误处理策略

| 场景 | 策略 |
|------|------|
| 工具执行异常 | 捕获并转为错误文本返回给 LLM，保证 tool 消息完整闭环 |
| 历史会话缺失 tool 消息 | `_repair_tool_messages()` 自动补齐合成错误结果，防止 API 400 |
| Agent 超过最大迭代 | 抛出 `MaxIterationsExceeded`，`chat()` 捕获后返回友好提示；`max_iterations < 1` 在入口处校验 |
| LLM 返回非法 JSON（计划/反思） | `extract_json()` 容忍 Markdown 代码块包裹；反思解析失败时返回 `passed=False` 并记录警告日志（不再静默假设通过） |
| Ask 模式尝试调用写/执行工具 | 两道防线：`_run_loop()` 过滤 Schema + `_execute_tool_calls()` 强行拦截并返回错误工具响应 |
| Plan 模式任务依赖存在环路 | Kahn 算法检测到环路或不可达时安全降级为原任务顺序，避免死锁或崩溃 |
| 配置文件不存在或格式错误 | 静默返回默认配置；`load_models()` 中 `create_llm` 失败时记录警告并跳过 |
| openai 包未安装 | 延迟到首次使用时才 `ImportError`，附带安装提示 |
| 记忆持久化文件损坏 | 静默忽略，使用空记忆启动 |
| Shell 命令超时 | 使用 `os.killpg` 清理整个进程组，防止子进程残留 |
| 工具动态加载失败 | 仅捕获 `ImportError` / `AttributeError`，附带警告日志（不再 `except Exception: pass`） |

**设计思想：Agent 系统应尽量自愈，避免因单点故障中断整个推理流程。**


