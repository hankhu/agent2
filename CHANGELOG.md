# Changelog

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
