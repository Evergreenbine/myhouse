import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

with open("D:\\code\\manbo\\renderer\\index_corrupted.html", "rb") as f:
    cur_raw = f.read()
with open("D:\\code\\manbo\\renderer\\index.html", "rb") as f:
    new_raw = f.read()

cur_text = cur_raw.decode("utf-8", errors="replace")
new_text = new_raw.decode("utf-8")

# Strategy: Extract the unique content from the corrupted file 
# that is NOT in the dist backup, and add it back.

# The extra functions not in dist:
# getFestiveEmoji, loadCapsuleOverview, loadMoodMap, loadWeather,
# moodAdd, moodReset, saveCapsule, showMoodAdvice, showToast,
# spawnCoinRain, toggleTag

# Let me extract these functions from the corrupted file,
# fix the Chinese text, and insert them into the new file.

# First, find where to insert the extra functions (before the AI section)
# In the new file, find where the AI functionality starts
ai_match = re.search(r"// ========== \xe5\x93\x88\xe5\x9f\xba", new_text)
# That regex might not work. Let me find another anchor
# Find the end of showToast or doPunch functions in the corrupted file

# Actually, let me try a different approach:
# 1. Extract the LAST script section from both files
# 2. Find what code is in cur but not in new
# 3. Fix the Chinese
# 4. Insert

# In both files, find the last <script>...</script> block
cur_script_match = re.search(r"<script[^>]*>(.*)</script>", cur_text, re.DOTALL)
new_script_match = re.search(r"<script[^>]*>(.*)</script>", new_text, re.DOTALL)

if cur_script_match and new_script_match:
    cur_script = cur_script_match.group(1)
    new_script = new_script_match.group(1)
    
    # Find the extra code - everything after the shared portion
    # Let me find where the scripts diverge
    # The new file is ~35KB, the cur file is ~70KB
    # Let me find the point where cur has extra code
    
    # Find the end of the doPunch function (which exists in both)
    dopunch_end_cur = cur_script.find("function doPunch")
    if dopunch_end_cur >= 0:
        # Find the closing } of doPunch 
        start = cur_script.find("{", dopunch_end_cur)
        if start >= 0:
            depth = 1
            pos = start + 1
            while depth > 0 and pos < len(cur_script):
                if cur_script[pos] == "{": depth += 1
                elif cur_script[pos] == "}": depth -= 1
                pos += 1
            doPunch_code = cur_script[dopunch_end_cur:pos]
            print(f"doPunch: {len(doPunch_code)} chars")
            print(f"Contains U+FFFD: {chr(0xfffd) in doPunch_code}")

    # Find showToast function start (this is in cur but not in new)
    toast_start = cur_script.find("function showToast")
    if toast_start >= 0:
        print(f"\nshowToast starts at position {toast_start}")
        print(f"Context: {cur_script[toast_start-30:toast_start+20]}")
    
    # Find all code in cur_script that starts after the last shared function
    # Actually, let me find where new_script appears in cur_script
    # Since cur_script = new_script + extra_code
    # But the Chinese text differs, so they won't match exactly
    
    # Let me just try to find the insertion point by looking at 
    # what comes after the last shared function
    
    # Find the last function in new_script
    new_funcs = re.findall(r"function\s+\w+", new_script)
    print(f"\nNew script functions: {len(new_funcs)}")
    
    # The extra code starts after showToast or doPunch
    # Let me extract from the corrupted file the code that comes
    # after a known shared function
    
    # Find "=====" comment sections
    ai_section = new_script.find("哈基米AI")
    if ai_section >= 0:
        print(f"\nAI section found in new at: {ai_section}")
    
    # Let me just find where showToast is in cur_script
    # and extract everything from there to the end
    # This includes: showToast, getFestiveEmoji, spawnCoinRain, 
    # toggleTag, loadCapsuleOverview, loadMoodMap, moodAdd, moodReset,
    # saveCapsule, showMoodAdvice, loadWeather
    
    # The approach: extract the extra functions one by one from cur_script
    extra_func_names = ["showToast", "getFestiveEmoji", "spawnCoinRain", 
                       "toggleTag", "loadCapsuleOverview", "loadMoodMap", 
                       "loadWeather", "moodAdd", "moodReset", "saveCapsule", 
                       "showMoodAdvice"]
    
    for func_name in extra_func_names:
        pattern = r"function\s+" + re.escape(func_name) + r"\s*\([^)]*\)\s*\{"
        match = re.search(pattern, cur_script)
        if match:
            # Find the closing brace
            start = match.start()
            pos = cur_script.find("{", start)
            if pos >= 0:
                depth = 1
                pos += 1
                while depth > 0 and pos < len(cur_script):
                    if cur_script[pos] == "{": depth += 1
                    elif cur_script[pos] == "}": depth -= 1
                    pos += 1
                func_code = cur_script[start:pos]
                # Check for Chinese text that needs fixing
                if chr(0xfffd) in func_code:
                    print(f"\n{func_name}: {len(func_code)} chars, HAS U+FFFD")
                else:
                    print(f"\n{func_name}: {len(func_code)} chars, OK")
        else:
            print(f"\n{func_name}: NOT FOUND in cur_script")

