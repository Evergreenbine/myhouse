c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

old = """function archiveConv(id){
  api('/api/chat/archive',{method:'POST',body:JSON.stringify({id:id,archived:true})});
  var p=document.getElementById('ai-chat-panel');
  if(p)p.querySelectorAll("[onclick*=switchAIConv(" + id + ")]").forEach(function(x){x.remove()});
}"""

new = """function archiveConv(id){
  M('<div style="text-align:center;padding:8px"><div style="font-size:18px;font-weight:bold;margin-bottom:12px">' +
    '\uD83D\uDCC4 \u5f52\u6863\u5bf9\u8bdd</div><div style="font-size:14px;color:var(--text-sec);margin-bottom:20px">' +
    '\u786e\u5b9a\u8981\u5f52\u6863\u6b64\u5bf9\u8bdd\u5417\uff1f\u5f52\u6863\u540e\u53ef\u5728\u8bbe\u7f6e-\u5386\u53f2\u5f52\u6863\u4e2d\u6062\u590d\u3002</div>' +
    '<div style="display:flex;gap:12px;justify-content:center"><button class="btn btn-outline" onclick="CM()">\u53d6\u6d88</button>' +
    '<button class="btn btn-primary" onclick="CM();doArchive('+id+')">\u786e\u5b9a\u5f52\u6863</button></div></div>');
}
function doArchive(id){
  api('/api/chat/archive',{method:'POST',body:JSON.stringify({id:id,archived:true})});
  var p=document.getElementById('ai-chat-panel');
  if(p)p.querySelectorAll("[onclick*=switchAIConv(" + id + ")]").forEach(function(x){x.remove()});
}"""

if old in c:
    c = c.replace(old, new)
    open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
    print("confirm dialog added")
else:
    print("NOT found")