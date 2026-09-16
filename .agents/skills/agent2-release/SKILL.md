---
name: agent2-release
description: >-
  agent2 项目发版固定流程。自动完成版本号递增、文档更新（架构/设计/实现/工作日志/变更日志/功能清单）、
  Git 提交与推送至 GitHub、以及 uv build + uv publish 发布包。
  当用户说"发版"、"发布"、"release"或需要执行发布流程时激活此 skill。
---

# agent2 发版流程

> **适用项目**: agent2 (`/Volumes/code/repos/agent2`)
> **包管理**: uv
> **发布目标**: PyPI (`uv publish`)
> **代码托管**: GitHub (`git@github.com:hankhu/agent2.git`)

---

## 前置条件

- 所有代码修改已完成并经过 review
- 测试通过（如有）
- 用户已确认要发布的版本号（或使用默认的末位 +1）

---

## 发版步骤

严格按以下顺序执行，每步完成后再进行下一步。

### Step 1: 确定版本号

1. 读取 `pyproject.toml` 中当前的 `version` 字段
2. 默认策略：**末位数字 +1**（例如 `0.1.3.9` → `0.1.3.10`）
3. 如果用户指定了版本号，使用用户指定的版本号
4. 用 `replace_file_content` 更新 `pyproject.toml` 中的 version

### Step 2: 查看本次变更

1. 运行 `git log --oneline <上一版本commit>..HEAD` 查看自上次发版以来的提交
2. 运行 `git diff HEAD --stat` 查看未提交的改动
3. 如果有未提交的改动，先理解改动内容，作为文档更新的素材

### Step 3: 更新文档

需要更新的文档清单（仅更新与本次变更相关的内容）：

| 文档 | 路径 | 更新内容 |
|------|------|----------|
| **变更日志** | `CHANGELOG.md` | 在顶部新增版本条目，使用 Keep a Changelog 格式（Added/Changed/Fixed），中英混排 |
| **工作日志** | `memo_dsh.md` | 追加新编号章节，记录本次变更的技术细节 |
| **功能清单** | `FEATURE.md` | 更新版本号，新增功能条目（如有新功能） |
| **架构设计** | `DESIGN.md` | 新增或修改架构描述（如有架构变更） |
| **实现要点** | `IMPLEMENT.md` | 新增实现细节（如有值得记录的实现） |
| **README** | `README.md` | 更新版本号或功能列表（如有重大变更） |

**文档更新原则**：
- 保持现有文档的语言风格（中文技术笔记 + 英文术语内联）
- 使用 `replace_file_content` 做精确编辑，不要重写整个文件
- 没有相关变更的文档不需要更新
- 可以使用子代理并行更新多个文档
- 中型变动：更新工作日志和变更日志，根据情况更新功能清单、实现要点
- 大型变动：更新所有文档
- 如果没有可更新的内容，直接跳过此步骤，但在 report 中需要说明

### Step 4: Git 提交

```bash
git add -A
git commit -m "v<VERSION>: <简要中文描述>"
```

提交信息格式：
- 以 `v<版本号>:` 开头
- 后跟中文简要描述（包含主要特性关键词）
- 例如：`v0.1.3.10: 消息搜索与历史过滤`

### Step 5: 推送到 GitHub

```bash
git push origin main
```

> 如果当前分支不是 `main`，推送当前分支。

### Step 6: 构建并发布

```bash
uv build
uv publish
```

> 注意：`uv publish` 需要 PyPI token 已配置。如果发布失败，报告错误信息给用户。

---

## 错误处理

- **git push 失败**: 检查是否需要先 pull，提示用户处理冲突
- **uv build 失败**: 检查 pyproject.toml 配置是否正确
- **uv publish 失败**: 检查 PyPI token 是否配置，提示用户设置 `UV_PUBLISH_TOKEN` 或 `~/.pypirc`
- **文档格式问题**: 参考现有文档的格式和编号规则

---

## 完成确认

发版完成后，向用户报告：
1. ✅ 版本号：`<NEW_VERSION>`
2. ✅ 更新的文档列表
3. ✅ Git commit hash
4. ✅ GitHub push 状态
5. ✅ PyPI 发布状态
