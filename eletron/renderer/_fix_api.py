# -*- coding: utf-8 -*-
with open('D:\\code\\manbo\\renderer\\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find script tag
script_tag = content.find('<script>')
script_close = content.find('</script>', script_tag)
before = content[:script_tag+8]
after = content[script_close:]
script_content = content[script_tag+8:script_close]

# The script content has lost its api() function. Check first 100 chars
print('Script starts with:', repr(script_content[:100]))

# Find S state or const API
start_actual = 0
for keyword in ['let S=', 'var S=', 'S={', 'const API']:
    idx = script_content.find(keyword)
    if idx >= 0:
        start_actual = idx
        break

if start_actual > 0:
    # There's something before S - keep it and add api too
    pass

# Prepend the correct api function
api_fn = "const API='http://127.0.0.1:18520';
async function api(url,o={}){const ctrl=new AbortController();const t=setTimeout(()=>ctrl.abort(),15000);try{const r=await fetch(API+url,{headers:{'Content-Type':'application/json'},signal:ctrl.signal,...o});clearTimeout(t);if(!r.ok)throw new Error(r.status+' '+r.statusText);return r.json()}catch(e){clearTimeout(t);throw e}}
"

new_script = api_fn + script_content
content = before + new_script + after

with open('D:\\code\\manbo\\renderer\\index.html', 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open('D:\\code\\manbo\\renderer\\index.html', 'r', encoding='utf-8') as f:
    v = f.read()
script_tag2 = v.find('<script>')
script_close2 = v.find('</script>', script_tag2)
vc = v[script_tag2+8:script_close2]
print('Has api():', 'function api(' in vc)
print('Has async:', 'async function api(' in vc)
print('First 200 chars:', vc[:200])
