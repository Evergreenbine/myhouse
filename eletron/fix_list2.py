c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()

# 1) Add list-style-position:inside to li CSS
c = c.replace(
    ".chat-bubble-ai li{margin:2px 0}",
    ".chat-bubble-ai li{list-style-position:inside;margin:2px 0}"
)
print("1 CSS fixed")

# 2) Add <ul> wrapping regex after ordered list regex
old = 't=t.replace(/^(\d+)\. (.+)$/gm,"<li>$2</li>");'
new = old + '\n  t=t.replace(/((?:<li>[\\s\\S]*?<\\/li>(?:\\n|$))+)/g,"<ul>$1</ul>");'
c = c.replace(old, new)
print("2 ul wrapping added")

open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
print("done")