c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()
# Find the conv item template
i = c.find("sideH+='<div onclick=\"switchAIConv(")
j = c.find("</div>';", i) + len("</div>';")
old_item = c[i:j]
print("old item:")
print(repr(old_item))