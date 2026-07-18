import traceback

import requests

import local_db as db
from ai_knowledge import init_knowledge_base, search_knowledge
from ai_service import PROVIDERS, ai_svc

from app.services.ai_context import build_rental_ai_context


GUIDED_HELP_REPLY = (
    "我还不能确定你遇到的具体问题。请告诉我：你正在做什么（查询、录入读数、生成账单或收款），"
    "涉及哪个楼栋、房间和月份，以及现在卡在哪一步或页面显示了什么。"
    "我会根据这些信息告诉你下一步怎么处理。"
)


def _safe_ai_reply(content):
    text = str(content or "").strip()
    technical_markers = (
        "连接失败", "API错误", "API 错误", "请求失败", "服务暂时不可用",
        "timeout", "traceback", "exception", "工具不在白名单", "🐱",
    )
    if not text or any(marker.lower() in text.lower() for marker in technical_markers):
        return GUIDED_HELP_REPLY
    return text


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

    orchestrator_error = ""
    try:
        from app.services.ai_orchestrator import chat as skill_chat

        result = skill_chat(data)
        if result and result.get("reply"):
            return result
    except Exception as exc:
        orchestrator_error = str(exc)
        traceback.print_exc()

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
        profile = db.load_app_user() or {}
        ai_nickname = str(profile.get("ai_nickname") or "哈基米").replace("\n", " ").replace("\r", " ").strip()[:20] or "哈基米"
        user_nickname = str(profile.get("user_nickname") or "大王").replace("\n", " ").replace("\r", " ").strip()[:20] or "大王"
        system_prompt = (
            f"你的名字是'{ai_nickname}'，你对用户的称呼是'{user_nickname}'。"
            "请优先根据下面的实时系统数据回答用户问题；不要编造不存在的数据。"
            "如果数据没有录入或上下文没有提供，明确说明缺少数据。"
            "不要展示程序错误、接口错误、工具名称、异常堆栈或内部日志；无法继续时，追问用户正在做什么、涉及的楼栋房间月份和卡住的步骤。"
            "涉及金额时使用人民币并保留两位小数。"
            "识别或解释机械式电表时，黑色数字窗口从左到右是整数位，可能超过4位；标0.1/0.01、红色数字、红框小窗或白底小窗通常是小数位，租房抄表默认忽略小数，只录整数。"
            "例如黑色整数位2088、右侧0.1小数位9，应按2088处理，不要按20889处理。"
            "识别或解释机械式水表时，优先读取长方形数字窗整数位，忽略下方小圆盘小数位，并去掉前导零；例如00712按712处理。"
            "回答简洁实用，首行先给结论，后面用简短分组和紧凑表格。"
            "不要频繁使用 Markdown 大标题、横线和表情符号；除非确实需要，不要输出 ##、---。"
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
        reply = _safe_ai_reply(resp.get("content", ""))
        response = {"type": "assistant_message", "content": reply, "pending_actions": [], "bill_images": []}
        if orchestrator_error:
            response["orchestrator_error"] = orchestrator_error
        return {"reply": reply, "orchestrator_error": orchestrator_error, "response": response}
    except Exception:
        response = {"type": "assistant_message", "content": GUIDED_HELP_REPLY, "pending_actions": [], "bill_images": []}
        if orchestrator_error:
            response["orchestrator_error"] = orchestrator_error
        return {"reply": GUIDED_HELP_REPLY, "orchestrator_error": orchestrator_error, "response": response}


def save_chat(data):
    conv_id = data.get("id", 0)
    title = data.get("title", "")
    messages = data.get("messages", [])
    if conv_id > 0:
        db.update_chat(conv_id, title, messages)
        return {"id": conv_id}
    return {"id": db.save_chat(title, messages)}


def list_chats(data=None):
    data = data or {}
    return db.load_chats(data.get("keyword", ""), bool(data.get("archived", False)))


def delete_chat(data):
    db.delete_chat(data.get("id", 0))
    return {"success": True}


def archive_chat(data):
    db.set_chat_archived(data.get("id", 0), True)
    return {"success": True}


def restore_chat(data):
    db.set_chat_archived(data.get("id", 0), False)
    return {"success": True}


def init_knowledge():
    init_knowledge_base()
    try:
        from app.services.skill_vector_store import sync_skill_index

        skill_index = sync_skill_index(force=True)
    except Exception as e:
        skill_index = {"success": False, "backend": "fallback", "error": str(e)}
    return {"success": True, "skill_index": skill_index}
