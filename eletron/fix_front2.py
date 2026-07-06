c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

# Check renderMarkdown and buildChatBubble
print("renderMarkdown:", "renderMarkdown" in c)

# Add deleteConv function before newAIChat
old_fn = "function newAIChat()"
new_fn = """function deleteConv(id){
  if(!confirm("确定删除此对话？"))return;
  api("/api/chat/delete",{method:"POST",body:JSON.stringify({id:id})}).then(function(){
    var p=document.getElementById("ai-chat-panel");
    if(p)p.querySelectorAll("[onclick*=switchAIConv("+id+")]").forEach(function(x){x.remove()});
  });
}
""" + old_fn
c = c.replace(old_fn, new_fn)
print("deleteConv:", "deleteConv" in c)

# Add delete button to conv items (replace archive span with archive+delete)
old_item = '<span onclick="event.stopPropagation();archiveConv('
new_item = '<span onclick="event.stopPropagation();deleteConv('
c = c.replace(old_item, new_item)
print("delete button:", old_item in old_item)

# Actually we need to ADD a delete button, not replace the archive button
# Let me revert that and add a separate delete button
c = c.replace(new_item, old_item)  # revert

# The conv item has: archive archiveConv span, then </div>
# Let me add a delete span after the archive span
old_span_end = "' title=\"\\u5f52\\u6863\">"
new_span_with_delete = "' title=\"\\u5f52\\u6863\">\\uD83D\\uDCC4</span><span onclick=\"event.stopPropagation();deleteConv('+c.id+')\" style=\"font-size:11px;cursor:pointer;margin-left:4px;opacity:0.5\" title=\"\\u5220\\u9664\">\\u2716</span>"
c = c.replace(old_span_end, new_span_with_delete)
print("delete button text:", "\\u2716" in c)

# Update sendAIChat for streaming
old_api = "var r=await api('/api/ai/chat',{method:'POST',body:JSON.stringify({prompt:q,model:model,use_tools:true,personality:S.aiPersona||'warm',history:recentHistory.slice(0,-1)})});\n      clearInterval(thinkTimer);\n      var td=document.getElementById(thinkId);if(td){var p=td.parentNode;if(p)p.remove();}\n      var steps='';\n      if(r.thinking&&r.thinking.length)steps='<div style=\"font-size:10px;color:var(--text-third);margin-bottom:4px;font-style:italic\">'+r.thinking.map(function(s){return s}).join(' | ')+'</div>';\n      var reply=r.reply||'\\U0001f431 \\u54c8\\u57fa\\u7c73\\u5361\\u4f4f\\u4e86...';"
new_api = "var reply='';\n      // Try streaming\n      try{\n        var sr=await fetch(API+'/api/ai/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:q,model:model,personality:S.aiPersona||'warm',history:recentHistory.slice(0,-1)})});\n        var rdr=sr.body.getReader();var dcd=new TextDecoder();var buf='';\n        var td=document.getElementById(thinkId);\n        while(true){\n          var rr=await rdr.read();if(rr.done)break;\n          buf+=dcd.decode(rr.value,{stream:true});\n          var lines=buf.split('\\n');buf=lines.pop();\n          for(var l=0;l<lines.length;l++){\n            var ln=lines[l];\n            if(ln.startsWith('data: ')){\n              var dt=ln.slice(6);\n              if(dt==='[DONE]')break;\n              try{var p=JSON.parse(dt);if(p.token){reply+=p.token;if(td)td.innerHTML=renderMarkdown(reply);}}catch(e){}\n            }\n          }\n        }\n      }catch(e){\n        // Fallback\n        var fr=await api('/api/ai/chat',{method:'POST',body:JSON.stringify({prompt:q,model:model,use_tools:true,personality:S.aiPersona||'warm',history:recentHistory.slice(0,-1)})});\n        reply=fr.reply||'\\U0001f431 \\u54c8\\u57fa\\u7c73\\u5361\\u4f4f\\u4e86...';\n      }\n      clearInterval(thinkTimer);\n      var td2=document.getElementById(thinkId);if(td2){var p=td2.parentNode;if(p)p.remove();}"
if old_api in c:
    c = c.replace(old_api, new_api)
    print("streaming:", "chat/stream" in c[c.find("async function sendAIChat"):c.find("async function sendAIChat")+2000] )
else:
    print("streaming NOT found, checking...")
    idx = c.find("r.thinking&&r.thinking.length")
    print("r.thinking at", idx, repr(c[idx:idx+200]))

open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
print("done")