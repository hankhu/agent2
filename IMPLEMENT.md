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

- 只映射 JSON Schema 的基础类型，泛型容器（`list[X]`、`dict[X, Y]`）通过 `__origin__` 判断。
- 不支持的类型统一降级为 `"string"`，保证不崩溃。

### 2.2 同步函数异步化

```python
if self._is_async:
    result = await self.func(**kwargs)
else:
    result = await asyncio.to_thread(self.func, **kwargs)
```

- 同步工具函数被包装到 `asyncio.to_thread()` 中执行，不阻塞事件循环。
- 构造时通过 `asyncio.iscoroutinefunction()` 判断，运行时零开销分发。

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
    plan = json.loads(content.strip())
except json.JSONDecodeError:
    return [line.strip() for line in content.strip().split("\n") if line.strip()]
```

- 先尝试 JSON 解析；处理 markdown 代码块包裹的情况；最终 fallback 到按行切分。
- 确保即使 LLM 输出格式不完美，也能提取出计划步骤。

### 3.5 ReflectionMixin 的 super() 链

```python
class ReflectionMixin:
    async def chat(self, msg):
        result = await super().chat(msg)  # 调用被混入类的 chat()
        ...
```

- 利用 Python MRO（Method Resolution Order），`super().chat()` 沿着 MRO 链调用实际 Agent 类的 `chat()`。
- `ReflectionMixin` 必须在继承顺序中排在 Agent 类之前：`class X(ReflectionMixin, ReActAgent)`。

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
- 每次 `add()` 后重建 IDF（`_rebuild_idf`），保证 IDF 值基于全量文档。
- 向量长度不固定，`_cosine_similarity` 中用零填充对齐。

### 4.3 余弦相似度的零填充

```python
max_len = max(len(a), len(b))
a = a + [0.0] * (max_len - len(a))
b = b + [0.0] * (max_len - len(b))
```

- 因为词表会随新文档增长，历史文档的嵌入向量可能短于查询向量。
- 用零填充而非重新嵌入——牺牲少量精度换取性能（不需要每次 add 都重新嵌入所有文档）。

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
| Agent 超过最大迭代 | 抛出 `MaxIterationsExceeded`，`chat()` 捕获后返回友好提示 |
| LLM 返回非法 JSON（计划/反思） | fallback 解析（按行切分 / 假设通过） |
| 配置文件不存在或格式错误 | 静默返回默认配置 |
| openai 包未安装 | 延迟到首次使用时才 `ImportError`，附带安装提示 |
| 记忆持久化文件损坏 | 静默忽略，使用空记忆启动 |

**设计思想：Agent 系统应尽量自愈，避免因单点故障中断整个推理流程。**

