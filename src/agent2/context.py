"""Context loader — discovers and loads Rules and Skills.

Rules are plain text/markdown files that get injected into the agent's system prompt.
Skills are reusable instruction packages (SKILL.md) following the Agent Skills specification
with YAML frontmatter (name, description) and Markdown instructions.

Discovery paths for Skills (lower → higher priority):
  - Global:
    - ``~/.config/agent2/skills/``
    - ``~/.claude/skills/``
    - ``~/.agent2/skills/``
  - Project:
    - ``.claude/skills/``
    - ``.agents/skills/``
    - ``.agent2/skills/``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent2.app.config import CONFIG_DIR


# ── Data ────────────────────────────────────────────────────────────


@dataclass
class SkillInfo:
    """Metadata for a discovered skill."""

    name: str
    description: str
    path: Path
    content: str
    body: str = ""
    source: str = ""


@dataclass
class Context:
    """Aggregated rules and skills context."""

    rules_text: str = ""
    skills_text: str = ""
    skills: list[SkillInfo] = field(default_factory=list)

    def build_system_prompt(self, base_prompt: str) -> str:
        """Append rules and skills to *base_prompt*."""
        parts = [base_prompt]
        if self.rules_text:
            parts.append(f"\n\n<rules>\n{self.rules_text}\n</rules>")
        if self.skills_text:
            parts.append(f"\n\n<skills>\n{self.skills_text}\n</skills>")
        return "".join(parts)

    def get_skill(self, name: str) -> SkillInfo | None:
        """Look up a skill by name (case-insensitive)."""
        name_l = name.lower()
        for s in self.skills:
            if s.name.lower() == name_l:
                return s
        return None


# ── Rules ───────────────────────────────────────────────────────────

RULES_EXTS = {".md", ".txt"}


def _collect_rule_files(*dirs: Path) -> list[Path]:
    """Return sorted rule files from *dirs* (earlier dirs = lower priority)."""
    files: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix in RULES_EXTS:
                files.append(f)
    return files


def load_rules(
    work_dir: Path | None = None,
    *,
    inline_rules: list[str] | None = None,
) -> str:
    """Discover rule files and return merged text.

    Parameters
    ----------
    work_dir:
        Project root directory. Defaults to cwd.
    inline_rules:
        Additional inline rules from config.json.
    """
    work_dir = work_dir or Path.cwd()
    dirs = [
        CONFIG_DIR / "rules",               # ~/.config/agent2/rules
        Path.home() / ".agent2" / "rules",  # ~/.agent2/rules
        work_dir / ".agent2" / "rules",     # project .agent2/rules
    ]
    files = _collect_rule_files(*dirs)
    parts: list[str] = []

    # File-based rules
    for f in files:
        try:
            text = f.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
        except OSError:
            continue

    # Inline rules from config
    if inline_rules:
        for r in inline_rules:
            r = r.strip()
            if r:
                parts.append(r)

    return "\n\n".join(parts)


# ── Skills Specification Parser ─────────────────────────────────────


def parse_skill_markdown(content: str, default_name: str) -> tuple[str, str, str]:
    """Parse a SKILL.md file adhering to the skills specification.

    Extracts YAML frontmatter (between leading and closing '---') for metadata
    such as `name` and `description`. Returns (name, description, body).
    """
    content_stripped = content.strip()
    name = default_name
    description = ""
    body = content_stripped

    if content_stripped.startswith("---"):
        parts = content_stripped.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].strip()

            current_key: str | None = None
            current_val_lines: list[str] = []
            block_mode: str | None = None

            def _flush(k: str | None, lines: list[str], bmode: str | None) -> None:
                nonlocal name, description
                if not k:
                    return
                val = ""
                if bmode in (">", ">-"):
                    val = " ".join(l.strip() for l in lines if l.strip())
                elif bmode in ("|", "|-"):
                    val = "\n".join(lines).strip()
                elif lines:
                    val = " ".join(l.strip() for l in lines if l.strip())
                val = val.strip("\"'")
                if k == "name" and val:
                    name = val
                elif k == "description" and val:
                    description = val

            for line in fm_text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if not line.startswith(" ") and not line.startswith("\t") and ":" in line:
                    _flush(current_key, current_val_lines, block_mode)
                    k, rest = line.split(":", 1)
                    current_key = k.strip()
                    rest = rest.strip()
                    if rest in (">", ">-", "|", "|-"):
                        block_mode = rest
                        current_val_lines = []
                    elif rest:
                        block_mode = None
                        current_val_lines = [rest]
                    else:
                        block_mode = None
                        current_val_lines = []
                elif current_key:
                    current_val_lines.append(line.strip())

            _flush(current_key, current_val_lines, block_mode)

    # Fallback for description if not provided in YAML frontmatter
    if not description:
        for line in body.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                description = s.lstrip("# ").strip()[:120]
                break
            description = s[:120]
            break

    return name, description, body


# ── Skills Discovery ────────────────────────────────────────────────


def get_skill_search_dirs(work_dir: Path | None = None) -> list[tuple[Path, str]]:
    """Return search directories for skills ordered by priority (lowest first)."""
    home = Path.home()
    work = work_dir or Path.cwd()
    return [
        (CONFIG_DIR / "skills", "~/.config/agent2/skills"),
        (home / ".claude" / "skills", "~/.claude/skills"),
        (home / ".agent2" / "skills", "~/.agent2/skills"),
        (work / ".claude" / "skills", ".claude/skills"),
        (work / ".agents" / "skills", ".agents/skills"),
        (work / ".agent2" / "skills", ".agent2/skills"),
    ]


def discover_skills(work_dir: Path | None = None) -> list[SkillInfo]:
    """Discover all available skills from standard skill directories.

    Scans:
      - ~/.agent2/skills (primary)
      - ~/.claude/skills
      - .agent2/skills / .agents/skills / .claude/skills (project)
      - ~/.config/agent2/skills (fallback)
    """
    search_dirs = get_skill_search_dirs(work_dir)
    skills_map: dict[str, SkillInfo] = {}

    for d, source_label in search_dirs:
        if not d.is_dir():
            continue
        for child in sorted(d.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                skill_file = child / "SKILL.md"
                try:
                    content = skill_file.read_text(encoding="utf-8").strip()
                    if content:
                        name, desc, body = parse_skill_markdown(content, default_name=child.name)
                        info = SkillInfo(
                            name=name,
                            description=desc,
                            path=child,
                            content=content,
                            body=body,
                            source=source_label,
                        )
                        skills_map[name.lower()] = info
                except OSError:
                    continue

    return list(skills_map.values())


def load_skills(work_dir: Path | None = None) -> str:
    """Discover skills and return merged instruction text."""
    skills = discover_skills(work_dir)
    parts = [
        f"### Skill: {s.name}\nDescription: {s.description}\n\n{s.content}"
        for s in skills
    ]
    return "\n\n---\n\n".join(parts)


# ── Unified entry ───────────────────────────────────────────────────


def load_context(
    work_dir: Path | None = None,
    *,
    inline_rules: list[str] | None = None,
) -> Context:
    """Load all rules and skills into a :class:`Context`.

    Parameters
    ----------
    work_dir:
        Project root directory. Defaults to cwd.
    inline_rules:
        Additional inline rules from config.json.
    """
    skills = discover_skills(work_dir)
    skills_text = "\n\n---\n\n".join(
        f"### Skill: {s.name}\nDescription: {s.description}\n\n{s.content}"
        for s in skills
    )
    return Context(
        rules_text=load_rules(work_dir, inline_rules=inline_rules),
        skills_text=skills_text,
        skills=skills,
    )
