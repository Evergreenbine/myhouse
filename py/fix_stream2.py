c = open("D:/code/overtime-app/api_server.py", "r", encoding="utf-8").read()
# Find the AI chat endpoint and add streaming after it
ai_chat = 'if path == "/api/ai/chat":'
idx = c.find(ai_chat)
if idx >= 0:
    # Find the next "if path" or "elif path" after this block
    after = c.find("\n", idx) + 1  # start of the next line
    # Find the block by looking for the return statement
    ret = c.find("\"", c.find("reply=", idx))
    # Actually, find the end of the "/api/ai/chat" block - it ends with a return
    ret_end = c.find("})", c.find("return self._send_json", idx)) + 2
    # Find the next "elif path" or "if path"
    next_path = c.find("\n            elif path", ret_end)
    stream_code = '''
            if path == "/api/ai/chat/stream":
                prompt = body.get("prompt", "")
                model = body.get("model", "")
                persona = body.get("personality", "warm")
                history = body.get("history", [])
                sp = "\u4f60\u662f\u54c8\u57fa\u7c73\uff0c\u4e00\u4e2a\u53ef\u7231\u7684AI\u52a9\u624b..."
                if persona == "tsundere":
                    sp = "\u4f60\u662f\u54c8\u57fa\u7c73\uff0c\u50b2\u5a07\u7684AI\u52a9\u624b..."
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    for token in ai_svc.call_stream(prompt, system_prompt=sp, max_tokens=1024, temperature=0.7, timeout=60):
                        self.wfile.write(("data: " + json.dumps({"token": token}) + "\\n\\n").encode("utf-8"))
                        self.wfile.flush()
                except Exception as ex:
                    self.wfile.write(("data: " + json.dumps({"error": str(ex)}) + "\\n\\n").encode("utf-8"))
                self.wfile.write(("data: [DONE]\\n\\n").encode("utf-8"))
                return
'''
    c = c[:next_path] + stream_code + c[next_path:]
    open("D:/code/overtime-app/api_server.py", "w", encoding="utf-8").write(c)
    print("streaming endpoint added")
else:
    print("AI chat endpoint not found")