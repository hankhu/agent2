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
