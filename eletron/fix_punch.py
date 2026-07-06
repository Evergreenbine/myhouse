import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("D:\\code\\manbo\\renderer\\index.html", "r", encoding="utf-8") as f:
    c = f.read()
old = "CM();alert(res.success?"
new = 'CM();if(res.success){showToast("\u2705 \u8865\u5361\u6210\u529f "+t)}else{alert("\u274c "+res.msg)};'
if old in c:
    c = c.replace(old, new, 1)
    print("OK - replaced")
    with open("D:\\code\\manbo\\renderer\\index.html", "w", encoding="utf-8") as f:
        f.write(c)
else:
    print("Pattern not found")
    idx = c.find("function doPunch")
    if idx > 0:
        print(repr(c[idx:idx+250]))
