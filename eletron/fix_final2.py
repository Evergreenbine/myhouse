c = open("D:/code/manbo/renderer/index.html", "r", encoding="utf-8").read()
# Fix 1: change style.display='none' to x.remove() in archiveConv
c = c.replace("x.style.display='none'", "x.remove()")
print("1 style.display fixed:", "x.style.display" not in c)

# Fix 2: remove deleteConv function
i = c.find("function deleteConv")
if i > 0:
    j = c.find("function newAIChat", i)
    while c[i-1] in "\n\r": i -= 1
    c = c[:i] + c[j:]
    print("2 deleteConv removed:", "function deleteConv" not in c)
else:
    print("2 deleteConv not found")

# Fix 3: remove delete button span from conv item
conv_start = c.find("convs.forEach")
if conv_start > 0:
    conv_section = c[conv_start:conv_start+800]
    del_pos = conv_section.find("deleteConv")
    if del_pos > 0:
        span_start = conv_section.rfind("<span", 0, del_pos)
        span_end = conv_section.find("</span>", del_pos) + 7
        delete_span = conv_section[span_start:span_end]
        c = c.replace(delete_span, "")
        print("3 delete button removed:", "deleteConv" not in c)
    else:
        print("3 delete button not in conv area")
else:
    print("3 convs.forEach not found")

open("D:/code/manbo/renderer/index.html", "w", encoding="utf-8").write(c)
print("done")