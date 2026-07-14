# -*- coding: utf-8 -*-
"""Skill 向量检索。

ChromaDB 和 embedding 模型都采用懒加载：后端启动不会加载模型，第一次检索或同步索引时才加载。
如果依赖未安装或模型加载失败，会自动退回到轻量关键词检索。
"""
from __future__ import annotations

import math
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

from app.services.skill_registry import load_skill_chunks


EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
COLLECTION_NAME = "myhouse_business_skills_v1"
CHROMA_PATH = Path(__file__).resolve().parents[2] / "data" / "chroma"
HF_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "hf_cache"

os.environ.setdefault("HF_HOME", str(HF_CACHE_PATH))
os.environ.setdefault("HF_HUB_CACHE", str(HF_CACHE_PATH))

_LOCK = threading.Lock()
_MODEL = None
_CLIENT = None
_COLLECTION = None
_INDEX_READY = False
_BACKEND = "fallback"
_LAST_ERROR = ""


def _tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    raw_tokens = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", text)
    tokens: List[str] = []
    for token in raw_tokens:
        tokens.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.extend(list(token))
            tokens.extend(token[i:i + 2] for i in range(max(len(token) - 1, 0)))
    return [t for t in tokens if t]


def _fallback_search(query: str, top_k: int = 5) -> List[Dict[str, object]]:
    docs = load_skill_chunks()
    query_tokens = set(_tokenize(query))
    if not docs or not query_tokens:
        return []

    results = []
    query_text = (query or "").lower()
    for doc in docs:
        text = f"{doc['title']}\n{doc['content']}".lower()
        doc_tokens = set(_tokenize(text))
        overlap = query_tokens & doc_tokens
        phrase_bonus = sum(2.0 for token in query_tokens if len(token) >= 2 and token in text)
        score = len(overlap) + phrase_bonus
        if query_text and query_text in text:
            score += 5.0
        if score > 0:
            item = dict(doc)
            item["score"] = round(float(score), 4)
            item["backend"] = "fallback"
            results.append(item)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def _get_model():
    global _MODEL
    if _MODEL is None:
        allow_download = os.getenv("MYHOUSE_EMBEDDING_ALLOW_DOWNLOAD", "").lower() in {"1", "true", "yes"}
        if not allow_download and not _has_local_model_cache():
            raise RuntimeError(
                "本地未缓存 embedding 模型，已使用关键词检索降级；"
                "如需自动下载，请设置 MYHOUSE_EMBEDDING_ALLOW_DOWNLOAD=1 后重新同步索引。"
            )

        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            cache_folder=str(HF_CACHE_PATH),
            local_files_only=not allow_download,
        )
    return _MODEL


def _has_local_model_cache() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache

        cached = try_to_load_from_cache(
            EMBEDDING_MODEL_NAME,
            "modules.json",
            cache_dir=str(HF_CACHE_PATH),
        )
        return isinstance(cached, str) and os.path.exists(cached)
    except Exception:
        return False


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        import chromadb

        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _CLIENT = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _CLIENT


def _embed_texts(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()
    return [list(v) for v in embeddings]


def _reset_collection():
    global _COLLECTION
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    _COLLECTION = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return _COLLECTION


def sync_skill_index(force: bool = False) -> Dict[str, object]:
    """同步 Skill.md 到 Chroma。

    返回 backend=fallback 表示依赖缺失或模型不可用，调用方仍可使用关键词检索。
    """
    global _BACKEND, _COLLECTION, _INDEX_READY, _LAST_ERROR

    with _LOCK:
        if _INDEX_READY and not force:
            return {
                "success": _BACKEND == "chroma",
                "backend": _BACKEND,
                "model": EMBEDDING_MODEL_NAME if _BACKEND == "chroma" else "",
                "path": str(CHROMA_PATH),
                "error": _LAST_ERROR,
            }

        docs = load_skill_chunks()
        if not docs:
            _BACKEND = "fallback"
            _LAST_ERROR = "未找到 Skill.md 文档"
            _INDEX_READY = True
            return {"success": False, "backend": _BACKEND, "count": 0, "error": _LAST_ERROR}

        try:
            collection = _reset_collection() if force or _COLLECTION is None else _COLLECTION
            texts = [f"{d['title']}\n{d['content']}" for d in docs]
            embeddings = _embed_texts(texts)
            collection.upsert(
                ids=[d["id"] for d in docs],
                documents=[d["content"] for d in docs],
                metadatas=[{
                    "skill": d["skill"],
                    "title": d["title"],
                    "path": d["path"],
                    "content_hash": d["content_hash"],
                } for d in docs],
                embeddings=embeddings,
            )
            _BACKEND = "chroma"
            _LAST_ERROR = ""
            _INDEX_READY = True
            return {
                "success": True,
                "backend": _BACKEND,
                "count": len(docs),
                "model": EMBEDDING_MODEL_NAME,
                "path": str(CHROMA_PATH),
            }
        except Exception as exc:
            _BACKEND = "fallback"
            _LAST_ERROR = str(exc)
            _INDEX_READY = True
            return {
                "success": False,
                "backend": _BACKEND,
                "count": len(docs),
                "model": "",
                "path": str(CHROMA_PATH),
                "error": _LAST_ERROR,
            }


def search_skills(query: str, top_k: int = 5) -> List[Dict[str, object]]:
    info = sync_skill_index(force=False)
    if info.get("backend") != "chroma":
        return _fallback_search(query, top_k)

    try:
        collection = _COLLECTION or _get_client().get_or_create_collection(COLLECTION_NAME)
        query_embedding = _embed_texts([query or ""])[0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=max(1, int(top_k or 5)),
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: List[Dict[str, object]] = []
        for idx, doc_id in enumerate(ids):
            meta = metadatas[idx] or {}
            distance = float(distances[idx]) if idx < len(distances) else math.nan
            hits.append({
                "id": doc_id,
                "skill": meta.get("skill", ""),
                "title": meta.get("title", ""),
                "content": docs[idx] if idx < len(docs) else "",
                "path": meta.get("path", ""),
                "content_hash": meta.get("content_hash", ""),
                "score": round(1.0 - distance, 4) if not math.isnan(distance) else 0,
                "backend": "chroma",
            })
        return hits
    except Exception:
        return _fallback_search(query, top_k)


def get_skill_index_status() -> Dict[str, object]:
    return {
        "ready": _INDEX_READY,
        "backend": _BACKEND,
        "model": EMBEDDING_MODEL_NAME if _BACKEND == "chroma" else "",
        "path": str(CHROMA_PATH),
        "last_error": _LAST_ERROR,
    }
