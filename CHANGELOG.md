# Changelog

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
