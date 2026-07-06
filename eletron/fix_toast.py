import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("D:\\code\\manbo\\renderer\\index.html", "r", encoding="utf-8") as f:
    c = f.read()

# 1. Fix: change type="time" back to type="text" for punch-time
c = c.replace('type="time" step="1" id="punch-time"', 'type="text" id="punch-time"', 1)
print("1. Reverted time picker to text input")

# 2. Add showToast function before doPunch
toast_fn = 'function showToast(msg){var t=document.createElement("div");t.textContent=msg;t.style.cssText="position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:99999;background:#333;color:#fff;padding:10px 24px;border-radius:10px;font-size:14px;opacity:1;transition:opacity 0.4s;pointer-events:none";document.body.appendChild(t);setTimeout(function(){t.style.opacity="0";setTimeout(function(){if(t.parentNode)t.parentNode.removeChild(t)},400)},2000)}\n\n'

# Insert before doPunch
idx = c.find("async function doPunch")
if idx > 0:
    c = c[:idx] + toast_fn + c[idx:]
    print("2. Added showToast function")
else:
    print("2. Could not find doPunch to insert toast before")

with open("D:\\code\\manbo\\renderer\\index.html", "w", encoding="utf-8") as f:
    f.write(c)
print("Done")
