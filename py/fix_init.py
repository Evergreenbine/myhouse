import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

with open("D:\\code\\manbo\\renderer\\index.html", "rb") as f:
    raw = f.read()
text = raw.decode("utf-8")

# The issue: init() calls loadAttendance() WITHOUT await
# This means if init finishes before the fetch completes,
# and then there is a context issue, loadAttendance never runs.

# Fix: Change loadAttendance to be awaited
# Original:
# loadAttendance();
# Fix:
# await loadAttendance();

old_init_line = "loadAttendance();"
new_init_line = "await loadAttendance();"

if old_init_line in text:
    text = text.replace(old_init_line, new_init_line, 1)
    print(f"Fixed: loadAttendance() is now awaited in init()")
else:
    print(f"WARNING: '{old_init_line}' not found!")
    # Search for alternative
    pos = text.find("loadAttendance()")
    if pos >= 0:
        ctx = text[max(0,pos-10):pos+30]
        print(f"Found at {pos}: {repr(ctx)}")

# Also add a safety check: if loadAttendance fails, still show "已就绪"
# The init function sets bottom-status="已就绪" at the end
# But if loadAttendance is awaited and fails, it would throw
# Let me wrap the whole init body in a try/catch

# Actually the simpler fix: add a try-catch around await loadAttendance()
# Let me check the current init structure
init_pos = text.find("async function init(){")
if init_pos >= 0:
    # Wrap loadAttendance call in try/catch
    old = "try{await loadAttendance()}catch(e){}"
    new = "try{await loadAttendance()}catch(e){console.error(e)}"
    text = text.replace("await loadAttendance()", old)
    print("Wrapped loadAttendance in try/catch")

with open("D:\\code\\manbo\\renderer\\index.html", "w", encoding="utf-8") as f:
    f.write(text)
print(f"File updated: {len(text.encode('utf-8'))} bytes")
