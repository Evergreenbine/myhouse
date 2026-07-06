# Add call_stream method after call method in ai_service.py
c = open("D:/code/overtime-app/ai_service.py", "r", encoding="utf-8").read()

old_call = """    def call(self, prompt, system_prompt=None, max_tokens=512, temperature=0.7, timeout=30):
        \"\"\"同步调用AI，自动重试3次\"\"\"
        model_name = self._model()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = self._build_payload(model_name, messages, max_tokens=max_tokens, temperature=temperature)"""

new_call = """    def call(self, prompt, system_prompt=None, max_tokens=512, temperature=0.7, timeout=30):
        \"\"\"同步调用AI，自动重试3次\"\"\"
        model_name = self._model()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = self._build_payload(model_name, messages, max_tokens=max_tokens, temperature=temperature)

    def call_stream(self, prompt, system_prompt=None, max_tokens=512, temperature=0.7, timeout=60):
        \"\"\"流式调用AI，逐个token返回\"\"\"
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
            yield "流式输出需要requests库" """

c = c.replace(old_call, new_call)
open("D:/code/overtime-app/ai_service.py", "w", encoding="utf-8").write(c)
print("ai_service OK")