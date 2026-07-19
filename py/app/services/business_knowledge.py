# -*- coding: utf-8 -*-
"""业务知识检索。

给 AI 提供比 Skill.md 更偏规则层的知识：合同、账单、水电、异常处理等。
先走轻量 TF-IDF，避免额外依赖。
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


BUSINESS_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[1] / "business_knowledge"


def _tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    raw_tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+", text)
    tokens: List[str] = []
    for token in raw_tokens:
        tokens.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.extend(list(token))
            tokens.extend(token[i:i + 2] for i in range(max(len(token) - 1, 0)))
    return [t for t in tokens if t]


def _load_docs() -> List[Dict[str, str]]:
    docs: List[Dict[str, str]] = []
    if not BUSINESS_KNOWLEDGE_ROOT.exists():
        return docs
    for md in sorted(BUSINESS_KNOWLEDGE_ROOT.glob("*.md")):
        raw = md.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        lines = [line.rstrip() for line in raw.splitlines()]
        title = ""
        body: List[str] = []
        for line in lines:
            if not title and line.startswith("#"):
                title = re.sub(r"^#+\s*", "", line).strip()
                continue
            body.append(line)
        content = "\n".join(body).strip() or raw
        docs.append({
            "id": md.stem,
            "title": title or md.stem,
            "content": content,
            "path": str(md.relative_to(Path(__file__).resolve().parents[2])),
        })
    return docs


def _cosine(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    keys = set(v1) | set(v2)
    dot = sum(v1.get(k, 0.0) * v2.get(k, 0.0) for k in keys)
    norm1 = math.sqrt(sum(v * v for v in v1.values()))
    norm2 = math.sqrt(sum(v * v for v in v2.values()))
    return dot / (norm1 * norm2) if norm1 and norm2 else 0.0


def _tfidf_vectors(texts: List[str]) -> List[Dict[str, float]]:
    tokenized = [_tokenize(text) for text in texts]
    df = defaultdict(int)
    for tokens in tokenized:
        for token in set(tokens):
            df[token] += 1
    total = max(len(texts), 1)
    vectors: List[Dict[str, float]] = []
    for tokens in tokenized:
        if not tokens:
            vectors.append({})
            continue
        tf = defaultdict(int)
        for token in tokens:
            tf[token] += 1
        vec: Dict[str, float] = {}
        for token, count in tf.items():
            idf = math.log((total + 1) / (df[token] + 1)) + 1.0
            vec[token] = (1.0 + math.log(count)) * idf
        vectors.append(vec)
    return vectors


def search_business_knowledge(query: str, top_k: int = 4) -> List[Dict[str, object]]:
    docs = _load_docs()
    if not docs:
        return []
    query = str(query or "").strip()
    if not query:
        return []

    texts = [query] + [f"{doc['title']}\n{doc['content']}" for doc in docs]
    vectors = _tfidf_vectors(texts)
    query_vec = vectors[0]
    results: List[Dict[str, object]] = []
    query_lower = query.lower()
    query_tokens = set(_tokenize(query))
    for idx, doc in enumerate(docs, start=1):
        doc_vec = vectors[idx]
        score = _cosine(query_vec, doc_vec)
        text = f"{doc['title']}\n{doc['content']}".lower()
        if query_lower in text:
            score += 0.5
        overlap = query_tokens & set(_tokenize(text))
        score += min(len(overlap) * 0.08, 0.32)
        if score <= 0:
            continue
        item = dict(doc)
        item["score"] = round(float(score), 4)
        item["backend"] = "tfidf"
        results.append(item)

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(1, int(top_k or 4))]


def format_business_knowledge_hits(hits: List[Dict[str, object]]) -> str:
    if not hits:
        return "无匹配业务规则文档。"
    lines = []
    for hit in hits:
        lines.append(
            "### {title}\n"
            "来源: {path}\n"
            "{content}".format(
                title=hit.get("title", ""),
                path=hit.get("path", ""),
                content=hit.get("content", ""),
            )
        )
    return "\n\n".join(lines)
