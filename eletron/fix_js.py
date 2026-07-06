import sys, re
sys.stdout.reconfigure(encoding="utf-8")
filepath = "D:\\code\\manbo\\renderer\\index.html"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1: Syntax error - missing semicolon 
old1 = "c.note||'\' rows=document.querySelectorAll('#capsule-overview-content tbody tr');"
old1_alt = "c.note||" + chr(39) + chr(39) + " rows=document.querySelectorAll"
new1 = "c.note||" + chr(39) + chr(39) + "; var rows=document.querySelectorAll"

count = content.count(old1_alt)
print(f"Found {count} occurrences of the syntax error pattern")

if count > 0:
    content = content.replace(old1_alt, new1, count)
    print(f"Fixed {count} syntax error(s)")
else:
    # Try to find it
    idx = content.find("c.note")
    while idx > 0:
        ctx = content[idx+6:idx+130]
        if "rows=document.querySelectorAll" in ctx:
            print(f"Found syntax error at {idx}")
            print(f"  Context: {repr(content[idx:idx+130])}")
        idx = content.find("c.note", idx+1)

# Fix 2: Missing await before loadAttendance() in init()
old2 = "loadAttendance();"
# Find the one in init()
init_idx = content.find("async function init()")
if init_idx > 0:
    init_end = content.find("\n", init_idx)
    if init_end < 0:
        init_end = init_idx + 1000
    init_section = content[init_idx:init_end]
    print(f"\ninit() section length: {len(init_section)}")
    if old2 in init_section:
        # Replace inside init
        content = content[:init_idx + init_section.find(old2)] + "await " + content[init_idx + init_section.find(old2):]
        print("Fixed: added await before loadAttendance() in init()")
    else:
        print("loadAttendance() not found in init() section")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("\nAll fixes applied!")
