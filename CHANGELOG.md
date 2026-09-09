# Changelog

## [0.1.3.15] - 2026-09-10

### Added
- **支持 `Ctrl-Z` 进程挂起切换到后台**：
  - 在 `Agent2App` 配置全局高优先级快捷键 `ctrl+z,ctrl-z`（`priority=True`），绑定到 Textual 原生 `suspend_process` 动作（向进程发送 `SIGTSTP`，在终端中输入 `fg` 即可无缝唤醒恢复）。
  - `HelpScreen` 与内联快捷键面板 `ShortcutHelp` 同步补充 `Ctrl+Z` 挂起后台说明。

### Changed
- **聊天历史支持 `/` 开头的命令**：
  - `ChatInput` 移除提交时对以 `/` 开头命令的过滤限制，所有提交的斜杠命令与普通文本一致记录到输入历史，按 ↑ / ↓ 方向键可无缝回溯。
  - 调出历史记录时光标自动移动至行尾，便于快速编辑。
  - 翻阅历史期间（`_history_index is not None`）在 `ChatScreen.on_text_area_changed` 中主动收起补全浮层，防止补全浮层拦截方向键导致历史回溯卡死。

### Fixed
- **会话删除后选中位置保持不变**：
  - `SessionSelectScreen._populate_options` 接收并维护 `highlight_index`，在有效范围 `[0, len(_filtered_sessions) - 1]` 内校准，避免列表重绘时强制跳回第 0 项。
  - `action_delete_session()` 删除后将删除前记录的高亮位置 `h` 传入 `_populate_options`，删除后光标停留在原地（如删除最后一项则安全停留在新的末尾项）。

## [0.1.3.14] - 2026-09-09

### Added
- **内联快捷键面板 (`ShortcutHelp`)**：
  - 新增 `src/agent2/app/tui/widgets/shortcut_help.py`，在输入框正上方渲染紧凑的按键速查面板（Chat / Sessions / Skills 三段）。
  - 输入框为空时按 `?` 即时切换显示/隐藏，无需再弹出独立 `HelpScreen` 模态；开始输入或切换面板时自动收起。
  - `?` / `+` 在空输入框（含 `MessageList`、`TopTabBar`、`ChatInput` 三处入口）被拦截为即时快捷键，不再需要回车提交。

### Changed
- **顶栏标签精简为 Current / Sessions / Skills 三档**：
  - 移除 `Help` 标签与 `F4` 绑定，帮助信息改为内联 `ShortcutHelp` 面板；`Tab` / `Shift+Tab` 统一用于立即切换上一/下一个顶层面板（含模态视窗内的切换）。
  - `TopTabBar.cycle_tab(direction)` 支持双向循环，`StatusBar` 新增 `active_tab` 响应式属性，按当前面板动态渲染底部快捷键提示。
  - 移除各模态视窗中遗留的 `HelpScreen` 导入与跳转分支。
- **会话删除改为两段式确认**：由单键 `d` / `Delete` 改为 `Ctrl+X` 先进入 armed 状态，再按 `X` 确认；期间任意其它键或 `Esc` 取消，避免误删。
- **输入框视觉优化**：`#chat-input` 改为左侧 `$primary` 竖线强调并统一 `$surface` 背景（聚焦时不再变暗），`#input-area` 最大高度 14 → 18，为快捷键面板预留空间。

### Fixed
- 修复 Session 预览与 `ToolCard` 标题中富文本标签未转义导致的 Rich Markup 解析异常（`session.py` / `tool_card.py` 统一 `rich.markup.escape`）。
- 修复移除 `Help` 标签后相关测试（`test_context` / `test_tui_layout` / `test_session_preview` / `test_yolo_allow_all`）与新交互不一致的回归。

## [0.1.3.13] - 2026-09-09

### Added
- **Context 与 Skills 系统** (`agent2/context.py`)：
  - 自动发现并加载 Rules（`~/.config/agent2/rules`、`~/.agent2/rules`、`.agent2/rules`）与 Skills（`~/.agent2/skills`、`~/.claude/skills`、`.agents/skills` 等），统一注入 Agent 的 system prompt。
  - 解析 `SKILL.md` 的 YAML frontmatter（`name` / `description`），支持折叠多行描述、无 frontmatter 回退与多目录优先级覆盖。
  - 新增 TUI Skills 管理视窗 `SkillSelectScreen`、顶栏 `Skills` 标签、`/skills` 命令、动态 `/<skill_name> [prompt]` 调用与斜杠命令补全集成。
- **MCP (Model Context Protocol) 集成** (`agent2/mcp.py`)：
  - 新增 `MCPManager`，通过 stdio 连接外部 MCP server，将 server 暴露的 tools 自动包装为 agent2 `Tool` 实例。
  - `pyproject.toml` 新增可选依赖 `mcp>=1.0`；用户可在 `config.json` 的 `mcp_servers` 中配置多个 server。
- **多级工具审批作用域** (`agent2/app/approval.py`)：
  - ConfirmCard 升级为 `Approve once` / `In conversation` / `In project` / `Always approve` / `Reject` 五档审批。
  - 审批结果按 conversation / project / global 三级持久化到 `.agent2/approvals.json` 或 `~/.config/agent2/approvals.json`。
  - 新增 `1/y`、`2/c`、`3/p`、`4/a`、`n` / `Esc` 快捷键，Agent 自动读取已授权作用域，减少重复确认。
- **YOLO / Allow-all 自动审批模式**：
  - 新增 `/yolo [on|off|show]` 与 `/allow-all [on|off|show]` 命令，自动批准所有工具执行。
  - YOLO 模式额外向 system prompt 注入自主决策指令，让 LLM 无需向用户提问即可推进任务。
  - `ContextBar` / `StatusBar` 增加 `YOLO` / `ALLOW-ALL` 状态徽标；TUI 与 Chat CLI 均支持。
- **最大迭代次数配置化**：
  - 默认 `max_iterations` 由 `10` 提升至 `50`，支持 `config.json`、`AGENT2_AGENT_MAX_ITERATIONS` 环境变量与构造参数三级优先级。
  - 兼容旧配置字段 `max_turns` / `max_rounds` 自动迁移为 `max_iterations`。
- **Session 预览与 Token 用量持久化**：
  - `SessionManager.list_sessions()` 增加 `message_count` 与 `preview`；会话管理视窗新增右侧预览面板，并支持按预览内容搜索。
  - 持久化 `usage` 字段；恢复会话、切换模型、Plan 子任务聚合均保留 Token 计数。
  - Thought / Tool 完成事件实时刷新 `ContextBar`，取消或异常时 `finally` 也会同步状态栏。
  - 旧会话无 usage 数据时按消息内容 best-effort 估算，并防止上一个会话的计数泄漏到新恢复的会话。
- **ToolCard 结果标题与折叠体验**：
  - 工具卡片标题自动显示操作摘要（shell command / python 首行 / 文件路径 / web query 等），运行中显示 `⏳` 且不可折叠。
  - 成功结果保持紧凑，错误结果额外显示 `❌ Error` 状态行；`Ctrl+O` 批量展开/收起。
- **Chat CLI 同步增强** (`agent2.app.chat`)：
  - 同步支持 Rules/Skills 上下文加载、`/skills`、动态技能调用、MCP tools、`/yolo` 与 `/allow-all`。

### Changed
- 顶层 TUI 标签栏由 `Current` / `Sessions` / `Help` 扩展为 `Current` / `Sessions` / `Skills` / `Help`，快捷键对应 `F1`–`F4`。
- `BaseAgent.from_dict()` 恢复内置工具时按名称去重，避免重复注册。
- `SessionManager.save()` 支持顶层 `usage` 字段，并保留已有标题与 usage 回退逻辑。
- README、FEATURE、DESIGN、IMPLEMENT、memo 文档同步更新。

### Fixed
- 修复 TUI `ContextBar` 始终显示 `Session: 0 tokens`、恢复会话/切换模型后 Token 计数清零、Plan 子任务 Token 未计入会话总量的问题。
- 修复 legacy 会话恢复时旧 Token 计数泄漏的问题。
- 修复 `test_tui_layout.py` WelcomeBanner 文案断言与当前 UI 不一致的测试回归。

## [0.1.3.12] - 2026-09-08

### Added
- **Copilot CLI 风格现代极简 TUI 架构**：
  - 顶部导航栏 `TopTabBar`：包含 `Current`、`Sessions`、`Help` 紧凑标签，支持点击、快捷键（F1/F2/F3）与输入为空时按 `Tab` 键循环切换
  - 极简欢迎横幅 `WelcomeBanner`：呈现 ASCII Mascot 图标、系统免责声明与动态轮播的 Tip 卡片（`/plan`、`/ask`、`#file` 等），支持 `/clear` 后优雅恢复
  - 独立帮助浮层 `HelpScreen`：集中展示运行模式、按键绑定、斜杠命令与上下文语法，支持 `?` / `help` 快捷调出
- **全屏极简视窗交互**：
  - 会话管理视窗 `SessionSelectScreen`：全宽亮蓝高光选框、实时关键词搜索过滤、`↑`/`↓` 键盘导航、`e` 重命名、`d` 删除、`Enter` 恢复会话
  - 模型选择器 `ModelSelectScreen`：顶栏联动、全宽高亮选中条、即打即搜过滤与自定义模型回车直达
- **模型提供商与 Host 智能识别**：
  - 模型选择列表与状态栏统一显示提供商标识（`[provider] model_name`）
  - 若无法确定提供商（如私有网关或局域网 IP），自动提取并选用 `base_url` 的 host（如 `[localhost:11434] llama3.1`）
  - 完善 Rich Markup 括号转义，避免方括号标签被误解析丢失
- **状态栏与上下文栏拆分优化**：
  - `ContextBar`（输入框上方）：显示当前工作目录/执行状态 Spinner、Session Token 用量、上下文占比及模型与提供商
  - `StatusBar`（终端底行）：显示全局快捷键指引与当前交互模式徽标（`[AGENT]` / `[PLAN]` / `[ASK]`）
- 新增单元测试套件 `test_tui_layout.py`，全量 104 项测试 100% 通过

### Changed
- 斜杠命令补全菜单：弹出时按 `Enter` 键等同于 `Tab` 键快速确认补全
- 统一 `_set_busy` 状态管理，修复输入 `?` / `help` 导致终端卡在 `processing...` 的状态同步问题

## [0.1.3.11] - 2026-09-04

### Added
- **模型选择 Drop-down Menu (`Select[str]`)**：将原表格选择列表替换为轻量扁平的下拉菜单组件，支持即打即搜（type-to-search）与回车直接选取，并保留自定义模型输入框
- **用户消息即时挂载与渲染**：输入提交后立即在 DOM 中挂载渲染用户消息并贴底展示，避免等待模型网络请求响应产生卡顿感
- **底部状态栏**：状态栏移至视窗最底部行，位于输入框之下，采用自然竖向流式布局杜绝 dock 层叠冲突

### Changed
- **全面无边框扁平化设计**：移除状态栏、消息卡片、输入框、补全框及弹窗的所有实线边框，基于背景明暗色块呈现极简视觉层级
- **零衬距全贴合视窗**：消除输入框、消息流、模态对话框与主窗口之间的 padding 与 margin，实现边缘完全平铺对齐

## [0.1.3.10] - 2026-09-03

### Added
- 支持 `/retry` 命令与消息级 `🔄 Retry` 操作按钮，精准回退至上一轮或指定节点并重新生成
- 消息列表平滑贴底自动滚动（Sticky Scroll）：未主动上滚时新消息自动滚至最底端，上滚时不打扰视窗，滚回底部自动恢复
- 助手回复代码块（` ``` ` 超过 4 行）与大段文字（超过 8 行或 400 字符）自动使用 `Collapsible` 折叠，保持界面清爽
- 文件写入（`file_write`）Diff 预览（超过 6 行）自动使用 `Collapsible` 折叠
- 全局快捷键 `Ctrl+O` 支持一键展开/折叠消息流中所有折叠块
- 多轮对话达到最大轮数限制时允许无缝继续执行（HITL 弹窗审批、消息卡片 `▶ Continue` 按钮与 `/continue` 命令）
- 新增 9 项测试用例，覆盖重试、自动贴底滚动、折叠渲染与最大轮数继续

## [0.1.3.9] - 2026-09-03

### Added
- 消息级回退与分叉功能：BaseAgent `rewind`/`rewind_to`，TUIReActAgent `fork` override
- `/rewind` 和 `/fork` TUI 命令
- SelectableMessage 选中态 UI 交互，支持 point rewind/fork 按钮
- 新增 9 项测试用例

## [0.1.3.8]

### Changed
- ConfirmCard 改为 inline flow 布局
- Tool result panel 支持 Ctrl+O 折叠/展开

## [0.1.3.7]

### Added
- TUI 交互模式切换：Agent / Plan / Ask 三种模式
- DAG 任务拓扑调度（Plan mode）
- Ask mode 只读沙箱
- 状态栏模式徽标（mode badge）
- 新增 49 项测试用例

## [0.1.3.6]

### Added
- Session logging 与对话导出功能
- LLM token 用量追踪，含 context window 估算
- TUI 状态栏用量显示增强；Usage `__add__` 修复；`/new` `/resume` 用量重置

### Fixed
- **Critical**: reflection retry 改用完整 agent loop 而非单次调用
- **Critical**: JSON 解析失败不再静默视为通过
- **Critical**: TF-IDF 向量在语料变化后重新计算
- **Medium**: planner 使用 `extract_json` 解析；shell tool 使用 `os.killpg`；`assert` 替换为 `ValueError`；logging 加 `threading.Lock`
- 12 项 minor 修复

## [0.1.3.3]

### Added
- TUI 应用：聊天界面、model 选择、session 管理（TUI screens、chat input、message list、status bar、session 持久化、confirmation modal、shell tool）
- Session 选择界面
- `/rename` 命令更新 session 标题并持久化
- Session 管理 modal：支持 rename 和 delete 操作
- 文档文件（初始文档）

### Changed
- TUI 扁平化设计样式全面改版（flat design styling overhaul）
- Python 版本要求降至 `>=3.13`
- 更新 `pyproject.toml` 依赖
- Makefile 新增 `clean` target

## [0.1.1]

### Changed
- 引入多轮对话支持、agent forking 与改进的 base/subclass agent 初始化
- 移除 Google、Anthropic、Ollama provider，专注 OpenAI-compatible LLM
- Wikidata 查询改用 Nominatim → Wikidata entity API 调用
- Wikidata 查找结果缓存；planner prompt 优化以减少冗余 tool call
- 版本号更新至 0.1.1；Python 要求调整为 `>=3.13`

### Added
- Model 配置支持
- Wikidata 城市指标工具及 Tokyo 数据测试脚本

## [0.1.0] - Initial Release

### Added
- 初始 agent 框架：planner、executor、LLM interface、沙箱化 tool 执行
- 交互式 CLI 聊天应用
- 示例更新为使用 deepseek-v4-flash
