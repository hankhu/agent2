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
