c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()
close_end = "  S.chatHistory=[];\n}\n\n\nfunction newAIChat"
archive_func = "  S.chatHistory=[];\n}\nfunction archiveConv(id){\n  var a=JSON.parse(localStorage.getItem('archivedConvs')||'[]');\n  if(!a.includes(id))a.push(id);\n  localStorage.setItem('archivedConvs',JSON.stringify(a));\n  var p=document.getElementById('ai-chat-panel');\n  if(p)p.querySelectorAll(\"[onclick*=switchAIConv('+id+')]\").forEach(function(x){x.style.display='none'});\n}\nfunction unarchiveConv(id){\n  var a=JSON.parse(localStorage.getItem('archivedConvs')||'[]');\n  var i=a.indexOf(id);if(i>=0)a.splice(i,1);\n  localStorage.setItem('archivedConvs',JSON.stringify(a));\n}\n\n\n\nfunction newAIChat"
if close_end in c:
    c = c.replace(close_end, archive_func)
    open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
    print("archiveConv added")
else:
    print("not found")
