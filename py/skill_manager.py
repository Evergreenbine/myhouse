# -*- coding: utf-8 -*-
"""Skill Manager — 中文语义匹配"""
import os
import re
import logging
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
SKILL_DIR = os.path.join(os.path.dirname(__file__), "skills")
DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_data")
EXCLUDE_KEYWORDS = {"今天", "今日", "今日"}
logger = logging.getLogger("skill_manager")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[SkillManager] %(message)s"))
    logger.addHandler(_h)
_ef = None
def _get_embedding_function():
    global _ef
    if _ef is None:
        logger.info("loading multilingual embedding model...")
        _ef = SentenceTransformerEmbeddingFunction(model_name="paraphrase-multilingual-MiniLM-L12-v2")
        logger.info("embedding model loaded")
    return _ef
def _simple_parse_frontmatter(content):
    meta = {}
    content = content.lstrip()
    if not content.startswith("---"):
        return meta, content
    end = content.find("---", 3)
    if end == -1:
        return meta, content
    lines = content[3:end].strip().split("\n")
    current_key = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        kv = stripped.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip()
            val = kv[1].strip().strip('"').strip("'")
            if val == "|":
                current_key = key
                meta[key] = ""
            else:
                meta[key] = val
                current_key = None
        elif current_key and stripped:
            meta[current_key] += (" " + stripped) if meta[current_key] else stripped
        else:
            current_key = None
    body = content[end + 3:].strip()
    return meta, body
def _parse_frontmatter(content):
    if HAS_YAML:
        content = content.lstrip()
        if not content.startswith("---"):
            return {}, content
        end = content.find("---", 3)
        if end == -1:
            return {}, content
        try:
            meta = yaml.safe_load(content[3:end])
        except Exception:
            meta = {}
        body = content[end + 3:].strip()
        return meta or {}, body
    else:
        return _simple_parse_frontmatter(content)
def _extract_keywords(desc):
    kw_list = []
    for line in desc.split("\n"):
        line = line.strip()
        if not line or "触发" not in line:
            continue
        trigger_part = line.split("触发", 1)[-1].lstrip("：:").strip()
        for t in re.split(r"[、，,\s]+", trigger_part):
            t = t.strip().strip("。.")
            if len(t) >= 2 and t not in EXCLUDE_KEYWORDS and t not in kw_list:
                kw_list.append(t)
    return kw_list
def _build_keyword_map():
    kw_map = {}
    for name in os.listdir(SKILL_DIR):
        md_file = os.path.join(SKILL_DIR, name, "SKILL.md")
        if not os.path.isfile(md_file):
            continue
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
            meta, _ = _parse_frontmatter(content)
            skill_name = meta.get("name", name)
            desc = meta.get("description", "")
            kw_list = _extract_keywords(desc)
            if kw_list:
                kw_map[skill_name] = kw_list
        except Exception:
            pass
    logger.info(f"keywords: {sum(len(v) for v in kw_map.values())} kw from {len(kw_map)} skills")
    return kw_map
class SkillManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    def _init(self):
        self._skills = {}
        ef = _get_embedding_function()
        self._client = chromadb.PersistentClient(path=DB_PATH, settings=Settings(anonymized_telemetry=False))
        self._ensure_collection(ef)
        self._keyword_map = {}
        self.reload()
    def _ensure_collection(self, ef):
        try:
            self._col = self._client.get_collection("skills", embedding_function=ef)
        except Exception:
            try:
                self._client.delete_collection("skills")
            except Exception:
                pass
            self._col = self._client.create_collection("skills", embedding_function=ef)
    def reload(self):
        if not os.path.isdir(SKILL_DIR):
            logger.warning("skills/ not found")
            return
        self._skills = {}
        self._keyword_map = _build_keyword_map()
        ids, docs, metas = [], [], []
        for name in os.listdir(SKILL_DIR):
            skill_path = os.path.join(SKILL_DIR, name)
            md_file = os.path.join(skill_path, "SKILL.md")
            if not os.path.isfile(md_file):
                continue
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()
                meta, body = _parse_frontmatter(content)
                skill_name = meta.get("name", name)
                desc = meta.get("description", "").strip()
                self._skills[skill_name] = {"meta": meta, "body": body, "path": md_file}
                ids.append(skill_name)
                docs.append(desc + "\n" + body)
                metas.append({"name": skill_name, "path": md_file})
            except Exception as e:
                logger.warning(f"load failed: {md_file} - {e}")
        logger.info(f"loaded {len(self._skills)} skills")
        if ids:
            try:
                existing = self._col.get()["ids"]
                if existing:
                    self._col.delete(ids=existing)
                self._col.add(ids=ids, documents=docs, metadatas=metas)
            except Exception as e:
                logger.warning(f"index failed: {e}")
    def match(self, query, top_k=2):
        if not self._skills or not query:
            return []
        keyword_hits = {}
        for skill_name, keywords in self._keyword_map.items():
            for kw in keywords:
                if kw in query:
                    keyword_hits[skill_name] = max(keyword_hits.get(skill_name, 0), 0.75)
                    break
        try:
            n = min(top_k * 2, len(self._skills))
            results = self._col.query(query_texts=[query], n_results=n)
            vec_matches = {}
            if results and results.get("ids") and results["ids"][0]:
                dists = results.get("distances", [[1]])
                for i, sid in enumerate(results["ids"][0]):
                    dist = dists[0][i] if dists and dists[0] else 1
                    score = max(0, 1 - dist / 2)
                    if score > 0.25:
                        vec_matches[sid] = score
        except Exception:
            vec_matches = {}
        merged = {}
        for sid, score in keyword_hits.items():
            merged[sid] = min(score, 0.99)
        for sid, score in vec_matches.items():
            if sid not in merged:
                merged[sid] = score
            else:
                merged[sid] = min(max(merged[sid], score + 0.1), 0.99)
        sorted_hits = sorted(merged.items(), key=lambda x: -x[1])[:top_k]
        result = []
        for sid, score in sorted_hits:
            if sid in self._skills:
                logger.info(f"matched {sid} score={score}")
                result.append({"name": sid, "body": self._skills[sid]["body"], "score": round(score, 3)})
        return result
    def format_for_prompt(self, query, top_k=2):
        matched = self.match(query, top_k)
        if not matched:
            return ""
        lines = ["\n=== 已激活的业务技能（请按以下规则执行） ===\n"]
        for m in matched:
            lines.append(f"--- 技能 {m['name']} (匹配度 {m['score']}) ---")
            lines.append(m["body"])
        return "\n".join(lines) + "\n"
    def list_skills(self):
        return list(self._skills.keys())
    def hot_reload(self):
        logger.info("hot_reload")
        self.reload()
skill_mgr = SkillManager()
