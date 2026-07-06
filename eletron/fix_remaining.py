import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("D:\\code\\manbo\\renderer\\index.html", "r", encoding="utf-8") as f:
    c = f.read()

# Remove the leftover template literal from the bad replacement
# Find the pattern after else clause
idx = c.find('else{alert("\u274c "+res.msg)};')
if idx > 0:
    end_idx = c.find("loadAttendance()", idx)
    if end_idx > 0:
        before = c[:idx+len('else{alert("\u274c "+res.msg)};')]
        after = c[end_idx:]
        c = before + after
        print("Fixed leftover template literal")
    else:
        print("loadAttendance() not found after else")
else:
    print("Pattern not found")
    # Try alternate
    idx2 = c.find("else{alert")
    print("Found else at", idx2, repr(c[idx2:idx2+100]))

with open("D:\\code\\manbo\\renderer\\index.html", "w", encoding="utf-8") as f:
    f.write(c)
print("Done")
