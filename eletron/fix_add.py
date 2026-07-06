c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

# Insert archiveConv, doArchive, unarchiveConv before function newAIChat
ins = c.find("function newAIChat()")
if ins > 0:
    funcs = """
function archiveConv(id){
  M('\u003cdiv style=\"text-align:center;padding:8px\"\u003e\u003cdiv style=\"font-size:18px;font-weight:bold;margin-bottom:12px\"\u003e\\U0001F4C4 \\u5f52\\u6863\\u5bf9\\u8bdd\u003c/div\u003e\u003cdiv style=\"font-size:14px;color:var(--text-sec);margin-bottom:20px\"\u003e\\u786e\\u5b9a\\u8981\\u5f52\\u6863\\u6b64\\u5bf9\\u8bdd\\u5417\\uff1f\\u5f52\\u6863\\u540e\\u53ef\\u5728\\u8bbe\\u7f6e-\\u5386\\u53f2\\u5f52\\u6863\\u4e2d\\u6062\\u590d\\u3002\u003c/div\u003e\u003cdiv style=\"display:flex;gap:12px;justify-content:center\"\u003e\u003cbutton class=\"btn btn-outline\" onclick=\"CM()\"\u003e\\u53d6\\u6d88\u003c/button\u003e\u003cbutton class=\"btn btn-primary\" onclick=\"CM();doArchive('+id+')\"\u003e\\u786e\\u5b9a\\u5f52\\u6863\u003c/button\u003e\u003c/div\u003e\u003c/div\u003e');
}
function doArchive(id){
  api('/api/chat/archive',{method:'POST',body:JSON.stringify({id:id,archived:true})});
  var p=document.getElementById('ai-chat-panel');
  if(p)p.querySelectorAll("[onclick*=switchAIConv(" + id + ")]").forEach(function(x){x.remove()});
}
function unarchiveConv(id){
  api('/api/chat/archive',{method:'POST',body:JSON.stringify({id:id,archived:false})});
}

"""
    c = c[:ins] + funcs + c[ins:]
    open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
    print("functions added")
else:
    print("newAIChat not found")