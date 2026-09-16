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

## 14. Copilot CLI 风格极简 TUI、顶栏导航、全屏视窗与模型提供商/Host 智能识别 (v0.1.3.12)

- **Copilot CLI 风格极简现代布局**：
  - **顶部导航栏 (`TopTabBar`)**：水平并排渲染 `Current`、`Sessions`、`Help` 紧凑标签。`Current` 采用深蓝色胶囊样式高亮；支持鼠标点击、快捷键直达（`F1`/`F2`/`F3`），以及在输入框为空时按 `Tab` 键循环切换标签。
  - **欢迎横幅 (`WelcomeBanner`)**：空会话状态下展示居中的 ASCII Mascot 图标、版本与免责声明，以及随机轮播的 Tip 指引卡片（如 `/plan`、`/ask`、`#file` 上下文注入等），并在 `/clear` 清屏后优雅恢复。
  - **独立帮助浮层 (`HelpScreen`)**：集中呈现 Agent/Plan/Ask 三大运行模式说明、常用按键绑定、斜杠命令清单及 `#file`/`#dir` 语法，支持 `?` 或 `/help` 快捷调出。

- **全屏极简视窗交互重构**：
  - **会话管理视窗 (`SessionSelectScreen`)**：采用全屏极简风格并保持顶栏联动；展示 `• Tip: /sessions` 引导文案；支持实时关键词过滤、全宽亮蓝高光选框（`#1f6feb`）、`↑`/`↓` 快速导航、`e` 重命名、`d` 删除会话、`Enter` 恢复会话。
  - **模型选择视窗 (`ModelSelectScreen`)**：保留顶栏联动与 `• Tip: /model` 指引；提供模型分组与全宽亮蓝选条高光；底部搜索框边输边搜，按 `Enter` 选定或直接提交自定义模型 identifier。

- **模型提供商 (Provider) 与 Host 智能识别**：
  - 在 `src/agent2/app/chat.py` 中引入 `extract_host` 与 `resolve_provider_or_host`：
    - 若显式配置或识别出已知提供商（如 `deepseek`、`openai`、`ollama`、`anthropic`、`siliconflow` 等），直接采用提供商名称。
    - 若无法确定提供商（如内网私有网关或局域网 IP），自动提取并选用 `base_url` 的 host（如 `api.deepseek.com`、`localhost:11434`、`192.168.1.100:8000`）。
    - 过滤掉 `config.models` / `config.default` / `default` 等通用占位符。
  - 模型选择列表项清晰展示 `[provider] model_id` 或 `[host] model_id`。
  - 转义 Rich Markup 中方括号（`\[provider]`），防止方括号文字被 Rich 误当做样式标签解析丢失。

- **双层状态栏拆分与联动 (`ContextBar` + `StatusBar`)**：
  - **`ContextBar`**（紧贴输入框上方）：左侧展示当前工作目录与执行 Spinner/耗时；右侧展示会话 Token 统计、上下文窗口占比与当前模型标签 `[provider] model_name`（或 `[host] model_name`）。
  - **`StatusBar`**（终端底行）：左侧呈现全局导航提示，右侧呈现 `[AGENT]` / `[PLAN]` / `[ASK]` 模式徽标。
  - `ChatScreen._sync_status_bar` 自动同步底层 LLM 的模型名称、提供商与 Token 用量至两个栏目。

- **交互体验修复与增强**：
  - 修复命令补全菜单：弹出 `/` 命令补全列表时，按 `Enter` 键直接等同于 `Tab` 键完成补全填充。
  - 统一 `_set_busy` 管理机制，修复输入 `?` 或 `help` 导致终端卡在 `processing...` 的状态同步问题。

- **测试套件扩展**（`tests/test_tui_layout.py`）：
  - 涵盖组件挂载、标签循环切换、Rich 渲染、提供商与 host 解析、方括号转义及状态栏同步。
  - 全量 104 项单元测试全部通过。



## 15. Context/Skills、MCP、审批作用域、YOLO/Allow-all、配置化迭代与 Token 用量持久化 (v0.1.3.13)

- **Context 与 Skills 加载体系**（`src/agent2/context.py`）：
  - `SkillInfo` / `Context` 数据类；`Context.build_system_prompt()` 将 `<rules>` 与 `<skills>` 注入 system prompt。
  - Rules 搜索路径：`~/.config/agent2/rules`、`~/.agent2/rules`、`<cwd>/.agent2/rules`，支持 `.md` / `.txt` 与 `config.json` 中的 inline rules。
  - Skills 搜索路径按优先级从低到高：`~/.config/agent2/skills`、`~/.claude/skills`、`~/.agent2/skills`、`.claude/skills`、`.agents/skills`、`.agent2/skills`；后扫描目录覆盖同名技能。
  - `parse_skill_markdown()` 解析 `SKILL.md` YAML frontmatter，支持 `name` / `description`、`>` / `|` 折叠与多行值；无 frontmatter 时从正文标题或首行回退。
  - TUI 新增 `SkillSelectScreen`（`screens/skill_select.py`）：实时过滤、上下导航、`r` 重载、`Enter` 调用；`TopTabBar` 新增 `Skills` 标签（`F3`）。
  - `ChatScreen` 的 `/skills`、`/skills reload`、动态 `/<skill_name> [prompt]` 均接入 `Context.get_skill()` 与 `discover_skills()`；斜杠命令补全列表自动包含技能名。

- **MCP (Model Context Protocol) 客户端**（`src/agent2/mcp.py`）：
  - `MCPServerConfig` 支持 stdio `command` / `args` / `env` 与 SSE `url` 配置。
  - `MCPManager.connect()` 动态导入可选依赖 `mcp`，通过 `stdio_client` + `ClientSession` 建立长连接，调用 `session.list_tools()` 发现工具。
  - `_make_mcp_tool()` 将 MCP `inputSchema` 转换为 agent2 `ToolSchema`，并用 `Tool.__new__` 构造带异步 `call_fn` 的 Tool；MCP 返回的 content blocks 合并为字符串结果。
  - `MCPManager.close()` 逆序执行 context manager 清理；`build_tui_agent()` 与 `_build_agent()` 在启动时读取 `config.mcp_servers` 并合并 MCP tools。
  - `pyproject.toml` 增加 optional dependency `mcp = ["mcp>=1.0"]`。

- **多级工具审批作用域**（`src/agent2/app/approval.py` + `widgets/confirm_modal.py`）：
  - 审批作用域：`once` / `conversation` / `project` / `always`；分别对应不持久化、当前会话内存、项目级 `.agent2/approvals.json`、全局 `~/.config/agent2/approvals.json`。
  - `is_tool_approved()` 依次检查 conversation set、project 文件、global 文件；`record_approval()` 负责持久化。
  - `find_project_root()` 以 `.agent2` / `.git` / `pyproject.toml` 向上查找项目根目录。
  - ConfirmCard 按钮改为 `[1/y] Approve once`、`[c] In conversation`、`[p] In project`、`[a] Always approve`、`[n] Reject`；`max_iterations` 审批仍保持单次/始终两档语义。

- **YOLO / Allow-all 自动审批**（`app.py` + `screens/chat.py` + `app/chat.py`）：
  - `TUIReActAgent.set_yolo()` 将 `YOLO_INSTRUCTION` 追加到 system prompt；`set_allow_all()` 仅设置自动审批标志。
  - 工具审批判断改为 `allow_all or yolo or safe_tool or is_tool_approved(...)`；`_auto_approved` 与 project/global 审批文件统一走 `record_approval()`。
  - `/yolo on|off|show`、`/allow-all on|off|show` 同时支持 TUI 与 Chat CLI；状态栏 `StatusBar` 与 `ContextBar` 渲染 `YOLO` / `ALLOW-ALL` 徽标。
  - `_get_extra_state()` / `_restore_extra_state()` 持久化 `yolo`、`allow_all`、`mode`、`auto_approved` 与 `llm.total_usage`。

- **最大迭代次数配置化**（`utils/config.py` + `app/config.py` + `agent/base.py` + `app/tui/app.py`）：
  - `Settings.agent_max_iterations` 默认值 10 → 50；`AppConfig.max_iterations` 默认 50，并支持 `max_turns` / `max_rounds` 别名迁移。
  - `BaseAgent.__init__` 优先级：显式参数 > `AGENT2_AGENT_MAX_ITERATIONS` 环境变量 > `config.json.max_iterations` > 默认值。
  - `build_tui_agent(max_iterations=...)` 透传到 `TUIReActAgent`，Plan 子任务可通过配置继承。
  - `BaseAgent.from_dict()` 恢复内置工具时增加 `seen_names` 去重。

- **Session 预览与 Token 用量持久化**（`session.py` + `app.py` + `screens/chat.py` + `widgets/tool_card.py`）：
  - `SessionManager.get_session_preview()` 返回富文本转录预览；`list_sessions()` 增加 `message_count` / `preview`；`SessionSelectScreen` 增加右侧预览列，并支持按预览内容过滤。
  - `SessionManager.save()` 增加顶层 `usage` 字段，支持从 `agent_data["extra"]["usage"]` 自动提取与旧文件回退。
  - `restore_agent()` 恢复 `usage`；旧会话无 usage 时 `_estimate_session_usage()` 按消息内容估算，并强制覆盖 live 计数器，避免跨会话泄漏。
  - `Agent2App.switch_model()` 保留 `total_usage` / `last_usage`；`_run_plan_execution()` 在子任务 `finally` 中把 `subagent.llm.total_usage` 聚合到父会话（失败/取消也计入）。
  - `_run_agent()` / `_run_plan_generation()` / `_run_plan_execution()` 的 `finally` 统一调用 `_sync_status_bar()`；`on_thought_received()` / `on_tool_call_completed()` 实时刷新。
  - `ToolCard` 新增 `ToolTitle` / `ToolCollapsible`：运行中显示 `⏳` 且禁止折叠，完成后标题显示操作摘要（命令首行 / 文件路径 / query），错误额外显示 `❌ Error`。

- **测试覆盖**：
  - 新增 `tests/test_context.py`、`test_skills_ui.py`、`test_mcp.py`、`test_approval_scopes.py`、`test_yolo_allow_all.py`、`test_max_iterations_config.py`、`test_session_preview.py`、`test_tool_result_title.py`、`test_token_usage.py`。
  - 全量测试从 104 项扩展至 166 项，全部通过。

- **主要涉及文件**：
  - `src/agent2/context.py`、`src/agent2/mcp.py`、`src/agent2/app/approval.py`
  - `src/agent2/app/config.py`、`src/agent2/utils/config.py`、`src/agent2/agent/base.py`
  - `src/agent2/app/tui/app.py`、`src/agent2/app/tui/screens/chat.py`、`src/agent2/app/tui/session.py`
  - `src/agent2/app/tui/screens/skill_select.py`、`session_select.py`、`widgets/confirm_modal.py`、`tool_card.py`
  - `tests/test_context.py` 等新增测试文件


## 16. 内联快捷键面板、Tab 即时切面板与两段式会话删除 (v0.1.3.14)

- **内联快捷键面板**（`src/agent2/app/tui/widgets/shortcut_help.py`）：
  - 新增 `ShortcutHelp(Static)`：`display: none` + `.visible` 类切换，`max-height: 14` 可滚动，常驻于 `#input-area` 中、`ChatInput` 之上。
  - `SHORTCUT_HELP_TEXT` 分为 `Keyboard shortcuts` / `Sessions panel` / `Skills panel` 三段，纯文本 + Rich Markup 上色。
  - `show_help()` / `hide_help()` / `toggle_help()` 返回当前可见状态；`ChatScreen.action_toggle_shortcuts()` 负责切换并在展开时收起斜杠补全。

- **`?` / `+` 即时快捷键（无需回车）**：
  - `ChatInput.on_key` 在空输入框且非补全态下拦截 `question_mark` / `?` / `？` 与 `plus` / `+` / `＋`，分别 post `ShortcutsRequested` / `SessionsRequested` 消息。
  - `MessageList` 与 `TopTabBar.TabItem` 的 type-to-focus 分支同样在空输入时识别 `?` / `+`，直接调用 `screen.action_toggle_shortcuts()` / `action_tab_sessions()`，避免先把字符插入输入框再提交。
  - 保留 `on_chat_input_submitted` 对 `?` / `help` / `+` 的兼容处理。

- **顶栏精简与 Tab 即时切面板**：
  - `TopTabBar.TABS` 由 `current` / `sessions` / `skills` / `help` 精简为前三档，移除 `F4` 与 `action_tab_help` / `_open_help_dialog`，各模态视窗同步删除 `HelpScreen` 跳转分支。
  - `ChatInput` 将 `Tab` 完全让渡给切面板（`CycleTabRequested`），补全导航只保留 `↑` / `↓` / `Esc`；`TabItem` 监听 `tab` / `shift+tab` 调用 `TopTabBar.cycle_tab(±1)`。
  - `TopTabBar.cycle_tab(direction)` 支持双向循环；`StatusBar` 新增 `active_tab` 响应式属性，按 `sessions` / `skills` / 其它动态渲染底部提示行。

- **两段式会话删除**（`screens/session_select.py`）：
  - 移除单键 `d` / `Delete` 直接删除，改为 `Ctrl+X` 触发 `DeleteArmRequested` 进入 armed 态，再按 `x` / `X` / `Shift+X` 触发 `DeleteRequested`。
  - armed 期间任意其它按键或 `Esc` 取消（`_clear_delete_armed()`），底部提示实时切换为红色确认提示。
  - `action_delete_session()` / `action_cancel_or_close()` 均先清理 armed 状态，切换顶栏标签时也一并复位。

- **视觉与转义修复**：
  - `styles.py`：`#chat-input` 增加 `border-left: solid $primary` 并以 `$surface` 统一背景（聚焦不再变暗）；`#input-area` 最大高度 14 → 18；`#shortcut-help` 新增样式。
  - `session.py` / `tool_card.py`：预览与标题统一 `rich.markup.escape`，修复含方括号内容被当作样式标签吞掉的问题。

- **测试**：
  - 更新 `tests/test_context.py`、`test_tui_layout.py`、`test_session_preview.py`、`test_yolo_allow_all.py` 以匹配三档顶栏、`?` 面板与两段式删除。
  - 全量 166 项测试全部通过。

---

## 25. 会话删除保持选中位置、斜杠命令历史与 Ctrl-Z 挂起后台 (v0.1.3.15)

- **会话删除保持选中位置**（`screens/session_select.py`）：
  - `SessionSelectScreen._populate_options(query, highlight_index=0)`：引入 `highlight_index` 形参，并使用 `idx = max(0, min(highlight_index, len(self._filtered_sessions) - 1))` 进行范围截断保护，替代以往硬编码的 `highlighted = 0`。
  - `action_delete_session()`：在移除会话前记录当前高亮行 `h`，删除数据并更新 `_sessions` 后调用 `_populate_options(inp.value, highlight_index=h)`，使选中行停留在删除位置；若删除的是末尾项则平滑向上回退至新的末尾项。

- **聊天历史支持 `/` 命令与光标行尾**（`widgets/input_area.py` / `screens/chat.py`）：
  - `ChatInput._on_key`：去除 `if not text.startswith("/")` 限制，斜杠命令（`/model`、`/clear` 等）与常规聊天文本一并纳入历史列表并支持连续去重。
  - 调出历史记录（Up/Down）时，通过 `lines = self.text.splitlines()` 将 `cursor_location` 置于末尾 `(len(lines) - 1, len(lines[-1]))`，符合终端 readline 惯性。
  - 历史浏览防拦截保护：在 `ChatScreen.on_text_area_changed` 中，检测到 `_history_index is not None` 时立即调用 `_hide_completion()` 并提前返回，避免历史回退中的 `/` 命令弹出补全面板截获后续的上下箭头键。当用户键入其它字符时重置 `_history_index = None`，无缝恢复斜杠补全。

- **Ctrl-Z 挂起进程至后台**（`app.py` / `screens/help.py` / `widgets/shortcut_help.py`）：
  - 在 `Agent2App` 增加全局 `priority=True` 的 `Binding("ctrl+z,ctrl-z", "suspend_process", "Suspend", priority=True, show=False)`。
  - 触发 Textual 内建 `action_suspend_process()`，向进程发送 `SIGTSTP` 挂起进入后台，用户在终端运行 `fg` 即可恢复运行。
  - 同步更新 `HelpScreen` 与 `ShortcutHelp` 中的按键说明。

- **测试**：
  - `tests/test_session_preview.py`：新增 `test_session_delete_preserves_highlight_index`，覆盖三会话中删除中间项后的高亮索引保持验证。
  - `tests/test_tui_layout.py`：新增 `test_chat_input_history_supports_slash_commands` 与 `test_agent2_app_ctrl_z_suspend`。
  - 全量 169 项自动化测试全部通过。

## 26. 代码审查修复与文档勘误 (v0.1.3.16)

- **MCP 资源泄漏修复**（`mcp.py`）：
  - `_connect_stdio` 中手动管理的 `transport_ctx.__aenter__()` / `session_ctx.__aenter__()` 被 `try...except BaseException` 包裹；若 session 初始化失败，`except` 分支显式调用 `transport_ctx.__aexit__(None, None, None)` 释放已打开的 transport，然后 re-raise。修复了 transport 永不关闭的潜在泄漏路径。

- **配置加载异常收窄**（`agent/base.py`）：
  - `BaseAgent.__init__` 加载 `max_iterations` 时的 `except Exception` 改为 `except (KeyError, ValueError, FileNotFoundError, ImportError)`，并通过 `_logging.getLogger(__name__).warning(...)` 记录回退原因，便于排查配置问题。

- **流式 token 用量估算**（`llm/openai.py`）：
  - `chat_stream` 请求参数新增 `"stream_options": {"include_usage": True}`，显式要求 provider 在最终 chunk 附带 usage。
  - 流结束后检查 `usage_received` 标志，若 provider 未返回 usage（如部分本地 LLM），按 `len(content) // 4` 估算 prompt/completion tokens 并调用 `_record_usage`，保证 `total_usage` 始终有值。

- **Planner JSON 回退校验**（`agent/planner.py`）：
  - `_generate_plan` 的 newline 回退增加 `len(ln) > 3` 过滤，丢弃纯编号（如 `1.`）和空白行，避免无效步骤进入执行流水线。

- **模型名前缀精确匹配**（`llm/base.py`）：
  - `guess_context_window` 的匹配条件从 `if prefix in m`（子串匹配）改为 `if m.startswith(prefix)`（前缀匹配），消除未来新增模型名时的误匹配风险。

- **`rewind()` docstring 补充**（`agent/base.py`）：
  - 明确记录"当请求轮数超过可用 user 消息数时，所有可用轮均被移除（静默截断）"的行为。

- **文档勘误**：
  - `agent_tui_reqs.md`：为三条未实现的功能 `/thinking`（FR-MOD-02）、`/compact`（FR-SES-04）、`/undo`（FR-DIF-02）标注 **(Planned)** 状态。
  - `README.md`：快捷键行补充 `Ctrl+Z 挂起至后台`。

- **测试**：全量 169 项自动化测试全部通过。

## 36. 模型配置扩展、对话语义压缩(/compact)与文件路径补全(@file) (2026-09-10)

- **扩展模型参数与计价模块**（`llm/pricing.py`、`llm/base.py`、`llm/openai.py`、`app/config.py`）：
  - 新增 `agent2.llm.pricing` 模块与 `ModelPricing` 数据模型（输入/输出每 100万 tokens 美元费率），内建 OpenAI、Claude、DeepSeek、Gemini、Qwen 及本地免费模型费率表；
  - `BaseLLM` 与 `OpenAILLM` 支持 `context_window`、`temperature`、`top_k`、`top_p`、`reasoning_effort` 与 `pricing`；
  - `_CONTEXT_WINDOWS` 新增 `deepseek-v4`（1M）、`gemini-2.0`（1M）、`o3-mini`（200k）、`claude-3-7`（200k）等现代模型；针对 OpenAI o 系列推理模型自动处理 `temperature` 不受支持的问题；
  - 会话自动累加计费，在 TUI `ContextBar` / `StatusBar` 实时显示 Token 开销估算，并在 `ModelSelectScreen` 与 CLI `select_model_menu` 中呈现容量与费率。

- **对话历史语义压缩**（`agent/base.py`、`app/tui/screens/chat.py`、`app/chat.py`）：
  - `BaseAgent.compact(keep_recent_turns=1)`：多轮历史过长时，调用 LLM 对过往多轮交互与工具执行输出进行语义摘要并保留关键系统设定与最近轮次，大幅释放上下文窗口；
  - 在 TUI 视窗与 CLI 聊天均接入 `/compact [keep_turns]` 命令，配套 `COMPACT` 会话生命周期日志与界面通知。

- **文件引用与实时路径补全**（`app/tui/file_completion.py`、`app/tui/screens/chat.py`、`app/chat.py`）：
  - 新增 `agent2.app.tui.file_completion`：在输入框键入 `@` 时触发文件/目录实时联想补全浮层，支持层级路径递归与内部无关目录过滤；
  - `_process_context` 全面支持 `@<file path>`、`@path`、`#file`、`#dir` 语法在发送消息时自动注入文件与目录内容。

- **测试**：全量 180 项自动化测试全部通过。

## 37. Tab 补全循环、跨面板导航修复与请求级 TPS/耗时指标 (v0.1.3.18)

- **Tab / Shift+Tab 补全交互重构**（`app/tui/widgets/input_area.py`、`app/tui/screens/chat.py`、`styles.py`）：
  - 补全浮层可见时，`Tab` 不再切面板：当仅有一个候选直接接受，多候选则环形后移高亮；`Shift+Tab` 反向环形前移；无补全时才回退为切换顶层面板。`ChatInput.CycleTabRequested` 增加 `direction` 参数（`1` / `-1`），`shift+tab` 分支 post `-1`。
  - 补全候选渲染加 `❯` 高亮前缀与 `#f0f6fc / #c9d1d9 / #8b949e` 配色，`_show_completion` 记录 `_completion_matches`，`_update_completion_prompts()` 依据 `OptionList.highlighted` 用 `replace_option_prompt_at_index` 就地刷新；新增 `on_option_list_option_highlighted` 保持鼠标/键盘高亮同步。
  - 上游 `ChatScreen` 的 `tab` / `shift+tab` 绑定从 `priority=True` 降为 `priority=False`，确保输入框内的 Tab 补全语义不被截获。
  - 补全列表样式去重：`option-list--option*` 背景透明，仅保留行内高亮色，避免双层底色。

- **跨面板导航栈查找修复**（`screens/model_select.py`、`screens/session_select.py`、`screens/skill_select.py`、`screens/chat.py`）：
  - 原实现以 `self.app.screen_stack[-2]` 猜测 ChatScreen，多层模态叠加（如 Model→Sessions→Skills）时索引漂移，导致切换丢失或高亮错位；改为逆序扫描 `screen_stack` 用 `hasattr(s, "_open_*_dialog")` 精准定位宿主 ChatScreen。
  - 通过 `chat.call_next(getattr(chat, method))` 在 `dismiss()` 之后延后压栈新面板，避免在同一帧内争用屏幕栈。
  - `ChatScreen._set_active_tab` 同时调用 `top_bar._update_tab_classes(tab_id)`，并新增 `_on_screen_resume` 将顶栏强制同步为 `Current`，保证从任意模态返回后顶栏高亮与实际视图一致。

- **请求级性能与吞吐指标**（`llm/base.py`、`llm/openai.py`、`app/tui/widgets/status_bar.py`、`app/tui/widgets/tool_card.py`、`app/tui/screens/chat.py`）：
  - `BaseLLM` 新增计时钩子：`_begin_request()` 记录 `_request_started_monotonic` 与 `last_request_started_at`；`_end_request(usage)` 计算 `last_request_duration`、`last_request_finished_at`、累加 `total_generation_time`，并据 `completion_tokens / duration` 得出 `last_tps`（`last_tokens_per_second` 为别名）。重复调用安全，仅首次产出时长。
  - `OpenAILLM.chat()` / `chat_stream()` 在请求前后自动 `_begin_request()` / `_end_request()` 埋点；流式在 `[...]` 结束后统一结算。
  - `StatusBar` / `ContextBar` 新增 `tps`、`long_operation` 响应式字段，以及 `session_duration` / `last_operation` 只读别名；渲染时追加 `⏱ 会话时长`、`TPS: n tok/s`，并对 `_busy_since` 计算的操作耗时 ≥ `LONG_OPERATION_SECONDS`(5s) 追加 `, started HH:MM:SS`。
  - `ChatScreen` 新增 `_reset_session_metrics()`（切会话/新会话时归零计时与 TPS）、`_record_long_operation()`（仅记录 ≥5s 且开始时间不早于上次的操作）、`_update_tps_from_run()` / `_resolve_tps()`（优先 provider 级 `last_tps`，回退按 `total_usage.completion_tokens` 增量 / 墙钟估算）。
  - `ToolCard` 持有 `_started_at` / `_started_monotonic` / `_duration`，`set_result` 计算耗时，长耗时工具在标题追加 `· 6.3s (started HH:MM:SS)`。
  - 辅助格式化：`_fmt_duration` / `_fmt_clock` / `_fmt_operation_duration` / `_fmt_tps`，并统一 `max(0.0, seconds)` 防负值。

- **UI 视觉微调**（`styles.py`、`widgets/message_list.py`、`widgets/nav_bar.py`）：
  - `#chat-input` 最小高度 `2 → 3`、左侧边角色改为 `#818b98`、背景 `$surface → $panel 35%`、内边距 `0 1 → 1 1`。
  - 移除 `MessageList.on_mount` 的 `anchor(True)`，欢迎横幅顶部锚定（`region.y == 1`）。
  - 移除 `TabItem.on_focus` 中联动切换 active tab 的行为。

- **测试**（`tests/test_file_completion.py`、`tests/test_tui_layout.py`、`tests/test_yolo_allow_all.py`）：新增 Tab 接受单候选 / 循环候选、Shift+Tab 返回 Current 高亮、WelcomeBanner 顶部锚定、Tab 非补全时切面板等用例；全量 187 项自动化测试全部通过。

## 38. MCP 配置增强、/mcp 与 /tools 命令及跨事件循环断连自愈 (v0.1.3.19)

- **MCP 配置扩展与安全持久化**（`src/agent2/mcp.py`、`src/agent2/app/config.py`）：
  - `MCPServerConfig` 支持 `type` (`"sse"` / `"stdio"`, 智能推断)、`url`、`headers` (如 `Authorization: Bearer ...`)、`disabled` 及 `alwaysAllow` / `always_allow`；支持 `["*"]` 通配所有工具免审批。
  - `update_mcp_server_disabled(server_name, disabled)`：安全读写 `~/.config/agent2/config.json`，原地持久化服务器启用/禁用状态。

- **跨事件循环生命周期断裂修复与自动重连自愈**（`src/agent2/mcp.py`、`src/agent2/app/tui/app.py`、`src/agent2/app/chat.py`）：
  - **根因分析**：`build_tui_agent()` / `_build_agent()` 在同步函数内使用 `asyncio.run(manager.connect())` 建立连接。一旦临时 loop 销毁，AnyIO task group 强制退出导致 SSE 传输通道被取消，进入 Textual 的 `app.run()`（新 loop）后调用直接抛出 `Connection closed`，且因 sessions 字典未清空导致状态误判。
  - **Loop 感知与校验**：`MCPManager` 增加 `_server_loops: dict[str, asyncio.AbstractEventLoop]` 记录连接时的 loop，`is_server_connected()` 严格校验 loop 是否匹配且未 closed。
  - **委托式调用与自动重连**：MCP `Tool` 的 `_call` 统一调用 `manager.call_tool(server_name, tool_name, kwargs)`；当检测到非当前 loop 或网络断开时，自动在当前活跃 loop 中重新建立连接并自动重试一次。
  - **启动优雅释放**：`build_tui_agent()` 与 CLI 在启动发现工具后调用 `await manager.close(keep_tools=True)`，优雅退出临时 AnyIO 作用域消除报错，同时完整保留已发现工具的 schema。
  - **退出清理**：`Agent2App.on_unmount()` 与 `_run_single()` 在 finally 块中调用 `await manager.close()`，保证退出的优雅释放。
  - **SDK 兼容**：兼容 MCP Python SDK 2.x 的 `input_schema`（以及 1.x 的 `inputSchema`），正确提取参数定义至 `ToolParameter`。

- **TUI `/mcp` 与 `/tools` 命令**（`src/agent2/app/tui/screens/chat.py`）：
  - `/mcp` 或 `/mcp list`：以表格化树状结构展示已配置的 MCP 服务器状态（`● enabled` / `○ disabled`）、传输类型、URL/命令、激活工具列表及免审批名单。
  - `/mcp enable <name>`：在当前活跃事件循环中连接 MCP 服务器，将工具注册至 `tool_registry`，更新 `alwaysAllow` 审批白名单，并持久化 `disabled: false`。
  - `/mcp disable <name>`：断开服务器连接释放资源，从 `tool_registry` 注销工具并持久化 `disabled: true`。
  - `/tools`：列出当前 Agent 注册的所有本地与 MCP 工具名称及描述。
  - `ChatScreen.on_mount()` 启动后台 worker `_init_mcp_servers()`，在 Textual 活跃 loop 中异步连接 MCP 服务，消除启动卡顿。

- **测试覆盖**（`tests/test_mcp.py`、`tests/test_tui_modes.py`）：
  - 新增 `test_update_mcp_server_disabled`、`test_mcp_manager_connect_server_and_disconnect`、`test_mcp_manager_call_tool_auto_reconnect`、`test_tui_mcp_command`、`test_tui_tools_command` 等用例；
  - 全量 202 项自动化测试全部通过。


## 39. 工具调用显示优化与最后回复不折叠 (v0.1.3.20)

- **友好工具标签**（`src/agent2/app/tui/widgets/tool_card.py`）：
  - `ToolCard._friendly_operation()` 新方法，为 `file_read`/`read_file`、`file_write`/`write_file`、`shell_exec` 三类工具生成简洁的一行标签：`⚙ Read: <path>`、`⚙ Write: <path>`、`⚙ Exec: <command first line>`。
  - `_get_operation_text()` 优先调用 `_friendly_operation()`，命中则返回友好标签，否则回退到原先的泛化格式。
  - `ToolTitle._update_label()` 改为内联拼接 `f"{self.label}  {sym}"`，折叠/展开符号紧跟文本，不再使用 `Table.grid(expand=True)` 右对齐。移除 `rich.table.Table` 导入。

- **最后一条回复不折叠**（`src/agent2/app/tui/widgets/message_list.py`、`src/agent2/app/tui/screens/chat.py`）：
  - `AssistantMessage` 新增 `fold: bool = True` 参数；`_compose_content()` 中 `fold=False` 时直接 `yield Markdown(self._content)` 跳过分段折叠。
  - `MessageList.add_assistant_message()` 透传 `fold` 参数。
  - `ChatScreen._run_agent()` 中最后的 `add_assistant_message(result, ..., fold=False)`，实时对话最后一条回复不折叠。
  - `ChatScreen._rebuild_messages()` 预扫描 `last_assistant_idx`，仅最后一条内容消息 `fold=False`，历史恢复同样保持最后回复展开。

## 40. 状态精细化、MCP HTTP 支持与 /cfg 配置管理与备份容灾 (v0.1.3.21)

- **状态栏状态精细化与工具标签前缀**（`src/agent2/app/tui/widgets/status_bar.py`、`src/agent2/app/tui/widgets/tool_card.py`、`src/agent2/app/tui/screens/chat.py`）：
  - `StatusBar` 与 `ContextBar` 新增 `status_state` 响应式属性：LLM 正常输出完毕无待办时显示 `idle`；当暂停等待确认（Approve 弹窗）、Plan 计划确认、或 LLM 提问等待回复时，统一显示 `wait for input`。
  - 工具操作标签重构：由原有的 `⚙ Read:`、`⚙ Write:`、`⚙ Exec:` 调整为 `⚙ /read:`、`⚙ /write:`、`⚙ /exec:`。
  - 修复卡片标题点击事件冒泡：`ToolTitle._on_click` 调用 `event.prevent_default()` 阻断基类重复触发，彻底解决单击卡片标题导致双次切换无法展开的问题。

- **MCP HTTP (Streamable HTTP) 原生支持**（`src/agent2/mcp.py`）：
  - `MCPServerConfig` 支持 `type: "http"` 及 `type: "streamable_http"`；
  - 新增 `_connect_http` 使用 MCP 官方 `streamable_http_client` 与 `create_mcp_http_client` 建立连接，并支持自定义 `headers`；
  - 向后兼容：`type: "sse"` 发生异常时自动降级回退尝试 Streamable HTTP 协议；
  - 完善 AnyIO 异步任务异常回收：在当前 task 中立即退出 cancel scope 并清理 cleanups，防止跨 task 作用域释放引发 RuntimeError。
  - 测试隔离：TUI 后台 `_init_mcp_servers()` 检测到 pytest 运行环境时跳过全局配置加载，避免测试阻塞。

- **配置管理命令 `/cfg`、自动备份与异常容灾回退**（`src/agent2/app/config.py`、`src/agent2/app/tui/screens/chat.py`、`src/agent2/app/chat.py`、`src/agent2/app/tui/screens/help.py`）：
  - 新增 `/cfg`（及别名 `/config`）斜杠命令：在 TUI（通过 `with app.suspend():`）及 CLI 模式下唤起系统编辑器（`$VISUAL` / `$EDITOR` 或 `nano`/`vim`/`vi`/`notepad`）直接编辑 `~/.config/agent2/config.json`；
  - 编辑前自动创建 `config.json.backup` 备份文件；保存退出后执行 JSON 与 Schema 校验，合法时自动刷新最新备份；
  - `load_config()` 全局捕获读取异常，当 `config.json` 语法错误或解析异常时，自动安全回退加载 `config.json.backup` 作为活跃配置，杜绝配置丢失与应用崩溃。
  - 在 `SLASH_COMMANDS`、命令补全与帮助界面接入 `/cfg`。

- **测试覆盖**（`tests/test_tool_result_title.py`、`tests/test_tui_layout.py`、`tests/test_mcp.py`、`tests/test_cfg_command.py`）：
  - 新增斜杠工具标签断言、状态栏 `idle` / `wait for input` 状态断言、Streamable HTTP 客户端模拟握手与降级测试、`/cfg` 命令交互、备份创建与损坏回退测试；
  - 全量 213 项自动化测试全部通过。

## 41. 工具标签去斜杠+亮灰配色、MCP cleanup 跨 task 修复 (v0.1.3.22)

- **工具调用标签视觉优化**（`src/agent2/app/tui/widgets/tool_card.py`、`src/agent2/app/tui/session.py`）：
  - 去掉 `⚙ /read:` / `⚙ /write:` / `⚙ /exec:` 前缀斜杠，改为 `⚙ read:` / `⚙ write:` / `⚙ exec:`，标签关键词加 `[bold]`。
  - 整体配色由 `[bold yellow]` + `[dim]` 改为 `[#adbac7]`（亮灰，标签）+ `[#768390]`（暗灰，参数/路径）。
  - Session 预览界面同步统一风格：加入 exec/read/write 友好名称映射，取代原有 `[dim yellow]⚙ {tc_name} ...` 格式，未命中的通用工具名同样加粗。

- **MCP cleanup 跨 task cancel scope 错误修复**（`src/agent2/mcp.py`）：
  - 根本原因：anyio cancel scope 要求 `__aexit__` 必须在 `__aenter__` 的同一 asyncio task 中调用；旧代码将 `__aexit__` 存入 `cleanups` 列表后在 `disconnect_server` 里跨 task 调用，触发 "Attempted to exit cancel scope in a different task" 错误。
  - 新增 `_start_server_task()`：为每个 MCP 服务器启动专属后台 `asyncio.Task`，在该 task 内用 `async with transport_ctx / ClientSession` 持有全部 context manager；通过 `asyncio.Queue(maxsize=1)` 将就绪的 `session` 传回调用方，通过 `asyncio.Event` 接收关断信号。
  - `disconnect_server` 改为 `shutdown.set()` + `asyncio.wait_for(shield(task), timeout=5)` 等待 task 自然退出，不再直接调用 `__aexit__`。
  - `MCPManager.__init__` 新增 `_server_tasks` 与 `_server_shutdowns` 字段；`close()` 同步清理这两个字典。
  - 三个 `_connect_*` 方法统一收敛为 `_start_server_task()` 一行调用，代码量大幅减少。

## 42. 高级多 Agent 综合示例（上下文继承/隔离、Skill 选择性激活、Plan 模式与 Prompt 设定）

- **多 Agent 综合模式示例**（`examples/06_advanced_multi_agent.py`）：
  - **上下文不继承（隔离模式）**：各 sub-agent 初始化为完全独立的新实例，互不共享历史与状态，适用于职责严格隔离的子任务。
  - **上下文完整继承**：利用 `orchestrator.fork(name=...)` 深度克隆消息历史与工具上下文，再通过 `set_rule()` 重新赋予特定角色定义。
  - **上下文选择性继承**：实现 `extract_selective_context()`，保留最近 N 轮完整对话原文，早期对话提炼为紧凑摘要作为背景信息注入 sub-agent。
  - **Skill 选择性激活**：实现 `build_prompt_with_skills()`，基于 `discover_skills()` 按需过滤并动态注入指定 Skill 的指令块，支持全激活与完全隔离（最小化模式）。
  - **Plan 模式 Orchestrator**：以 `PlannerAgent` 作为顶层规划编排者，将专业子 Agent（如天气专家、股票专家）封装为 `@tool` 工具，实现由规划模型拆解多步骤后自动分发执行并汇总生成综合报告。
  - **System Prompt 设定与动态切换**：提供构造时定义、运行时 `set_rule()` 动态角色切换（如诗人/程序员/翻译模式转换且保留历史），以及基于模板（`PROMPT_TEMPLATE`）参数化组装的多场景范例。

