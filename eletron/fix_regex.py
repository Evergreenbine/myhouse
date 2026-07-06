c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()
# Fix literal newline in regex: replace(/\n/g with replace(/\\n/g
old = "t=t.replace(/\n/g,\"<br>\");"
new = "t=t.replace(/\\n/g,\"<br>\");"
if old in c:
    c = c.replace(old, new)
    open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
    print("fixed")
else:
    print("not found")
    # Check for any other regex issues
    import re
    matches = list(re.finditer(r"t\.t\.replace\(/[^/]+/", c))
    for m in matches:
        print(repr(c[m.start():m.start()+50]))