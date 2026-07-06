import sys
sys.stdout.reconfigure(encoding="utf-8")
filepath = "D:\\code\\manbo\\renderer\\index.html"
with open(filepath, "r", encoding="utf-8") as f:
    c = f.read()

# Fix saveCarEdit: remove the leftover ";" + chr(39)*3 + ... + ")" garbage
# The leftover is: ;'"'"'"(backtick)??????(backtick):(backtick)??????(backtick)";  )
# Actually simpler - find the ";'...' pattern and remove it
old = chr(39) + chr(10004) + chr(24050) + chr(20462) + chr(25913) + chr(39) + chr(58) + chr(39) + chr(10062) + chr(22833) + chr(36133) + chr(39)
# Oh this is getting complex. Let me just use the raw string match
idx = c.find("saveCarEdit")
if idx > 0:
    # Find the specific pattern in the function
    fn_end = c.find("loadCar()", idx)
    if fn_end > 0:
        # Look backwards from loadCar() to find the leftover
        section = c[idx:fn_end]
        leftover_start = section.find(chr(39) + chr(10004) + chr(24050))
        if leftover_start > 0:
            # Remove from the start of the leftover to before loadCar()
            before = c[:idx + leftover_start]
            after = c[idx + fn_end:]
            c = before + after
            print("1. Fixed saveCarEdit leftover")
        else:
            print("1. Could not find leftover in saveCarEdit")
            # Debug
            end_part = section[-80:]
            print("   End section:", repr(end_part))

with open(filepath, "w", encoding="utf-8") as f:
    f.write(c)
print("Done")
