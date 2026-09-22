# Agent2 — 沉浸式终端 AI 智能体工作台

Agent2 是一个从零构建的 Python 模块化 Agent 系统框架与全键盘沉浸式终端交互工作台。

## 安装

```bash
# 安装完整版（含沉浸式终端 TUI）
pip install agent2

# 或使用 uv
uv add agent2
```

> 如果您只需要无 UI 的轻量 SDK 或基础 CLI（例如云端容器、自动化脚本集成），请安装 `pip install agent2-core`。

## 启动

在终端直接运行：

```bash
agent2
```

支持多种运行模式与参数：

```bash
agent2 --mode plan      # 以 Plan 模式启动（任务拆解与子 Agent 拓扑派发）
agent2 --mode ask       # 以只读 Ask 模式启动（严格禁止写和执行工具）
agent2 -p "执行目标任务"  # 单轮运行后直接退出
agent2 -i "你好"         # 预设首条消息并进入交互界面
```
