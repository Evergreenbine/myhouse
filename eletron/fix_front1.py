c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

# 1) Add renderMarkdown function after buildChatBubble
old = "  return html;\n}\n\n  async function closeAIChat"
new = """  return html;
}
// Markdown renderer
function renderMarkdown(t){
  t=t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  t=t.replace(/```(\\w*)?\\n?([\\s\\S]*?)```/g,"<pre><code>$2</code></pre>");
  t=t.replace(/`([^`]+)`/g,"<code>$1</code>");
  t=t.replace(/\\*\\*([^*]+)\\*\\*/g,"<strong>$1</strong>");
  t=t.replace(/\\*([^*]+)\\*/g,"<em>$1</em>");
  t=t.replace(/^- (.+)$/gm,"<li>$1</li>");
  t=t.replace(/(<li>[\\s\\S]*?<\\/li>\\n?)+/g,"<ul>$&</ul>");
  t=t.replace(/^(\\d+)\\. (.+)$/gm,"<li>$2</li>");
  t=t.replace(/(<li>[\\s\\S]*?<\\/li>\\n?)+/g,"<ol>$&</ol>");
  t=t.replace(/\\n/g,"<br>");
  return t;
}

  async function closeAIChat"""
if old in c:
    c = c.replace(old, new)
    print("1 renderMarkdown OK")
else:
    print("1 NOT found")

# 2) Use renderMarkdown for AI messages in buildChatBubble
old2 = "esc.replace(/\\n/g,'<br>')+'</div>'+(isUser?'<div style=\"text-align:right;margin-top:2px\">"
new2 = "(isUser?esc.replace(/\\n/g,'<br>'):renderMarkdown(content))+'</div>'+(isUser?'<div style=\"text-align:right;margin-top:2px\">"
c = c.replace(old2, new2)
print("2 markdown rendering", "OK" if old2 in c else "not found (may already be done)")

open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
print("saved")