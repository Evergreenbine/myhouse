# -*- coding: utf-8 -*-
"""统一AI服务模块 —— 所有页面共用的AI调用入口（使用 requests 库，解决 Windows SSL 兼容问题）"""
import json
import os
import time
import threading
from datetime import datetime

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ========== 模型供应商配置 ==========
PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "key_field": "api_key",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"]
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "key_field": "openai_key",
        "models": ["openai-gpt-4o", "openai-gpt-4o-mini"]
    },
    "zhipu": {
        "name": "智谱",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_field": "zhipu_key",
        "models": ["zhipu-glm-4-plus", "zhipu-glm-4-flash"]
    },
    "custom": {
        "name": "自定义",
        "base_url": "",
        "key_field": "custom_api_key",
        "models": []
    }
}

def get_provider(model_name):
    """根据模型名获取供应商信息"""
    # 优先按完整模型名匹配
    for pid, p in PROVIDERS.items():
        if pid == "custom":
            continue
        if model_name in p["models"]:
            return pid, p
    # 按前缀匹配
    for pid, p in PROVIDERS.items():
        if pid == "custom":
            continue
        if model_name.startswith(pid + "-"):
            return pid, p
    # 如果用户配置了自定义供应商，返回 custom
    try:
        from local_db import load_app_user
        data = load_app_user()
        if data and data.get("custom_base_url", "").strip():
            return "custom", PROVIDERS["custom"]
    except:
        pass
    try:
        from user_auth import load_user_config
        cfg = load_user_config()
        if cfg and getattr(cfg, "custom_base_url", ""):
            return "custom", PROVIDERS["custom"]
    except:
        pass
    return "deepseek", PROVIDERS["deepseek"]

def get_model_display_name(model_name):
    """获取模型显示名称"""
    names = {
        "deepseek-v4-flash": "DeepSeek V4 Flash",
        "deepseek-v4-pro": "DeepSeek V4 Pro",
        "deepseek-chat": "DeepSeek V3",
        "deepseek-reasoner": "DeepSeek R1",
        "openai-gpt-4o": "OpenAI GPT-4o",
        "openai-gpt-4o-mini": "OpenAI GPT-4o Mini",
        "zhipu-glm-4-plus": "智谱 GLM-4-Plus",
        "zhipu-glm-4-flash": "智谱 GLM-4-Flash",
    }
    return names.get(model_name, model_name)

def get_all_models():
    """获取所有可用模型列表"""
    models = []
    for pid, p in PROVIDERS.items():
        for m in p["models"]:
            models.append(m)
    return models


class AIService:
    """全局AI服务单例，提供轻量级AI调用"""
    _instance = None
    _last_quota_alert = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._config_path = os.path.join(os.path.dirname(__file__), "ai_config.json")
        self._page_ref = None
        self._session = None

    def set_page(self, page):
        self._page_ref = page

    def _get_config_value(self, key, default=""):
        """从本地库或 JSON 配置读取指定字段"""
        try:
            from local_db import load_app_user
            data = load_app_user()
            if data and key in data:
                return data[key]
        except:
            pass
        try:
            from user_auth import load_user_config
            cfg = load_user_config()
            if cfg:
                return getattr(cfg, key, default)
        except:
            pass
        return default

    def _load_config(self):
        """加载完整配置（兼容旧 JSON 配置）"""
        try:
            from local_db import load_app_user
            data = load_app_user()
            if data:
                model = data.get("ai_model", "deepseek-v4-flash")
                return {
                    "api_key": data.get("api_key", ""),
                    "openai_key": data.get("openai_key", ""),
                    "zhipu_key": data.get("zhipu_key", ""),
                    "custom_api_key": data.get("custom_api_key", ""),
                    "custom_base_url": data.get("custom_base_url", ""),
                    "custom_model": data.get("custom_model", ""),
                    "ai_provider": data.get("ai_provider", ""),
                    "model": model,
                }
        except:
            pass
        try:
            from user_auth import load_user_config
            cfg = load_user_config()
            if cfg:
                return {
                    "api_key": cfg.api_key or "",
                    "openai_key": getattr(cfg, "openai_key", "") or "",
                    "zhipu_key": getattr(cfg, "zhipu_key", "") or "",
                    "custom_api_key": getattr(cfg, "custom_api_key", "") or "",
                    "custom_base_url": getattr(cfg, "custom_base_url", "") or "",
                    "custom_model": getattr(cfg, "custom_model", "") or "",
                    "ai_provider": getattr(cfg, "ai_provider", "") or "",
                    "model": cfg.ai_model or "deepseek-v4-flash",
                }
        except:
            pass
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _get_session(self):
        if HAS_REQUESTS:
            s = requests.Session()
            s.headers.update({"Content-Type": "application/json"})
            return s
        return None

    def _api_key_for_model(self, model_name):
        """获取指定模型对应的 API Key"""
        cfg = self._load_config()
        pid, provider = get_provider(model_name)
        key_field = provider["key_field"]
        if pid == "custom":
            return cfg.get("custom_api_key", cfg.get("api_key", ""))
        return cfg.get(key_field, cfg.get("api_key", ""))

    def _model(self):
        return self._get_config_value("ai_model", "deepseek-v4-flash")

    def _build_payload(self, model, messages, **kwargs):
        """构建统一的 API 请求 payload"""
        return {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": kwargs.get("max_tokens", 512),
            "temperature": kwargs.get("temperature", 0.7),
        }

    def _api_request(self, model_name, payload, timeout=30):
        """向指定模型的 API 发起请求，返回响应 JSON"""
        pid, provider = get_provider(model_name)
        api_key = self._api_key_for_model(model_name)
        
        if pid == "custom":
            cfg = self._load_config()
            base_url = cfg.get("custom_base_url", "").strip()
            custom_model = cfg.get("custom_model", "").strip()
            if not base_url:
                return None, "🐱幾~ 请先配置自定义 API 地址"
            payload["model"] = custom_model or payload.get("model", "default")
        else:
            base_url = provider["base_url"]
            # 对于内置供应商，确保使用规范模型名清理掉可能的前缀干扰
            pass
            
        url = base_url.rstrip("/") + "/chat/completions"

        if not api_key:
            return None, "🐱幾~ 请在个人设置中配置 " + provider['name'] + " API Key"

        if HAS_REQUESTS:
            sess = self._get_session()
            sess.headers["Authorization"] = "Bearer " + api_key
            r = sess.post(url, json=payload, timeout=timeout)
            if r.status_code != 200:
                err_msg = ""
                try:
                    err_msg = r.json().get("error", {}).get("message", "")
                except:
                    pass
                if r.status_code == 402 or "insufficient" in err_msg.lower() or "quota" in err_msg.lower():
                    self._alert_quota()
                    return None, "🐱 额度不足！(" + err_msg[:60] + ")"
                return None, "API错误(" + str(r.status_code) + "): " + err_msg[:80]
            return r.json(), None
        else:
            import urllib.request
            import ssl
            data = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + api_key,
            })
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    return json.loads(resp.read().decode()), None
            except Exception as e:
                return None, str(e)

    def call(self, prompt, system_prompt=None, max_tokens=512, temperature=0.7, timeout=30):
        """同步调用AI，自动重试3次"""
        model_name = self._model()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = self._build_payload(model_name, messages, max_tokens=max_tokens, temperature=temperature)

    def call_stream(self, prompt, system_prompt=None, max_tokens=512, temperature=0.7, timeout=60):
        """流式调用AI，逐个token返回"""
        model_name = self._model()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = self._build_payload(model_name, messages, max_tokens=max_tokens, temperature=temperature)
        payload["stream"] = True
        
        pid, provider = get_provider(model_name)
        api_key = self._api_key_for_model(model_name)
        if pid == "custom":
            cfg = self._load_config()
            base_url = cfg.get("custom_base_url", "").strip()
            payload["model"] = cfg.get("custom_model", "") or payload.get("model", "default")
        else:
            base_url = provider["base_url"]
        if not api_key:
            yield "请先在个人设置中配置API Key"
            return
        url = base_url.rstrip("/") + "/chat/completions"
        
        if HAS_REQUESTS:
            try:
                sess = requests.Session()
                sess.headers.update({"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
                resp = sess.post(url, json=payload, stream=True, timeout=timeout)
                for line in resp.iter_lines():
                    if line:
                        txt = line.decode("utf-8").strip()
                        if txt.startswith("data: "):
                            data = txt[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                            except:
                                pass
            except Exception as e:
                yield "连接失败: " + str(e)[:60]
        else:
            yield "流式输出需要requests库" 

        last_error = ""
        for attempt in range(3):
            try:
                result, err = self._api_request(model_name, payload, timeout)
                if err:
                    if "API Key" in err:
                        return err
                    last_error = err
                    break
                return result["choices"][0]["message"]["content"]
            except Exception as e:
                last_error = "🐱 连接失败(第" + str(attempt+1) + "次): " + str(e)[:80]
                if attempt < 2:
                    time.sleep(1.5)
        return last_error or "🐱 AI睡着了..."

    def _alert_quota(self):
        now = datetime.now()
        if self._last_quota_alert and (now - self._last_quota_alert).seconds < 3600:
            return
        self._last_quota_alert = now
        if self._page_ref:
            try:
                self._page_ref.show_snack_bar(
                    __import__('flet').SnackBar(
                        __import__('flet').Text("⚠️ DeepSeek API 额度不足！请前往 platform.deepseek.com 充值。", size=13, color="white"),
                        bgcolor="#F54A45", duration=10000))
            except:
                pass

    def call_async(self, prompt, callback, system_prompt=None, max_tokens=512, temperature=0.7):
        def _run():
            result = self.call(prompt, system_prompt, max_tokens, temperature)
            callback(result)
        threading.Thread(target=_run, daemon=True).start()

    def call_with_tools(self, messages, tools=None, max_tokens=1024, temperature=0.7, timeout=90, model=None):
        """同步调用AI，支持Tool Calls，自动重试"""
        model_name = model or self._model()

        payload = self._build_payload(model_name, messages, max_tokens=max_tokens, temperature=temperature)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        last_error = ""
        for attempt in range(3):
            try:
                result, err = self._api_request(model_name, payload, timeout)
                if err:
                    if "API Key" in err:
                        return {"content": err, "tool_calls": None}
                    last_error = err
                    break
                choice = result["choices"][0]
                msg = choice["message"]
                return {
                    "content": msg.get("content", ""),
                    "tool_calls": msg.get("tool_calls"),
                    "finish_reason": choice.get("finish_reason", ""),
                }
            except Exception as e:
                last_error = "连接失败(第" + str(attempt+1) + "次): " + str(e)[:60]
                if attempt < 2:
                    time.sleep(1.5)
        return {"content": "🐱 " + last_error, "tool_calls": None}


ai_svc = AIService()
