c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

# 1) Add renderMarkdown function (add after buildChatBubble)
old = "  return html;\n}\n\n  async function closeAIChat"
new = """  return html;
}

function renderMarkdown(t){
  t=t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  t=t.replace(/\x60\x60\x60(\w*)?\n?([\s\S]*?)\x60\x60\x60/g,"<pre><code>$2</code></pre>");
  t=t.replace(/\x60([^\x60]+)\x60/g,"<code>$1</code>");
  t=t.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>");
  t=t.replace(/\*([^*]+)\*/g,"<em>$1</em>");
  t=t.replace(/^- (.+)$/gm,"<li>$1</li>");
  t=t.replace(/(<li>.*<\/li>\n?)+/g,"<ul>$&</ul>");
  t=t.replace(/^(\d+)\. (.+)$/gm,"<li>$2</li>");
  t=t.replace(/(<li>.*<\/li>\n?)+/g,"<ol>$&</ol>");
  t=t.replace(/\n/g,"<br>");
  return t;
}

  async function closeAIChat"""
c = c.replace(old, new)
print("1 renderMarkdown OK")

# 2) Use renderMarkdown for AI responses in buildChatBubble
old_bubble = "html+='<div><div style=\"font-size:10px;color:var(--text-third);margin-bottom:2px;'+(isUser?'text-align:right':'')+'\">'+name+'</div><div class=\"'+cls+'\">'+esc.replace(/\\n/g,'<br>')+'</div>'+(isUser?'<div style=\"text-align:right;margin-top:2px\"><span onclick=\"navigator.clipboard.writeText(decodeURIComponent(\\'+encodeURIComponent(content)+'\\'))\" style=\"font-size:12px;color:var(--text-third);cursor:pointer;opacity:0.6\" title=\"复制\">\\uD83D\\uDCCB</span></div>':'')+'</div>';"
new_bubble = "html+='<div><div style=\"font-size:10px;color:var(--text-third);margin-bottom:2px;'+(isUser?'text-align:right':'')+'\">'+name+'</div><div class=\"'+cls+'\">'+(isUser?esc.replace(/\\n/g,'<br>'):renderMarkdown(content))+'</div>'+(isUser?'<div style=\"text-align:right;margin-top:2px\"><span onclick=\"navigator.clipboard.writeText(decodeURIComponent(\\'+encodeURIComponent(content)+'\\'))\" style=\"font-size:12px;color:var(--text-third);cursor:pointer;opacity:0.6\" title=\"复制\">\\uD83D\\uDCCB</span></div>':'')+'</div>';"
if old_bubble in c:
    c = c.replace(old_bubble, new_bubble)
    print("2 markdown rendering OK")
else:
    print("2 bubble not found, checking...")
    idx = c.find("html+='<div><div style=\"font-size:10px")
    if idx >= 0:
        print("  found at", idx)

# 3) Add deleteConv function + delete button in sidebar conv items
old_conv_item = "sideH+='<div onclick=\"switchAIConv('+c.id+')\" style=\"display:flex;align-items:center;padding:8px 10px;cursor:pointer;border-radius:8px;font-size:12px;color:var(--text-sec);margin:2px;"+(c.id===loadConvId?'background:var(--blue-light);font-weight:bold;color:var(--blue);border-bottom:2px solid var(--blue)':'')+'\"><span style=\"flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">'+c.title+'</span><span onclick=\"event.stopPropagation();archiveConv('+c.id+')\" style=\"font-size:11px;cursor:pointer;margin-left:4px;opacity:0.5\" title=\"\">\\U0001f4c4</span></div>';"
new_conv_item = "sideH+='<div onclick=\"switchAIConv('+c.id+')\" style=\"display:flex;align-items:center;padding:8px 10px;cursor:pointer;border-radius:8px;font-size:12px;color:var(--text-sec);margin:2px;"+(c.id===loadConvId?'background:var(--blue-light);font-weight:bold;color:var(--blue);border-bottom:2px solid var(--blue)':'')+'\"><span style=\"flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">'+c.title+'</span><span onclick=\"event.stopPropagation();archiveConv('+c.id+')\" style=\"font-size:11px;cursor:pointer;margin-left:4px;opacity:0.5\" title=\"\">\\U0001f4c4</span><span onclick=\"event.stopPropagation();if(confirm(\\'确定删除此对话？\\')){api(\\'/api/chat/delete\\',{method:\\'POST\\',body:JSON.stringify({id:'+c.id+'})}).then(function(){var p=document.getElementById(\\'ai-chat-panel\\');if(p)p.querySelectorAll(\\\"[onclick*=switchAIConv(\\'+c.id+\\')]\\\").forEach(function(x){x.style.display=\\\"none\\\"})})}\" style=\"font-size:12px;cursor:pointer;margin-left:2px;opacity:0.5\" title=\"删除\">\\u2716</span></div>';"
if old_conv_item in c:
    c = c.replace(old_conv_item, new_conv_item)
    print("3 delete button OK")
else:
    print("3 conv item not found")
    idx = c.find("sideH+='<div onclick=\"switchAIConv")
    if idx >= 0:
        print("  conv item at", idx)

# 4) Update sendAIChat to use streaming
old_send = "var r=await api('/api/ai/chat',{method:'POST',body:JSON.stringify({prompt:q,model:model,use_tools:true,personality:S.aiPersona||'warm',history:recentHistory.slice(0,-1)})});\n      clearInterval(thinkTimer);\n      var td=document.getElementById(thinkId);if(td){var p=td.parentNode;if(p)p.remove();}\n      var steps='';\n      if(r.thinking&&r.thinking.length)steps='<div style=\"font-size:10px;color:var(--text-third);margin-bottom:4px;font-style:italic\">'+r.thinking.map(function(s){return s}).join(' | ')+'</div>';\n      var reply=r.reply||'\\U0001f431 \\u54c8\\u57fa\\u7c73\\u5361\\u4f4f\\u4e86...';"
new_send = "var reply='';\n      try{\n        var streamResp=await fetch(API+'/api/ai/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:q,model:model,personality:S.aiPersona||'warm',history:recentHistory.slice(0,-1)})});\n        var reader=streamResp.body.getReader();var decoder=new TextDecoder();var buffer='';\n        var replyDiv=document.getElementById(thinkId);\n        while(true){\n          var {done,value}=await reader.read();if(done)break;\n          buffer+=decoder.decode(value,{stream:true});\n          var lines=buffer.split('\\n');buffer=lines.pop();\n          for(var line of lines){\n            if(line.startsWith('data: ')){\n              var data=line.slice(6);\n              if(data==='[DONE]')break;\n              try{var parsed=JSON.parse(data);if(parsed.token){reply+=parsed.token;if(replyDiv)replyDiv.innerHTML=renderMarkdown(reply);}}catch(e){}\n            }\n          }\n        }\n      }catch(e){\n        // Fallback to non-streaming\n        var r=await api('/api/ai/chat',{method:'POST',body:JSON.stringify({prompt:q,model:model,use_tools:true,personality:S.aiPersona||'warm',history:recentHistory.slice(0,-1)})});\n        reply=r.reply||'\\U0001f431 \\u54c8\\u57fa\\u7c73\\u5361\\u4f4f\\u4e86...';\n      }\n      clearInterval(thinkTimer);\n      var td=document.getElementById(thinkId);if(td){var p=td.parentNode;if(p)p.remove();}"
if old_send in c:
    c = c.replace(old_send, new_send)
    print("4 streaming OK")
else:
    print("4 streaming not found, trying fallback...")
    idx = c.find("r.thinking&&r.thinking.length")
    if idx >= 0:
        print("  fallback found")
        # Try from "var r=await" to "reply='...';"
        start = c.rfind("\\n", 0, c.find("r=await api", idx)) + 1
        end = c.find("';", idx + 100) + 2
        old = c[start:end]
        print("  old:", repr(old[:150]))

open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
print("done")