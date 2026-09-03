# Agent2 开发备忘（memo_dsh）

> 本文档汇总当前分支/工作区中已完成的 TUI、CLI、LLM 层与 Session 相关改动。

## 1. TUI 基础交互

- **命令补全**
  - 输入 `/` 时弹出斜杠命令补全列表。
  - 支持 `↑/↓` 选择、`Tab` 接受、`Esc` 关闭。
  - 补全列表默认隐藏，输入 `/` 后显示。
  - 包含 `/model`、`/models`、`/clear`、`/new`、`/resume`、`/help`、`/h`、`/exit`、`/quit`。

- **Ctrl-D 退出**
  - `ChatScreen` 绑定 `Ctrl+D` 退出。
  - `ChatInput` 内也做了兜底处理，焦点在输入框时仍可退出。
  - 退出前尝试保存会话；保存失败不会阻塞退出。

- **聊天输入框历史**
  - `↑` 回溯上一条用户消息。
  - `↓` 向下回到较新消息，最后恢复进入历史前的草稿。
  - `/` 开头的命令不进入历史。
  - 命令补全弹出时，`↑/↓` 优先用于补全选择。

## 2. CLI 参数

- `agent2.app.tui` 新增：
  - `-p MSG`：单轮模式，发送消息、执行并退出。
  - `-i MSG`：交互模式，并把 MSG 作为首条用户消息自动发送。
- `agent2.app.chat` 已具备相同语义的 `-p` / `-i`。

## 3. 模型选择与记忆

- **记住上次选择的模型**
  - 新增 `~/.config/agent2/last_model`。
  - TUI/CLI 启动时若未显式传 `--model`，会恢复上次使用的模型。
  - 通过 `/model` 切换、`--model` 指定、恢复会话时会更新记录。

- **模型列表过滤**
  - 隐藏没有 API Key 的远端模型。
  - 本地/局域网模型始终显示：`localhost`、`127.x`、`10.x`、`192.168.x`、`172.16-31.x`、`169.254.x`、`*.local` 等。
  - 存在全局 API Key（配置或环境变量）时，远端模型也可显示。

- **模型选择界面简化**
  - 显示列简化为：`# | Provider | Model`。
  - Provider 从 `base_url` 域名主体提取，例如 `deepseek`、`nvidia`、`siliconflow`、`localhost`。
  - 增加 Filter 输入框，输入时实时过滤。
  - 支持按 Provider、Model ID、别名、来源过滤。
  - 打开弹窗时焦点自动在输入框。

- **小米 Mimo 模型找不到问题**
  - 根因：传入 `小米Mimo-v2.5` 等友好名称时，旧逻辑无法匹配配置中的 `mimo-v2.5`，会 fallback 到默认 endpoint 导致 “model not found”。
  - 已支持大小写不敏感、子串/反向匹配，自动解析到配置中的 `mimo-v2.5` 并使用 Xiaomi endpoint。

## 4. 工具调用与历史修复

- **`tool_calls` 400 错误修复**
  - 错误信息：`An assistant message with 'tool_calls' must be followed by tool messages...`
  - 原因：历史中缺少部分 `tool_call_id` 对应的 tool 响应。
  - 修复：
    - `BaseAgent._execute_tool_calls` 和 `TUIReActAgent._execute_tool_calls` 在工具执行异常时也会生成错误 tool 消息。
    - `BaseAgent` 新增 `_repair_tool_messages()`，在 `chat()` 前和 session 恢复时自动补全缺失 tool 消息。
    - `OpenAILLM.chat` / `chat_stream` 在发送前也做同样的完整性修复，作为 API 边界兜底。

## 5. Session 功能

- **Session 列表选择**
  - 新增 `SessionSelectScreen` 模态框。
  - `/resume` 无参数时弹出会话列表。
  - 支持 `↑/↓` 方向键选择，`Enter` 恢复，`Esc` 取消。
  - 列表显示：标题、ID、保存时间。

- **可读标题生成**
  - 改进 `_extract_title()`。
  - 从首条用户消息生成标题。
  - 自动移除 `<file>` / `<directory>` 注入内容、`#file` / `#dir` 指令。
  - 压缩空白/换行，超长截断为 60 字符左右。

## 6. 安全与仓库卫生

- 扫描了仓库内文件与 Git 历史，未发现硬编码密钥。
- 本地 `~/.config/agent2/agent2_config.json` 含大量明文 API Key，需注意不要提交/分享。
- `.gitignore` 已补充：
  - `config.json`
  - `agent2_config.json`
  - `cherrystudio_llm_config.json`
  - `.env` / `.env.*`
  - `*.pem` / `*.key` / `*.p12` / `*.pfx`

## 7. 主要涉及文件

- `src/agent2/app/tui/__init__.py`
- `src/agent2/app/tui/app.py`
- `src/agent2/app/tui/styles.py`
- `src/agent2/app/tui/session.py`
- `src/agent2/app/tui/screens/chat.py`
- `src/agent2/app/tui/screens/model_select.py`
- `src/agent2/app/tui/screens/session_select.py`
- `src/agent2/app/tui/widgets/input_area.py`
- `src/agent2/app/chat.py`
- `src/agent2/app/config.py`
- `src/agent2/agent/base.py`
- `src/agent2/llm/openai.py`
- `.gitignore`

## 8. 发送反馈与状态栏修复（本轮）

- **发送消息的即时反馈链路**：`ChatScreen.on_chat_input_submitted` 先 `add_user_message(text)` 回显、再启动 worker；`_run_agent` 内先置 `status.busy = True` + `"Processing…"`，响应返回（或失败/中断）后由 `finally` 清除。`#file`/`#dir` 上下文展开移入 worker（`asyncio.to_thread`），不再阻塞回显。
- **修复 `Usage + Usage` TypeError**（关键 bug）：pydantic `BaseModel` 不支持 `+`，`BaseLLM._record_usage` 的 `total_usage + usage` 每次请求都抛异常，导致回复丢失、状态栏 token 恒为 0。已在 `Usage` 上实现 `__add__`（字段累加）。
- **`chat_stream` 补记 usage**：流式响应的末块若携带 `chunk.usage` 则写入 `last_usage`/`total_usage`。
- **状态栏增强**（`widgets/status_bar.py`）：
  - 输入/输出 token 增加相对上下文窗口的百分比：`↑1.2k (1%) ↓345 (0%)`。
  - 新增 `reset_timer()`：`/new`、`/resume` 时重启“当前对话持续时间”计时。
  - 移除废弃的 `token_count` reactive。
- **`/new`、`/resume` 重置用量**：新增 `ChatScreen._reset_usage()`（清空 `llm.total_usage`/`last_usage` 与状态栏 token 读数），修复 `/new` 调用不存在方法的 `AttributeError`。

## 9. 状态栏不可见与补全回车修复（本轮）

- **状态栏文字从未上屏（模型不可见根因）**：`styles.py` 中 `StatusBar { height: 1 }` 同时声明了 `border-bottom`，Textual 里边框占用内容高度，内容区高度为 0，`render()` 的结果从未绘制。改为 `height: 2`（内容行 + 边框行）后状态栏正常显示 `Model: <model>` 等全部内容。
- **斜杠补全回车无效**：`ChatInput._on_key` 在补全列表可见时只转发 `tab/up/down/escape`，Enter 落入"提交消息"分支，高亮命令不会进输入栏。
  - 现在：补全列表打开时，**先按 ↑/↓ 选择过**再按 Enter → 接受高亮命令进输入栏（与 Tab 一致，一次性）；未选择直接回车 → 照常提交（完整命令如 `/help` 无需按两次回车）。
  - 实现：`ChatInput` 增加 `_completion_navigated` 闩锁（`watch_show_completion` 关闭列表时复位），`chat.py` 的 `on_chat_input_completion_key` 将 `enter` 与 `tab` 同样路由到 `_accept_completion()`。

## 10. 空会话不再保存（本轮）

- 新增 `ChatScreen._session_has_input()`（agent 历史中是否存在 user 消息）与 `_save_session()`（无输入则跳过保存）。
- 所有保存入口统一走守卫：`_run_agent` 自动保存、`/new` 切换前保存、`/rename`、`/exit`、`Ctrl+D` 退出。打开应用从不发送消息就退出 / 立即 `/new`，不再产生只有 system prompt 的空会话记录；`/rename` 空会话会提示"当前会话还没有内容，暂不保存"。
- 恢复的会话（含 user 消息）与失败/中断回合照常保存。

## 11. Rewind & Fork — 消息级回退/分叉交互 (v0.1.3.9)

- **BaseAgent 新增 `rewind()` / `rewind_to()` 方法**（`agent/base.py`）
  - `rewind(turns)`：按轮次回退对话历史，一轮从 user message 开始包含后续 assistant/tool messages。
  - `rewind_to(index, inclusive)`：回退到指定消息索引，`inclusive=True` 保留该消息，`False` 移除该消息及之后所有消息。
  - 两个方法均返回被移除的消息列表。

- **`TUIReActAgent.fork()` 覆写**（`app/tui/app.py`）
  - 覆写 `fork()` 确保克隆 agent 时复制 `_auto_approved`、`approval_callback`、`mode` 等 TUI 特有状态。

- **`/rewind` 命令**（`screens/chat.py`）
  - 回退最近一轮对话（最后一个 user message 及其后续 assistant 回复），将被回退的用户输入填入输入框。
  - 执行前检查 agent 是否繁忙，繁忙时提示等待。

- **`/fork [title]` 命令**（`screens/chat.py`）
  - 克隆当前完整会话为新 session（生成新 session ID），后续对话在新 session 中继续。
  - 支持可选参数指定 fork 后的会话标题。

- **消息级 Point Rewind / Fork 交互**（`screens/chat.py` + `widgets/message_list.py` + `styles.py`）
  - `SelectableMessage` 基类：消息支持点击/焦点选中，选中后高亮并显示 `⏪ Rewind` 和 `🍴 Fork` 操作按钮。
  - 在 `UserMessage` 上 Rewind：回退到该消息之前，将该消息内容填入输入框。
  - 在 `AssistantMessage` 上 Rewind：回退到该回复（保留该回复），后续对话从此处继续。
  - 在 `UserMessage` 上 Fork：创建新 session，保留该消息之前的历史，将该消息填入输入框。
  - 在 `AssistantMessage` 上 Fork：创建新 session，保留到该回复为止的完整历史。
  - `RewindRequested` / `ForkRequested` 自定义 Textual Message 事件。
  - Escape 键取消选择并返回焦点到输入框。

- **选中态 UI 样式**（`styles.py`）
  - `UserMessage` / `AssistantMessage` 选中态：高亮背景 + 左侧双线指示条。
  - `.message-actions` 按钮栏：默认隐藏，选中或聚焦时显示。
  - 按钮样式：扁平透明底色，hover/focus 时高亮。

- **测试覆盖**（`tests/test_rewind_fork.py`）
  - 新增 9 个测试：`BaseAgent` rewind/rewind_to 单元测试 + TUI 级 point rewind/fork 集成测试。

- **主要涉及文件**：
  - `src/agent2/agent/base.py`
  - `src/agent2/app/tui/app.py`
  - `src/agent2/app/tui/screens/chat.py`
  - `src/agent2/app/tui/styles.py`
  - `src/agent2/app/tui/widgets/message_list.py`
  - `tests/test_rewind_fork.py`

## 12. /retry 指令与按钮、平滑贴底滚动、代码/大段文字折叠与最大轮数继续 (v0.1.3.10)

- **支持 `/retry` 指令与重试按钮**：
  - `SLASH_COMMANDS` 注册 `/retry`；支持直接输入 `/retry` 重发最后一轮用户消息并重新生成助手回答。
  - `UserMessage` 与 `AssistantMessage` 的操作按钮栏增加 `🔄 Retry` 按钮。
  - 触发 `RetryRequested` 事件，支持精准从指定用户提问或指定助手回复对应的提问开始重试并自动重新执行。

- **平滑贴底自动滚动 (Sticky Scroll)**：
  - `MessageList` 挂载时启用 `anchor(True)`。
  - 用户未主动向上滚动或滚动条已在最底时，收到新消息（User、Assistant、System、Thinking、ToolCard、ConfirmCard 及工具执行完毕）均自动平滑滚动至最底。
  - 用户向上翻看历史时，不强制劫持视窗；当用户滚动回底部后，自动恢复随新消息下滚。
  - 用户主动提交消息时自动贴底并重置贴底锚点。

- **代码块与大段文字折叠 (Collapsible Folding)**：
  - `AssistantMessage` 自动解析 Markdown 段落：
    - 代码块（` ``` ` 超过 4 行）自动折叠为 `📦 Code (lang, N lines)` 面板，默认折叠。
    - 大段文字段落（超过 8 行或 400 字符）自动折叠为 `📄 Text (N lines) — 摘要…`，默认折叠。
    - 短小段落直接呈现为 Markdown，保持紧凑整洁。
  - `ConfirmCard` 中 `file_write` 生成的 Diff 预览超过 6 行时自动折叠为 `📝 Diff (N lines)`。
  - 快捷键 `Ctrl+O` 支持一键展开/折叠消息流中所有折叠块（工具结果、代码块、文字段落）。

- **多轮消息达到最大轮数时允许继续**：
  - `TUIReActAgent._run_loop` 在达到 `max_iterations` 限制且未完成时，通过 HITL 弹窗向用户请求审批（`tool_name="max_iterations"`），选项：`[y] 继续 (Continue) / [n] 停止 (Stop) / [a] 始终允许 (Always)`。
  - 用户同意后追加轮数无缝继续执行。
  - 支持 `/continue` 指令手动继续；助手消息遇到达到上限提示时自动展示 `▶ Continue` 按钮，一键继续执行。

- **测试覆盖**（`tests/test_retry_scroll_limit.py`）：
  - 9 个完整单元与集成测试全部通过，覆盖指令、按钮事件、滚动逻辑、折叠逻辑与轮数限制继续执行。

## 13. 全面扁平化去边框、模型选择 Drop-down Menu、底部状态栏与零衬距贴合布局 (v0.1.3.11)

- **全面去除边框与极简扁平化设计**（`styles.py`）：
  - 移除 `StatusBar`、`#input-area`、`#chat-input`、`#completion-list` 以及所有弹窗模态（`#model-dialog`、`#session-dialog`）的显式实线边框（`border: none`）。
  - 移除 `UserMessage`、`AssistantMessage`、`ThinkingBlock`、`ToolCard`、`DiffView`、`ConfirmCard` 等元素的左侧线条指示条，完全依托纯净的背景深浅明暗色块区分层级与选中状态。
  - 输入框获得焦点时由实线边框改为背景色微亮高亮（`background: $panel 60%`），与现代平铺无边框设计统一。

- **选择列表改为 Drop-down Menu 组件**（`model_select.py`）：
  - 将原本占用大量画面的 `DataTable` 表格选择列表替换为 Textual 原生下拉选择框组件 [`Select[str]`](file:///Volumes/code/repos/agent2/src/agent2/app/tui/screens/model_select.py)。
  - 弹窗打开后默认聚焦在下拉框，按 `Enter` 展开下拉选项列表，内置即打即搜（type-to-search）与键盘上下方向键导航。
  - 支持回车即刻选中并切换模型；同时保留下方自定义模型输入框，兼容任意自定义模型 ID 或别名输入。

- **状态栏移至视窗最下方**（`styles.py`, `chat.py`, `status_bar.py`）：
  - 改变顶栏悬浮的传统布局，将 `StatusBar` 移至界面最底端（24 行高度下位于 `y=23, height=1`），处于输入框正下方。
  - 移除原 `dock: top` 设定，采用自然的竖向流式贴底布局（`#messages` 1fr + `#input-area` auto + `StatusBar` 1），杜绝 dock 层叠冲突。

- **输入框、对话框与主窗口零衬距全贴合**（`styles.py`, `model_select.py`, `session_select.py`）：
  - 消除 `#chat-input` 的左右外边距（`margin: 0`）与 `#input-area` 的底部衬距（`padding: 0`），使输入框完整横向纵向平铺贴满视窗边缘。
  - 消除 `#messages` 的内衬距（`padding: 0; margin: 0`），消息流内容紧凑贴合两侧与底栏。
  - 移除弹窗模态内多余的行尾换行符及内衬距，使界面更加平整一体化。

- **用户消息即时挂载渲染**（`chat.py`, `widgets/message_list.py`）：
  - 用户按下回车后立即完成 DOM 挂载并强制刷新合成器渲染，贴底展示后再触发网络请求，彻底消除网络请求初期的延迟感。

- **测试覆盖**（`tests/test_model_select_flat.py`, `tests/test_retry_scroll_limit.py`）：
  - 新增测试覆盖无边框 CSS 有效性、`Select` 下拉菜单展开与选取、自定义模型输入、取消操作及状态栏底部定位校验。全量 91 项测试全部通过。

