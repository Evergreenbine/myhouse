# -*- coding: utf-8 -*-
"""本地知识库 —— ChromaDB 向量存储 + 文档解析 + 语义检索"""
import os
import json
import re
import chromadb
from chromadb.config import Settings

DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_data")


class KnowledgeBase:
    """本地知识库管理器"""

    def __init__(self):
        self._client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))
        self._ensure_collection()

    def _ensure_collection(self):
        """确保集合存在"""
        try:
            self._collection = self._client.get_collection("company_docs")
        except:
            self._collection = self._client.create_collection("company_docs")

    # ========== 文档上传 ==========

    def add_document(self, title: str, content: str, metadata: dict = None) -> int:
        """添加文档到知识库，返回分段数"""
        chunks = self._split_text(content, chunk_size=500, overlap=50)
        if not chunks:
            return 0

        ids = [f"{title}_{i}" for i in range(len(chunks))]
        metadatas = []
        for i, chunk in enumerate(chunks):
            m = {"title": title, "chunk_index": i, "total_chunks": len(chunks)}
            if metadata:
                m.update(metadata)
            metadatas.append(m)

        # 如果已存在，先删
        existing = self._collection.get(where={"title": title})
        if existing and existing["ids"]:
            self._collection.delete(ids=existing["ids"])

        self._collection.add(documents=chunks, metadatas=metadatas, ids=ids)
        return len(chunks)

    def add_file(self, filepath: str) -> int:
        """上传文件：支持 .txt .md .json .csv .py .docx .pdf"""
        ext = os.path.splitext(filepath)[1].lower()
        title = os.path.basename(filepath)

        if ext in (".txt", ".md", ".py", ".csv", ".json"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return self.add_document(title, content)

        elif ext == ".docx":
            try:
                from docx import Document
                doc = Document(filepath)
                content = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                return self.add_document(title, content)
            except ImportError:
                raise ImportError("需要 python-docx: pip install python-docx")

        elif ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(filepath)
                content = ""
                for page in doc:
                    content += page.get_text()
                doc.close()
                return self.add_document(title, content)
            except ImportError:
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(filepath)
                    content = "\n".join([p.extract_text() or "" for p in reader.pages])
                    return self.add_document(title, content)
                except ImportError:
                    raise ImportError("需要 PyMuPDF 或 PyPDF2: pip install PyMuPDF")
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    # ========== 检索 ==========

    def search(self, query: str, top_k: int = 3) -> list:
        """语义检索，返回最相关的文档片段"""
        results = self._collection.query(query_texts=[query], n_results=top_k)
        items = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results.get("distances") else 0
                items.append({
                    "content": doc,
                    "title": meta.get("title", ""),
                    "score": round(1 - dist, 3) if dist else 1.0,
                })
        return items

    def search_for_ai(self, query: str, top_k: int = 3) -> str:
        """为AI检索，返回格式化文本"""
        items = self.search(query, top_k)
        if not items:
            return ""
        lines = []
        for item in items:
            lines.append(f"【来源：{item['title']}】\n{item['content']}")
        return "\n\n---\n\n".join(lines)

    # ========== 管理 ==========

    def list_documents(self) -> list:
        """列出所有文档标题及分段数"""
        try:
            all_data = self._collection.get()
        except:
            return []
        if not all_data or not all_data["metadatas"]:
            return []

        titles = {}
        for m in all_data["metadatas"]:
            t = m.get("title", "未知")
            titles[t] = titles.get(t, 0) + 1
        return [{"title": k, "chunks": v} for k, v in titles.items()]

    def delete_document(self, title: str):
        """删除文档"""
        existing = self._collection.get(where={"title": title})
        if existing and existing["ids"]:
            self._collection.delete(ids=existing["ids"])

    def get_document_content(self, title: str) -> str:
        """获取文档全文"""
        existing = self._collection.get(where={"title": title})
        if existing and existing["documents"]:
            chunks = existing["documents"]
            # 按chunk_index排序
            pairs = []
            for i, doc in enumerate(chunks):
                idx = existing["metadatas"][i].get("chunk_index", i) if existing["metadatas"] else i
                pairs.append((idx, doc))
            pairs.sort(key=lambda x: x[0])
            return "\n".join([p[1] for p in pairs])
        return ""

    def total_chunks(self) -> int:
        try:
            return self._collection.count()
        except:
            return 0

    # ========== 文本分段 ==========

    def _split_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list:
        """简单分段：按句号/换行断句，尽量不截断"""
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        # 按句号、换行拆分
        sentences = re.split(r'(?<=[。！？\n])', text)
        chunks = []
        current = ""
        for s in sentences:
            if len(current) + len(s) <= chunk_size:
                current += s
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = s
                # 重叠
                if overlap > 0 and chunks:
                    current = chunks[-1][-overlap:] + current if len(chunks[-1]) > overlap else current
        if current.strip():
            chunks.append(current.strip())
        return chunks


# 全局单例
kb = KnowledgeBase()
