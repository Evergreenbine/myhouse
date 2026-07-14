# -*- coding: utf-8 -*-
"""业务 Skill 文档注册表。

这里不加载向量模型，只负责读取 Markdown 并切成可检索的小块。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List


SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_heading(line: str) -> str:
    return re.sub(r"^#+\s*", "", line).strip()


def _split_markdown(title: str, content: str) -> List[Dict[str, str]]:
    chunks: List[Dict[str, str]] = []
    current_title = title
    current_lines: List[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current_lines:
                chunks.append({
                    "title": current_title,
                    "content": "\n".join(current_lines).strip(),
                })
            current_title = f"{title} / {_clean_heading(line)}"
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append({
            "title": current_title,
            "content": "\n".join(current_lines).strip(),
        })

    return [c for c in chunks if c["content"]]


def load_skill_chunks() -> List[Dict[str, str]]:
    """读取所有 app/skills/*/SKILL.md 并返回可检索块。"""
    docs: List[Dict[str, str]] = []
    if not SKILL_ROOT.exists():
        return docs

    for skill_file in sorted(SKILL_ROOT.glob("*/SKILL.md")):
        skill_name = skill_file.parent.name
        raw = skill_file.read_text(encoding="utf-8").strip()
        if not raw:
            continue

        first_line = raw.splitlines()[0].strip()
        skill_title = _clean_heading(first_line) or skill_name
        for idx, chunk in enumerate(_split_markdown(skill_title, raw)):
            content = chunk["content"]
            docs.append({
                "id": f"{skill_name}:{idx:02d}",
                "skill": skill_name,
                "title": chunk["title"],
                "content": content,
                "path": str(skill_file.relative_to(Path(__file__).resolve().parents[2])),
                "content_hash": _content_hash(content),
            })

    return docs


def format_skill_hits(hits: List[Dict[str, object]]) -> str:
    if not hits:
        return "无匹配 Skill 文档。"

    lines = []
    for hit in hits:
        lines.append(
            "### {title}\n"
            "Skill: {skill}\n"
            "{content}".format(
                title=hit.get("title", ""),
                skill=hit.get("skill", ""),
                content=hit.get("content", ""),
            )
        )
    return "\n\n".join(lines)
