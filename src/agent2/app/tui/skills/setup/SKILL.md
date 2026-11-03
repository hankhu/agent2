---
name: setup
description: >-
  解决 agent2-tui 及 agent2 的所有配置与启动问题。包括 ~/.config/agent2/config.json 格式校验、
  Provider/模型凭据与端点配置、MCP 服务调试、备份自动回退与恢复、环境变量覆盖、以及 TUI 启动异常诊断。
  当用户在终端输入 /setup、或询问如何配置 agent2-tui、遭遇配置解析错误、API Key/Base URL 失效、模型未找到或 MCP 无法连接等问题时激活此 skill。
---

# agent2-tui 配置诊断与解决规范

> **适用范围**: `agent2-tui` 终端交互界面及 `agent2` 配置系统  
> **包管理**: `uv`  
> **激活方式**: TUI 中输入 `/setup` 或 `agent2-tui` 配置问答  
> **核心配置文件**: `~/.config/agent2/config.json`  
> **自动备份文件**: `~/.config/agent2/config.json.backup`  
> **运行时状态文件**: `~/.config/agent2/last_model`、`~/.config/agent2/sessions/`

---

## 1. 配置体系与优先级

配置加载时遵循以下优先级（高到低）：

1. **CLI 命令行参数**: 如 `--model deepseek`、`--no-tools`、`--mode ask`
2. **运行时选择记录**: `~/.config/agent2/last_model`（记录上次在 TUI 中选定的模型）
3. **主配置文件**: `~/.config/agent2/config.json`
4. **备份自动回退**: `~/.config/agent2/config.json.backup`（当主配置文件损坏时自动尝试回退）
5. **环境变量**: `AGENT2_API_KEY`、`AGENT2_BASE_URL`、`AGENT2_DEFAULT_MODEL` 等（`AGENT2_` 前缀）
6. **代码内置默认值**: `model="gpt-4o-mini"`, `max_iterations=50`, `temperature=0.7` 等

---

## 2. 标准配置文件模板 (`~/.config/agent2/config.json`)

```json
{
  "default": "gpt-4o-mini",
  "max_iterations": 50,
  "temperature": 0.7,
  "max_tokens": 4096,
  "context_window": 128000,
  "providers": {
    "openai": {
      "api_key": "sk-proj-..."
    },
    "deepseek": {
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-..."
    },
    "ollama": {
      "base_url": "http://localhost:11434/v1"
    },
    "vllm": {
      "base_url": "http://localhost:8000/v1",
      "api_key": "EMPTY"
    }
  },
  "models": {
    "gpt-4o-mini": {
      "provider": "openai"
    },
    "gpt-4o": {
      "provider": "openai"
    },
    "deepseek": {
      "provider": "deepseek",
      "model_id": "deepseek-chat"
    },
    "deepseek-r1": {
      "provider": "deepseek",
      "model_id": "deepseek-reasoner",
      "reasoning_effort": "high"
    },
    "llama3.1": {
      "provider": "ollama",
      "model_id": "llama3.1:8b"
    }
  },
  "mcp_servers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/yourname/workspace"],
      "disabled": false
    },
    "fetch": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "disabled": false
    }
  },
  "rules": [
    "回答请保持简洁清晰，优先使用中文。"
  ]
}
```

---

## 3. 标准排查与诊断步骤

遇到配置相关问题时，严格按照以下步骤递进定位：

### Step 1: 检查配置文件状态
在终端中执行：
```bash
ls -la ~/.config/agent2/
```
确认是否存在 `config.json`、`config.json.backup` 与 `last_model`。

### Step 2: 验证 JSON 语法与 Pydantic 校验
使用 `uv run` 执行内置快速校验：
```bash
uv run python -c "from agent2.app.config import load_config, validate_after_edit; print(load_config())"
```
- 如果返回 `AppConfig(...)`，说明配置加载成功（或已成功回退）。
- 若输出警告 `Error reading config from ...: ... Using backup ...`，说明主文件语法有错正在使用备份。

### Step 3: 检查模型解析 (Resolve Model)
测试目标模型能否正常解析其 Provider、Base URL 和 API Key：
```bash
uv run python -c "from agent2.app.config import load_config; cfg=load_config(); print(cfg.resolve_model('MODEL_NAME_OR_ALIAS'))"
```
检查输出的 `api_key` 是否非空、`base_url` 是否正确。

### Step 4: 快速测试模型连通性（无需打开完整 TUI）
使用 `-p` 单轮参数快速验证：
```bash
uv run -m agent2.app.tui --model <model_alias> -p "ping"
```
若能正常返回回复，则说明该配置的端点与凭据正常。

---

## 4. 常见问题分类与解决办法

### 场景 1: JSON 格式错误或文件损坏 (SyntaxError / DecodeError)
- **现象**: 启动日志提示 `Error reading config ... Using backup ...`，修改的内容不生效。
- **排查**:
  ```bash
  python3 -m json.tool ~/.config/agent2/config.json
  ```
- **修复**:
  1. 修复多余或遗漏的逗号、缺少引号等语法错误。
  2. 若已无法手工修复，直接从备份恢复：
     ```bash
     cp ~/.config/agent2/config.json.backup ~/.config/agent2/config.json
     ```

### 场景 2: 认证失败 / API Key 缺失 (AuthenticationError 401/403)
- **现象**: 提问时报错 `Incorrect API key` 或 `api_key is required`。
- **排查**:
  1. 查看 `resolve_model` 结果是否成功关联到对应 Provider 的 `api_key`。
  2. 检查 `models` 中的 `provider` 名称是否拼写错误（需与 `providers` 中的键名完全一致）。
- **修复**:
  1. 在 `~/.config/agent2/config.json` 中给对应 provider 添加 `"api_key": "sk-..."`。
  2. 或通过环境变量临时提供：`export AGENT2_API_KEY="sk-..."` 或 `export OPENAI_API_KEY="sk-..."`。

### 场景 3: 无法连接端点 / Base URL 格式错误 (ConnectionRefused / 404)
- **现象**: `APIConnectionError: Connection refused` 或 `404 Not Found`。
- **排查与注意点**:
  - `agent2` 会自动为不包含 `/v1~4` 且不以 `/openai` 结尾的 `base_url` 补齐 `/v1`。
  - 本地服务（如 Ollama、vLLM、LM Studio、LocalAI）：
    - 检查服务是否已启动：`curl http://localhost:11434/v1/models`
    - Ollama 需包含 `/v1`：`"base_url": "http://localhost:11434/v1"`
    - DeepSeek 官方地址：`"base_url": "https://api.deepseek.com/v1"`

### 场景 4: `last_model` 残留导致启动即报错
- **现象**: 启动 TUI 时直接试图加载一个已被删除或不可用的模型。
- **修复**:
  1. 查看当前记录：`cat ~/.config/agent2/last_model`
  2. 修复方式 A：启动时显式指定新模型并更新记录：
     ```bash
     agent2-tui --model gpt-4o-mini
     ```
  3. 修复方式 B：删除记录文件：
     ```bash
     rm ~/.config/agent2/last_model
     ```

### 场景 5: MCP 服务连接超时或崩溃导致卡顿
- **现象**: TUI 启动耗时异常，或提问时提示 MCP 错误。
- **排查**:
  1. 在 TUI 内输入 `/mcp` 查看所有已配置服务器的状态。
  2. 检查 `command` 对应的命令（如 `npx`、`uvx`）是否在当前系统的 `PATH` 中。
- **修复**:
  - 临时禁用该服务：在 TUI 运行 `/mcp disable <server_name>`，或在 `config.json` 中设置 `"disabled": true`。
  - 将绝对路径填入 `command`，例如 `"/usr/local/bin/npx"`。

### 场景 6: 系统编辑器启动失败 (执行 `/cfg` 报错)
- **现象**: 在 TUI 运行 `/cfg` 或 `/config` 时提示编辑器异常。
- **排查**: 系统没有配置默认图形或终端编辑器。
- **修复**:
  配置环境变量，推荐：
  ```bash
  export EDITOR="nano"   # 或 "code --wait", "vim"
  export VISUAL="nano"
  ```

### 场景 7: 包缺失与命令找不到 (`agent2-tui` command not found)
- **现象**: 无法运行 `agent2-tui`。
- **排查**: 是否只安装了 `agent2-core`（核心无界面轻量包）而缺少了 `agent2` 主包。
- **修复**:
  使用 `uv` 安装/运行全功能主包：
  ```bash
  uv run -m agent2.app.tui
  # 或全局/虚拟环境安装:
  uv pip install agent2
  ```

---

## 5. TUI 内置快捷维护命令

在 `agent2-tui` 运行期间，可直接使用以下 Slash Commands 进行实时配置管理：

- `/setup`: 激活本配置排错与向导技能。
- `/cfg` 或 `/config`: 调用系统编辑器直接编辑 `config.json`（自带修改前自动备份与修改后语法校验）。
- `/model`: 呼出模型切换选择面板，支持从 `models` 和 `providers` 列表中即时切换。
- `/mcp`: 查看 MCP 服务列表、测试连通性，或使用 `/mcp enable <name>` / `/mcp disable <name>` 管理服务。
- `/sysmsg`: 查看当前注入了 inline rules 后的系统提示词。
