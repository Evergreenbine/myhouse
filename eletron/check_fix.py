import sys, re
sys.stdout.reconfigure(encoding="utf-8")

with open("D:\\code\\manbo\\renderer\\index.html", "r", encoding="utf-8") as f:
    content = f.read()

print("=== Checking Fixes ===")
print(f"Fix 1 (semicolon): {'; var rows=document.querySelectorAll' in content}")
print(f"Fix 2 (await): {'await loadAttendance()' in content}")

# Check for potential syntax errors - var declarations followed by '' then identifier
print("\n=== Checking for more syntax errors ===")
# Search for patterns where '' is followed directly by a letter (no semicolon)
# Using bytes to avoid encoding issues
raw = content.encode("utf-8")
idx = raw.find(b"''")
while idx > 0:
    # Check what follows
    next_chars = raw[idx:idx+20]
    if len(next_chars) > 2 and next_chars[2:3].isalpha():
        ctx = content[max(0,idx-30):idx+25]
        print(f"  Potential missing semicolon at byte {idx}: {repr(ctx)}")
    idx = raw.find(b"''", idx+2)

# Also check for any '?;' patterns
if ");" in content:
    idx2 = content.find(");")
    while idx2 > 0:
        ctx = content[max(0,idx2-5):idx2+5]
        print(f"  Found ); at {idx2}: {repr(ctx)}")
        idx2 = content.find(");", idx2+1)
        if idx2 < 0 or idx2 > 60000:
            break

# Let's look at the init function to verify the fix
print("\n=== init() function check ===")
init_idx = content.find("async function init()")
if init_idx > 0:
    init_section = content[init_idx:init_idx+800]
    print("init() contains 'loadAttendance':", "loadAttendance" in init_section)
    print("init() contains 'await loadAttendance':", "await loadAttendance" in init_section)

print("\n=== Checking script length ===")
s_start = content.find("<script>")
s_end = content.find("</script>", s_start)
print(f"Script block: {s_end - s_start} bytes")

# Try using node to check syntax
print("\n=== Writing JS file for syntax check ===")
script = content[s_start+8:s_end]
with open("D:\\code\\manbo\\check_syntax.js", "w", encoding="utf-8") as f:
    f.write(script)
print("Written check_syntax.js")
