# -*- coding: utf-8 -*-
"""AI 知识库：系统 API 文档 + TF-IDF 语义检索"""
import json, re, os, math
from collections import defaultdict

# ====== 系统 API 文档（Markdown 格式） ======
SYSTEM_DOCS = r"""
# 租房管理系统 API 参考

## 楼栋管理

### 获取所有楼栋
- 接口: `POST /api/rental`
- 参数: `{"table":"buildings", "action":"list"}`
- 返回: 楼栋列表 `[{id, name, address, created_at}]`

### 获取单个楼栋
- 接口: `POST /api/rental`
- 参数: `{"table":"buildings", "action":"get", "data":{"id":1}}`

### 添加楼栋
- 接口: `POST /api/rental`
- 参数: `{"table":"buildings", "action":"add", "data":{"name":"A栋", "address":"..."}}`

### 更新楼栋
- 接口: `POST /api/rental`
- 参数: `{"table":"buildings", "action":"update", "data":{"id":1, "name":"新名称"}}`

## 房间管理

### 获取房间列表
- 接口: `POST /api/rental`
- 参数: `{"table":"rooms", "action":"list"}` 或 `{"data":{"building_id":1}}`
- 返回: 房间列表 `[{id, building_id, room_number, floor, status}]`
- status: `idle`(空置) / `rented`(已租)

### 添加房间
- 接口: `POST /api/rental`
- 参数: `{"table":"rooms", "action":"add", "data":{"building_id":1, "room_number":"101", "floor":1}}`

### 更新房间
- 接口: `POST /api/rental`
- 参数: `{"table":"rooms", "action":"update", "data":{"id":1, "room_number":"102"}}`

## 租客管理

### 获取租客列表
- 接口: `POST /api/rental`
- 参数: `{"table":"tenants", "action":"list"}` 或 `{"data":{"active_only":true}}`
- 返回: 租客列表 `[{id, name, phone, id_card, status}]`

### 添加租客
- 接口: `POST /api/rental`
- 参数: `{"table":"tenants", "action":"add", "data":{"name":"张三", "phone":"138...", "id_card":"440..."}}`

### 设置租客状态
- 接口: `POST /api/rental`
- 参数: `{"table":"tenants", "action":"set_status", "data":{"id":1, "status":"inactive"}}`

## 合同管理

### 获取合同列表
- 接口: `POST /api/rental`
- 参数: `{"table":"contracts", "action":"list"}` 或 `{"data":{"active_only":true}}`
- 返回: 合同列表，含租客名、房间号、月租、水电单价等

### 添加合同
- 接口: `POST /api/rental`
- 参数: `{"table":"contracts", "action":"add", "data":{"tenant_id":1, "room_id":1, "start_date":"2026-01-01", "monthly_rent":1500, "water_unit_price":5, "electric_unit_price":1.2, "deposit":3000}}`

### 终止合同
- 接口: `POST /api/rental`
- 参数: `{"table":"contracts", "action":"end", "data":{"id":1, "end_date":"2026-12-31"}}`

## 账单管理

### 获取账单列表
- 接口: `POST /api/rental`
- 参数: `{"table":"bills", "action":"list"}` 或 `{"data":{"month":"2026-07"}}`
- 返回: 账单列表 `[{id, contract_id, billing_month, rent_amount, water_fee, electric_fee, other_fee, total_amount, status}]`
- status: `draft`(录入中) / `pending`(待发送) / `pending_payment`(待收款) / `unpaid`(未收) / `partial`(部分收款) / `paid`(已收)

### 添加/更新账单
- 接口: `POST /api/rental`
- 参数: `{"table":"bills", "action":"add", "data":{"contract_id":1, "billing_month":"2026-07", "rent_amount":1500, "water_fee":25, "electric_fee":120, "other_fee":0}}`
- 说明: 如 data 含 id 则更新

### 更新账单状态
- 接口: `POST /api/rental`
- 参数: `{"table":"bills", "action":"update_status", "data":{"id":1, "status":"paid"}}`

## 缴费管理

### 获取缴费记录
- 接口: `POST /api/rental`
- 参数: `{"table":"payments", "action":"list"}`
- 返回: 缴费记录列表

### 添加缴费
- 接口: `POST /api/rental`
- 参数: `{"table":"payments", "action":"add", "data":{"bill_id":1, "amount":1645, "pay_date":"2026-07-05", "pay_method":"微信"}}`

## 水电表管理

### 获取水电表
- 接口: `POST /api/rental`
- 参数: `{"table":"meters", "action":"list"}`
- type: `water`(水表) / `electric`(电表)

### 添加读数
- 接口: `POST /api/rental`
- 参数: `{"table":"readings", "action":"add", "data":{"meter_id":1, "reading_date":"2026-07-01", "reading":1234}}`

## AI 功能

### 对话
- 接口: `POST /api/rental`
- 参数: `{"table":"_ai", "action":"chat", "data":{"prompt":"..."}}`

### 图片识别
- 接口: `POST /api/rental`
- 参数: `{"table":"_ocr", "action":"read", "data":{"image":"data:image/...", "meter_type":"电表"}}`
"""

# ====== TF-IDF 语义检索 ======
def tokenize(text):
    """中文分词（简单按字/词切分）"""
    text = text.lower()
    # 按非字母数字切分
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9_]+', text)
    return tokens

def compute_tfidf(docs):
    """计算所有文档的 TF-IDF 向量"""
    N = len(docs)
    # 计算 DF
    df = defaultdict(int)
    all_tokens = []
    for doc in docs:
        tokens = set(tokenize(doc))
        all_tokens.append(tokens)
        for t in tokens:
            df[t] += 1
    # 计算 TF-IDF
    vectors = []
    for tokens in all_tokens:
        vec = {}
        for t in tokens:
            tf = 1 + math.log(sum(1 for x in tokens if x == t)) if sum(1 for x in tokens if x == t) > 0 else 1
            idf = math.log((N + 1) / (df[t] + 1)) + 1
            vec[t] = tf * idf
        vectors.append(vec)
    return vectors, df

def cosine_sim(v1, v2):
    """余弦相似度"""
    all_keys = set(v1.keys()) | set(v2.keys())
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in all_keys)
    norm1 = math.sqrt(sum(v * v for v in v1.values()))
    norm2 = math.sqrt(sum(v * v for v in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0
    return dot / (norm1 * norm2)

def search(query, docs, top_k=5):
    """TF-IDF 语义搜索"""
    if not docs:
        return []
    doc_texts = [d["title"] + " " + d["content"] for d in docs]
    all_texts = [query] + doc_texts
    vectors, _ = compute_tfidf(all_texts)
    query_vec = vectors[0]
    results = []
    for i, vec in enumerate(vectors[1:]):
        sim = cosine_sim(query_vec, vec)
        results.append((sim, docs[i]))
    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:top_k] if r[0] > 0.05]

# ====== 初始化知识库 ======
def init_knowledge_base():
    """将系统 API 文档写入知识库"""
    from local_db import clear_knowledge, save_knowledge
    clear_knowledge()
    # 按 ## 分块
    sections = re.split(r'\n## ', SYSTEM_DOCS.strip())
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split('\n')
        title = lines[0].strip()
        content = '\n'.join(lines[1:]).strip()
        if title and content:
            category = "api"
            if "楼栋" in title: category = "building"
            elif "房间" in title: category = "room"
            elif "租客" in title: category = "tenant"
            elif "合同" in title: category = "contract"
            elif "账单" in title: category = "bill"
            elif "缴费" in title: category = "payment"
            elif "电表" in title or "水表" in title: category = "meter"
            elif "AI" in title: category = "ai"
            save_knowledge(title, content, category)

def search_knowledge(query, top_k=5):
    """搜索知识库"""
    from local_db import get_all_knowledge
    docs = get_all_knowledge()
    return search(query, docs, top_k)
