import requests

import local_db as db
from ai_knowledge import init_knowledge_base, search_knowledge
from ai_service import PROVIDERS, ai_svc

from app.services.ai_context import build_rental_ai_context


def test_provider(data):
    pid = data.get("_provider", "deepseek")
    provider = PROVIDERS.get(pid, PROVIDERS["deepseek"])
    api_key = data.get("_key", "")
    model = data.get("_model", "deepseek-v4-flash")
    if not api_key:
        return {"reply": "请填写 API Key"}

    if pid == "custom":
        base_url = data.get("_url", "")
        if not base_url:
            return {"reply": "请配置自定义API地址"}
        url = base_url.rstrip("/") + "/chat/completions"
    else:
        url = provider["base_url"].rstrip("/") + "/chat/completions"

    try:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "回复OK"}],
            "max_tokens": 10,
            "temperature": 0,
        }
        r = requests.post(url, json=payload, headers={"Authorization": "Bearer " + api_key}, timeout=10)
        if r.status_code == 200:
            data_resp = r.json()
            content = data_resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return {"reply": "✅ 连通性测试通过（回复：" + content[:40] + "）"}
            return {"reply": "✅ 连通性测试通过"}
        if r.status_code == 401:
            return {"reply": "❌ API Key 无效"}
        if r.status_code == 402:
            return {"reply": "❌ 账户余额不足"}
        try:
            err = r.json().get("error", {}).get("message", "")
        except Exception:
            err = ""
        return {"reply": "❌ 请求失败(" + str(r.status_code) + ")：" + err[:60]}
    except Exception as e:
        return {"reply": "❌ 连接失败：" + str(e)[:60]}


def chat(data):
    if data.get("_test"):
        return test_provider(data)

    try:
        prompt = data.get("prompt", "")
        history = data.get("history", [])
        relevant = search_knowledge(prompt, top_k=3)
        knowledge_text = ""
        if relevant:
            knowledge_text = "\n\n相关系统API参考：\n" + "\n".join([
                "### " + r["title"] + "\n" + r["content"]
                for r in relevant
            ])

        data_context = build_rental_ai_context(prompt)
        system_prompt = (
            "你是租房管理系统助手，名叫'租房小管家'。"
            "请优先根据下面的实时系统数据回答用户问题；不要编造不存在的数据。"
            "如果数据没有录入或上下文没有提供，明确说明缺少数据。"
            "涉及金额时使用人民币并保留两位小数。"
            "回答简洁实用，支持 Markdown 格式。"
            "\n\n实时系统数据：\n" + data_context
        )
        if knowledge_text:
            system_prompt += knowledge_text

        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            role = "assistant" if h.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        resp = ai_svc.call_with_tools(messages, max_tokens=1024)
        return {"reply": resp.get("content", "") or "抱歉，AI 服务暂时不可用"}
    except Exception as e:
        return {"reply": "AI 服务调用失败：" + str(e)}


def save_chat(data):
    conv_id = data.get("id", 0)
    title = data.get("title", "")
    messages = data.get("messages", [])
    if conv_id > 0:
        db.update_chat(conv_id, title, messages)
        return {"id": conv_id}
    return {"id": db.save_chat(title, messages)}


def list_chats():
    return db.load_chats()


def delete_chat(data):
    db.delete_chat(data.get("id", 0))
    return {"success": True}


def init_knowledge():
    init_knowledge_base()
    return {"success": True}

