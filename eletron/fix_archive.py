import re
c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

# 1) Add archiveFilter and archive button to conversation list rendering
old_conv_item = "sideH+='<div onclick=\"switchAIConv('+c.id+')\" style=\"padding:8px 10px;cursor:pointer;border-radius:8px;font-size:12px;color:var(--text-sec);margin:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'+(c.id===loadConvId?'background:var(--blue-light);font-weight:bold;color:var(--blue);border-bottom:2px solid var(--blue)':'')+'\">'+c.title+'</div>';"
new_conv_item = "var _arch=JSON.parse(localStorage.getItem('archivedConvs')||'[]');sideH+='<div onclick=\"switchAIConv('+c.id+')\" style=\"display:flex;align-items:center;padding:8px 10px;cursor:pointer;border-radius:8px;font-size:12px;color:var(--text-sec);margin:2px;"+(c.id===loadConvId?'background:var(--blue-light);font-weight:bold;color:var(--blue);border-bottom:2px solid var(--blue)':'')+'\"><span style=\"flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">'+c.title+'</span><span onclick=\"event.stopPropagation();archiveConv('+c.id+')\" style=\"font-size:11px;cursor:pointer;margin-left:4px;opacity:0.5\" title=\"归档\">\uD83D\uDCC4</span></div>';"
if old_conv_item in c:
    c = c.replace(old_conv_item, new_conv_item)
    print("1) archive button added to conv list")
else:
    print("1) conv item not found, trying fallback...")

# 2) Filter archived conversations from the list
old_filter = "if(convs.length){\n      convs.sort"
new_filter = "var _arch=JSON.parse(localStorage.getItem('archivedConvs')||'[]');convs=convs.filter(function(x){return !_arch.includes(x.id)});if(convs.length){\n      convs.sort"
if old_filter in c:
    c = c.replace(old_filter, new_filter)
    print("2) archive filter added")
else:
    print("2) filter not found")

# 3) Add archiveConv and unarchiveConv functions after closeAIChat
old_close_end = "  S.chatHistory=[];\n}\n\n\nfunction newAIChat"
new_functions = """  if(typeof localStorage!=='undefined')localStorage.setItem('lastAIConv',aiConvId);
  S.chatHistory=[];
}
function archiveConv(id){
  var a=JSON.parse(localStorage.getItem('archivedConvs')||'[]');
  if(!a.includes(id))a.push(id);
  localStorage.setItem('archivedConvs',JSON.stringify(a));
  var p=document.getElementById('ai-chat-panel');
  if(p)p.querySelectorAll('[onclick*=\"switchAIConv('+id+')\"]').forEach(function(x){x.style.display='none'});
}
function unarchiveConv(id){
  var a=JSON.parse(localStorage.getItem('archivedConvs')||'[]');
  var i=a.indexOf(id);if(i>=0)a.splice(i,1);
  localStorage.setItem('archivedConvs',JSON.stringify(a));
}

function newAIChat"""
if old_close_end in c:
    c = c.replace(old_close_end, new_functions)
    print("3) archiveConv/unarchiveConv added")
else:
    print("3) closeAIChat end not found")

# 4) Add archived conversations section in settings AI tab
old_ai_end = "return h\n}\nif(tab==='safe'){"
# Find the "return h" that ends the AI tab section, then the if for safe tab
# We need to insert archive section before "return h" of the ai tab
idx = c.find("\nreturn h\n}\nif(tab==='safe'){")
if idx >= 0:
    archive_section = """  // 历史归档对话
  h+=section('\u5386\u53f2\u5f52\u6863','\uD83D\uDCC4',
  '<div id=\"archived-conv-list\" style=\"font-size:13px;color:var(--text-third)\">\u52a0\u8f7d\u4e2d...</div>');
  if(typeof localStorage!=='undefined'){
    var _archIds=JSON.parse(localStorage.getItem('archivedConvs')||'[]');
    if(_archIds.length){
      api('/api/chat/list').then(function(convs){
        var _archived=convs.filter(function(c){return _archIds.includes(c.id)});
        if(_archived.length){
          var ah=_archived.map(function(c){return '<div style=\"display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:0.5px solid var(--border)\"><span style=\"font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1\">'+c.title+'</span><button class=\"btn btn-sm btn-outline\" onclick=\"unarchiveConv('+c.id+');document.getElementById(\\'archived-conv-list\\').innerHTML=\'<div style=font-size:13px;color:var(--text-third)>\\u5df2\u6062\u590d</div>\";setTimeout(function(){document.getElementById(\\'archived-conv-list\\').innerHTML=\'<div style=font-size:13px;color:var(--text-third)>\\u6682\u65e0\u5f52\u6863\u8bb0\u5f55</div>\'},2000)\" style=\"font-size:11px\">\u6062\u590d</button></div>'}).join('');
          document.getElementById('archived-conv-list').innerHTML=ah;
        }else{
          document.getElementById('archived-conv-list').innerHTML='<div style=\"font-size:13px;color:var(--text-third)\">\u6682\u65e0\u5f52\u6863\u8bb0\u5f55</div>';
        }
      }).catch(function(){document.getElementById('archived-conv-list').innerHTML='<div style=\"font-size:13px;color:var(--text-third)\">\u52a0\u8f7d\u5931\u8d25</div>'});
    }else{
      document.getElementById('archived-conv-list').innerHTML='<div style=\"font-size:13px;color:var(--text-third)\">\u6682\u65e0\u5f52\u6863\u8bb0\u5f55</div>';
    }
  }
"""
    c = c[:idx] + archive_section + c[idx:]
    print("4) archive section added to settings AI tab")
else:
    print("4) settings AI tab end not found")

open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
print("done")
