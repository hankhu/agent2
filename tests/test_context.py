"""Tests for agent2.context — Rules and Skills loading."""

from pathlib import Path

from agent2.context import Context, load_context, load_rules, load_skills


def test_context_build_system_prompt_empty():
    ctx = Context()
    assert ctx.build_system_prompt("base") == "base"


def test_context_build_system_prompt_with_rules():
    ctx = Context(rules_text="rule1")
    result = ctx.build_system_prompt("base")
    assert "base" in result
    assert "<rules>" in result
    assert "rule1" in result


def test_context_build_system_prompt_with_skills():
    ctx = Context(skills_text="skill info")
    result = ctx.build_system_prompt("base")
    assert "base" in result
    assert "<skills>" in result
    assert "skill info" in result


def test_context_build_system_prompt_with_both():
    ctx = Context(rules_text="r", skills_text="s")
    result = ctx.build_system_prompt("base")
    assert "<rules>" in result
    assert "<skills>" in result


def test_load_rules_from_directory(tmp_path: Path):
    rules_dir = tmp_path / ".agent2" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "01-style.md").write_text("Use type hints")
    (rules_dir / "02-lang.md").write_text("Reply in Chinese")

    result = load_rules(tmp_path)
    assert "Use type hints" in result
    assert "Reply in Chinese" in result


def test_load_rules_ignores_non_md(tmp_path: Path):
    rules_dir = tmp_path / ".agent2" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "notes.py").write_text("not a rule")

    result = load_rules(tmp_path)
    assert result == ""


def test_load_rules_inline():
    result = load_rules(Path("/nonexistent"), inline_rules=["Always be concise"])
    assert "Always be concise" in result


def test_load_rules_inline_and_files(tmp_path: Path):
    rules_dir = tmp_path / ".agent2" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "a.md").write_text("file rule")

    result = load_rules(tmp_path, inline_rules=["inline rule"])
    assert "file rule" in result
    assert "inline rule" in result


def test_load_skills_from_directory(tmp_path: Path):
    skill_dir = tmp_path / ".agent2" / "skills" / "git-expert"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("You are a git expert.")

    result = load_skills(tmp_path)
    assert "git-expert" in result
    assert "You are a git expert." in result


def test_load_skills_ignores_dir_without_skill_md(tmp_path: Path):
    skill_dir = tmp_path / ".agent2" / "skills" / "empty-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "README.md").write_text("not a SKILL.md")

    result = load_skills(tmp_path)
    assert result == ""


def test_load_context_combines_all(tmp_path: Path):
    # Rules
    rules_dir = tmp_path / ".agent2" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "r.md").write_text("my rule")

    # Skills
    skill_dir = tmp_path / ".agent2" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("skill instructions")

    ctx = load_context(tmp_path, inline_rules=["extra rule"])
    assert "my rule" in ctx.rules_text
    assert "extra rule" in ctx.rules_text
    assert "skill instructions" in ctx.skills_text

    prompt = ctx.build_system_prompt("You are helpful.")
    assert prompt.startswith("You are helpful.")
    assert "<rules>" in prompt
    assert "<skills>" in prompt


def test_load_rules_missing_dir():
    """Loading from a non-existent directory returns empty string."""
    result = load_rules(Path("/does/not/exist"))
    assert result == ""


def test_load_skills_missing_dir():
    result = load_skills(Path("/does/not/exist"))
    assert result == ""


def test_discover_skills_returns_skill_info(tmp_path: Path):
    from agent2.context import discover_skills

    skill_dir = tmp_path / ".agent2" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# My Skill\n\nDo great things.")

    skills = discover_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "my-skill"
    assert skills[0].description == "My Skill"
    assert "Do great things." in skills[0].content
    assert skills[0].path == skill_dir


def test_context_get_skill(tmp_path: Path):
    skill_dir = tmp_path / ".agent2" / "skills" / "git-expert"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("You are a git expert.")

    ctx = load_context(tmp_path)
    assert ctx.get_skill("git-expert") is not None
    assert ctx.get_skill("Git-Expert") is not None  # case-insensitive
    assert ctx.get_skill("nonexistent") is None


def test_context_get_skill_empty():
    ctx = Context()
    assert ctx.get_skill("anything") is None


def test_parse_skill_markdown_yaml_frontmatter():
    from agent2.context import parse_skill_markdown

    content = """---
name: release-tool
description: Automates the release process for the project.
version: 1.0.0
---

# Release Tool
Run release steps here.
"""
    name, desc, body = parse_skill_markdown(content, default_name="fallback")
    assert name == "release-tool"
    assert desc == "Automates the release process for the project."
    assert "Run release steps here." in body


def test_parse_skill_markdown_folded_multiline_description():
    from agent2.context import parse_skill_markdown

    content = """---
name: complex-skill
description: >-
  This is a long description
  spanning multiple lines
  that should be folded into one.
---

Instructions go here.
"""
    name, desc, body = parse_skill_markdown(content, default_name="fallback")
    assert name == "complex-skill"
    assert "This is a long description spanning multiple lines" in desc
    assert body == "Instructions go here."


def test_parse_skill_markdown_no_frontmatter():
    from agent2.context import parse_skill_markdown

    content = """# Plain Skill

Just some markdown instructions without YAML frontmatter.
"""
    name, desc, body = parse_skill_markdown(content, default_name="my-dir")
    assert name == "my-dir"
    assert desc == "Plain Skill"
    assert "Just some markdown" in body


def test_discover_skills_agent2_and_claude_dirs(tmp_path: Path, monkeypatch):
    from agent2.context import discover_skills

    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    agent2_skill = fake_home / ".agent2" / "skills" / "agent2-skill"
    agent2_skill.mkdir(parents=True)
    (agent2_skill / "SKILL.md").write_text("""---
name: agent2-skill
description: From agent2 home
---
Instructions
""")

    claude_skill = fake_home / ".claude" / "skills" / "claude-skill"
    claude_skill.mkdir(parents=True)
    (claude_skill / "SKILL.md").write_text("""---
name: claude-skill
description: From claude home
---
Claude instructions
""")

    work_dir = tmp_path / "work"
    skills = discover_skills(work_dir)
    skill_names = {s.name for s in skills}
    assert "agent2-skill" in skill_names
    assert "claude-skill" in skill_names


def test_discover_skills_priority_override(tmp_path: Path, monkeypatch):
    from agent2.context import discover_skills

    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Global claude skill
    claude_skill = fake_home / ".claude" / "skills" / "shared-skill"
    claude_skill.mkdir(parents=True)
    (claude_skill / "SKILL.md").write_text("""---
name: shared-skill
description: Claude global version
---
Global
""")

    # Project .agent2 skill overrides global
    work_dir = tmp_path / "work"
    proj_skill = work_dir / ".agent2" / "skills" / "shared-skill"
    proj_skill.mkdir(parents=True)
    (proj_skill / "SKILL.md").write_text("""---
name: shared-skill
description: Project override version
---
Project
""")

    skills = discover_skills(work_dir)
    shared = [s for s in skills if s.name == "shared-skill"]
    assert len(shared) == 1
    assert shared[0].description == "Project override version"
    assert shared[0].source == ".agent2/skills"


def test_top_tab_bar_has_skills_tab():
    from agent2.app.tui.widgets.nav_bar import TopTabBar

    tab_ids = [t[0] for t in TopTabBar.TABS]
    assert tab_ids == ["current", "sessions", "skills", "help"]

