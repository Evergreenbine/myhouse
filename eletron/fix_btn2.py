c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()
# Fix: change the broken css selector with '+id+' to proper concatenation
old = "[onclick*=switchAIConv('+id+')]"
new = '[onclick*=switchAIConv(" + id + ")]'
c = c.replace(old, new)
open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
print("fixed")