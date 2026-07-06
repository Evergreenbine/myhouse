c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

# Find the target pattern (4 newlines after })
close_end = "  S.chatHistory=[];\n}\n\n\n\nfunction newAIChat"
archive_func = "  S.chatHistory=[];\n}\nfunction archiveConv(id){\n  var a=JSON.parse(localStorage.getItem('archivedConvs')||'[]');\n  if(!a.includes(id))a.push(id);\n  localStorage.setItem('archivedConvs',JSON.stringify(a));\n  var p=document.getElementById('ai-chat-panel');\n  if(p)p.querySelectorAll(\"[onclick*=switchAIConv('+id+')]\").forEach(function(x){x.style.display='none'});\n}\nfunction unarchiveConv(id){\n  var a=JSON.parse(localStorage.getItem('archivedConvs')||'[]');\n  var i=a.indexOf(id);if(i>=0)a.splice(i,1);\n  localStorage.setItem('archivedConvs',JSON.stringify(a));\n}\n\n\n\nfunction newAIChat"

if close_end in c:
    c = c.replace(close_end, archive_func)
    open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
    print("archiveConv added, found pattern")
else:
    print("not found, searching...")
    idx = c.find("S.chatHistory=[];")
    while idx >= 0:
        end = c.find("function", idx)
        print(f"pos={idx}: {repr(c[idx:idx+60])}")
        idx = c.find("S.chatHistory=[];", idx+1)
