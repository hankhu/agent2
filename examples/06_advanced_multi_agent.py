"""Example 06: Advanced Multi-Agent — 上下文继承、Skill 选择激活、Plan 模式综合示例。

功能演示：
  1. 上下文不继承（隔离模式）：每个 sub-agent 独立运行，不带任何历史
  2. 上下文完整继承：sub-agent 继承 orchestrator 的全部对话历史（fork）
  3. 上下文选择性继承：仅将指定轮次的摘要作为背景注入
  4. Skill 选择性激活：动态生成 system prompt，按需注入特定 skill
  5. Plan 模式（PlannerAgent）作为 orchestrator，协调多个 ReActAgent
  6. System Prompt 设定：构造时设定、运行时 set_rule() 切换、模板化动态组装

Usage:
    export AGENT2_API_KEY=sk-...   # or set OPENAI_API_KEY / DEEPSEEK_API_KEY
    uv run examples/06_advanced_multi_agent.py
"""

from __future__ import annotations

import asyncio
from textwrap import dedent

from agent2.llm import create_llm
from agent2.agent import ReActAgent, PlannerAgent
from agent2.tools import tool
from agent2.context import discover_skills, SkillInfo


# ──────────────────────────────────────────────────────────────────────────────
# 1. 工具定义（mock）
# ──────────────────────────────────────────────────────────────────────────────


@tool
async def fetch_weather(city: str) -> str:
    """获取指定城市天气（模拟）。"""
    data = {
        "Beijing": "晴，26°C，湿度 40%",
        "Shanghai": "多云，28°C，湿度 65%",
        "Guangzhou": "阵雨，31°C，湿度 80%",
    }
    return data.get(city, f"{city}: 数据暂缺")


@tool
async def fetch_stock(symbol: str) -> str:
    """获取股票最新价格（模拟）。"""
    prices = {"AAPL": "185.20 USD", "TSLA": "248.50 USD", "BIDU": "98.10 USD"}
    return prices.get(symbol.upper(), f"{symbol}: 暂无报价")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Skill 选择性激活工具函数
# ──────────────────────────────────────────────────────────────────────────────


def build_prompt_with_skills(
    base_prompt: str,
    skill_names: list[str],
) -> str:
    """按名称列表选择性激活 skill，拼接进 system prompt。

    Parameters
    ----------
    base_prompt:
        Agent 基础 system prompt。
    skill_names:
        需要激活的 skill 名称（大小写不敏感）。传空列表则不注入任何 skill。
    """
    if not skill_names:
        return base_prompt

    all_skills: list[SkillInfo] = discover_skills()
    name_set = {n.lower() for n in skill_names}
    selected = [s for s in all_skills if s.name.lower() in name_set]

    if not selected:
        return base_prompt  # 没找到匹配 skill，降级

    skill_block = "\n\n---\n\n".join(
        f"### Skill: {s.name}\n{s.body}" for s in selected
    )
    return f"{base_prompt}\n\n<skills>\n{skill_block}\n</skills>"


# ──────────────────────────────────────────────────────────────────────────────
# 3. 上下文选择性提取工具函数
# ──────────────────────────────────────────────────────────────────────────────


def extract_selective_context(
    agent: ReActAgent,
    *,
    last_n_turns: int = 1,
    include_summary: bool = True,
) -> str:
    """从 orchestrator 历史中提取选择性上下文。

    Parameters
    ----------
    agent:
        上游 orchestrator，从其 .messages 中提取。
    last_n_turns:
        保留最近 N 轮原文，其余压缩为文字摘要。
    include_summary:
        是否把早期轮次内容拼成摘要一并返回。
    """
    from agent2.llm.message import Role

    msgs = agent.messages
    user_indices = [i for i, m in enumerate(msgs) if m.role == Role.USER]

    if not user_indices:
        return ""

    split_point = (
        user_indices[-last_n_turns] if len(user_indices) >= last_n_turns else 0
    )
    early_msgs = msgs[:split_point]
    recent_msgs = msgs[split_point:]

    parts: list[str] = []

    if include_summary and early_msgs:
        lines = []
        for m in early_msgs:
            if m.role == Role.SYSTEM:
                continue
            content = (m.content or "")[:300]
            lines.append(f"[{m.role.value.upper()}]: {content}")
        if lines:
            parts.append("--- 历史摘要（已压缩）---\n" + "\n".join(lines) + "\n--- 摘要结束 ---")

    if recent_msgs:
        lines = []
        for m in recent_msgs:
            if m.role == Role.SYSTEM:
                continue
            lines.append(f"[{m.role.value.upper()}]: {m.content or ''}")
        if lines:
            parts.append("--- 最近对话（原文）---\n" + "\n".join(lines) + "\n--- 结束 ---")

    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# 4. 五个演示场景
# ──────────────────────────────────────────────────────────────────────────────

SEP = "=" * 64


# ── 场景 A：上下文不继承（完全隔离） ─────────────────────────────────────────


async def demo_no_inherit(llm) -> None:
    """Sub-agent 完全独立，不接收 orchestrator 的任何历史。"""
    print(f"\n{SEP}")
    print("场景 A：上下文不继承（隔离模式）")
    print(SEP)

    orchestrator = ReActAgent(
        "orchestrator_A",
        llm=llm,
        system_prompt="你是总协调员，负责把任务分发给不同专家。",
    )
    # orchestrator 先建立一些上下文
    r = await orchestrator.chat("请记住：本次分析主题是'全球气候变化'。")
    print(f"[Orchestrator] {r}")
    print(f"[Orchestrator] 历史消息数: {len(orchestrator.messages)}")

    # sub-agent：全新独立实例，不传入任何历史
    sub = ReActAgent(
        "isolated_agent",
        llm=llm,
        system_prompt="你是天气数据分析师，直接回答用户问题。",
        tools=[fetch_weather],
    )
    result = await sub.run("北京今天天气如何？")
    print(f"\n[IsolatedAgent] 自有历史消息数: {len(sub.messages)}  (不含 orchestrator 历史)")
    print(f"[IsolatedAgent] {result}")


# ── 场景 B：上下文完整继承（fork） ───────────────────────────────────────────


async def demo_full_inherit(llm) -> None:
    """Sub-agent 通过 fork() 完整克隆 orchestrator 的全部对话历史。"""
    print(f"\n{SEP}")
    print("场景 B：上下文完整继承（fork）")
    print(SEP)

    orchestrator = ReActAgent(
        "orchestrator_B",
        llm=llm,
        system_prompt="你是一位市场研究专家，负责协调分析工作。",
        tools=[fetch_stock],
    )
    await orchestrator.chat("查询 AAPL 股价，记录结论：'苹果近期强势，建议持有'。")
    print(f"[Orchestrator] 历史消息数: {len(orchestrator.messages)}")

    # fork() 完整继承：sub-agent 拥有与 orchestrator 完全相同的历史
    sub = orchestrator.fork(name="writer_agent")
    # 替换 system prompt 为撰稿人角色
    sub.set_rule("你是一位财经撰稿人，根据已有分析写出简洁的投资摘要。")

    print(f"[WriterAgent]   继承历史消息数: {len(sub.messages)}  (与 orchestrator 相同)")
    result = await sub.chat("根据我们刚才的分析，写一段 30 字以内的投资摘要。")
    print(f"[WriterAgent]   {result}")


# ── 场景 C：上下文选择性继承 ─────────────────────────────────────────────────


async def demo_selective_inherit(llm) -> None:
    """Sub-agent 只注入 orchestrator 历史的选定部分（最近 1 轮原文 + 早期摘要）。"""
    print(f"\n{SEP}")
    print("场景 C：上下文选择性继承")
    print(SEP)

    orchestrator = ReActAgent(
        "orchestrator_C",
        llm=llm,
        system_prompt="你是产品经理，负责需求拆解。",
    )
    # 多轮对话建立历史
    await orchestrator.chat("我们要开发一个天气预报 App，核心功能：实时天气、7 天预报、空气质量。")
    await orchestrator.chat("用户画像：25-40 岁上班族，注重简洁 UI。")
    await orchestrator.chat("优先级：实时天气 > 空气质量 > 7 天预报。")
    print(f"[Orchestrator] 总历史消息数: {len(orchestrator.messages)}")

    # 提取选择性上下文（最近 1 轮原文 + 早期摘要）
    ctx = extract_selective_context(orchestrator, last_n_turns=1, include_summary=True)

    # sub-agent：只注入部分上下文
    sub = ReActAgent(
        "ui_designer",
        llm=llm,
        system_prompt="你是 UI 设计师，根据需求背景给出界面设计建议。",
    )
    task = f"""以下是需求背景（由产品经理提供，部分压缩）：

{ctx}

请根据以上背景，给出天气 App 首页的 UI 布局建议（3 条即可）。"""

    result = await sub.run(task)
    print(f"[UIDesigner] 自有历史消息数: {len(sub.messages)}  (仅含注入的选择性上下文)")
    print(f"[UIDesigner]\n{result}")


# ── 场景 D：Skill 选择性激活 ─────────────────────────────────────────────────


async def demo_selective_skills(llm) -> None:
    """根据任务类型，按需激活不同的 skill 集合注入 system prompt。"""
    print(f"\n{SEP}")
    print("场景 D：Skill 选择性激活")
    print(SEP)

    all_skills = discover_skills()
    print(f"[SkillDiscovery] 发现 {len(all_skills)} 个 skill: {[s.name for s in all_skills]}")

    # Agent 1：尝试激活「数据分析」skill（项目中若无同名 skill 则降级）
    prompt_analyst = build_prompt_with_skills(
        "你是数据分析师，擅长金融数据解读。",
        ["data-analysis", "finance"],   # 按需填写项目 .agents/skills/ 中的 skill 名
    )
    analyst = ReActAgent(
        "skill_analyst",
        llm=llm,
        system_prompt=prompt_analyst,
        tools=[fetch_stock],
    )

    # Agent 2：不激活任何 skill（最小化模式）
    prompt_writer = build_prompt_with_skills(
        "你是内容撰写员，负责将数据转化为易读文字。",
        [],   # 空列表 = 不注入任何 skill
    )
    writer = ReActAgent(
        "skill_writer",
        llm=llm,
        system_prompt=prompt_writer,
    )

    # 流水线：analyst 先分析，writer 再改写
    analysis = await analyst.run("查询 TSLA 股价并给出简短分析。")
    print(f"[SkillAnalyst]\n{analysis}\n")

    summary = await writer.run(
        f"请将以下分析改写为适合普通读者的一句话：\n{analysis}"
    )
    print(f"[SkillWriter]\n{summary}")


# ── 场景 E：Plan 模式（PlannerAgent 作为 orchestrator） ──────────────────────


async def demo_plan_mode(llm) -> None:
    """PlannerAgent 先生成执行计划，再通过工具调用子 agent 完成各步骤，最后整合。"""
    print(f"\n{SEP}")
    print("场景 E：Plan 模式（PlannerAgent orchestrator）")
    print(SEP)

    # 把子 agent 封装为工具，供 Planner 调用
    @tool
    async def run_weather_agent(cities: list[str]) -> str:
        """调用天气专家 agent，查询多个城市天气，返回汇总报告。"""
        agent = ReActAgent(
            "weather_expert",
            llm=llm,
            system_prompt="你是天气数据专家，查询并汇总多城市天气。",
            tools=[fetch_weather],
        )
        return await agent.run(
            f"查询以下城市的天气并按城市列出：{', '.join(cities)}"
        )

    @tool
    async def run_stock_agent(symbols: list[str]) -> str:
        """调用股票专家 agent，查询多只股票价格，返回汇总报告。"""
        agent = ReActAgent(
            "stock_expert",
            llm=llm,
            system_prompt="你是股票数据专家，查询并汇总多只股票价格。",
            tools=[fetch_stock],
        )
        return await agent.run(
            f"查询以下股票最新价格并列出：{', '.join(symbols)}"
        )

    # PlannerAgent：先分解任务为有序步骤，再逐步执行
    planner = PlannerAgent(
        "master_planner",
        llm=llm,
        tools=[run_weather_agent, run_stock_agent],
        system_prompt=dedent("""
            你是首席分析协调员，工作流程：
            1. 制定完整执行计划（拆解步骤）
            2. 依次调用专家 agent 工具执行各步骤
            3. 整合所有结果，给出综合报告

            调用工具时，cities 和 symbols 参数请传入列表格式。
        """).strip(),
        enable_replan=False,
        max_step_iterations=2,
    )

    result = await planner.run(
        "请完成综合调研：\n"
        "1. 查询北京、上海、广州三城市今日天气\n"
        "2. 查询 AAPL 和 TSLA 股价\n"
        "3. 给出一份简洁的综合情况报告"
    )
    print(f"\n[MasterPlanner 最终报告]\n{result}")


# ── 场景 F：System Prompt 设定 ───────────────────────────────────────────────


async def demo_system_prompt(llm) -> None:
    """展示 system prompt 的三种设定方式：构造时、运行时切换、模板动态组装。"""
    print(f"\n{SEP}")
    print("场景 F：System Prompt 设定")
    print(SEP)

    # ── F1: 构造时设定 ──────────────────────────────────────────────
    print("\n--- F1: 构造时设定 ---")
    agent = ReActAgent(
        "translator",
        llm=llm,
        system_prompt="你是一位英中翻译专家，用户输入英文，你输出中文翻译。只输出翻译结果。",
    )
    r = await agent.run("The quick brown fox jumps over the lazy dog.")
    print(f"[Translator] {r}")

    # ── F2: 运行时用 set_rule() 切换角色 ────────────────────────────
    # 同一个 agent 实例，运行时动态切换 system prompt（角色转变）
    print("\n--- F2: 运行时 set_rule() 切换角色 ---")
    agent_switchable = ReActAgent(
        "switchable",
        llm=llm,
        system_prompt="你是一位诗人，用优美的文字回答问题。",
    )
    r1 = await agent_switchable.chat("描述一下秋天。")
    print(f"[诗人模式] {r1}")

    # 切换角色为程序员
    agent_switchable.set_rule("你是一位 Python 程序员，只用代码回答。所有回复只包含代码块，不要解释。")
    r2 = await agent_switchable.chat("写一个计算斐波那契数列的函数。")
    print(f"[程序员模式] {r2}")

    # 再切换为英文翻译
    agent_switchable.set_rule("You are an English translator. Translate the user's Chinese input into English. Output only the translation.")
    r3 = await agent_switchable.chat("今天天气真好，适合出去走走。")
    print(f"[翻译模式] {r3}")

    # ── F3: 模板化动态组装 system prompt ────────────────────────────
    # 根据任务参数动态拼接 system prompt（适合批量创建角色相似但细节不同的 agent）
    print("\n--- F3: 模板化动态组装 ---")

    PROMPT_TEMPLATE = dedent("""
        你是 {domain} 领域的专家顾问。

        ## 约束
        - 回答语言：{language}
        - 回答风格：{style}
        - 字数限制：不超过 {max_words} 字

        ## 额外规则
        {extra_rules}
    """).strip()

    configs = [
        {
            "name": "finance_advisor",
            "domain": "金融投资",
            "language": "中文",
            "style": "专业严谨",
            "max_words": 80,
            "extra_rules": "- 必须附带风险提示\n- 不提供具体买卖建议",
        },
        {
            "name": "travel_advisor",
            "domain": "旅行规划",
            "language": "中文",
            "style": "轻松活泼",
            "max_words": 100,
            "extra_rules": "- 优先推荐性价比高的方案\n- 注意季节因素",
        },
    ]

    questions = [
        "现在适合定投吗？",
        "十月份去哪里旅行比较好？",
    ]

    for cfg, question in zip(configs, questions):
        prompt = PROMPT_TEMPLATE.format(**{k: v for k, v in cfg.items() if k != "name"})
        advisor = ReActAgent(cfg["name"], llm=llm, system_prompt=prompt)
        r = await advisor.run(question)
        print(f"[{cfg['name']}] {r}\n")


# ──────────────────────────────────────────────────────────────────────────────
# 6. 主入口
# ──────────────────────────────────────────────────────────────────────────────


async def main() -> None:
    llm = create_llm("deepseek")

    # 按需取消注释要运行的场景
    await demo_no_inherit(llm)
    await demo_full_inherit(llm)
    await demo_selective_inherit(llm)
    await demo_selective_skills(llm)
    await demo_plan_mode(llm)
    await demo_system_prompt(llm)


if __name__ == "__main__":
    asyncio.run(main())
