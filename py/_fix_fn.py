# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\code\\overtime-app\\local_db.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "        c.execute(\"SELECT date, reason FROM ot_reasons WHERE date LIKE ?\", (month + '%',))\n        rows = c.fetchall()"
new = "        rows = c.execute(\"SELECT date, reason FROM ot_reasons WHERE date LIKE ?\", (month + '%',)).fetchall()"

if old in content:
    content = content.replace(old, new)
    with open('D:\\code\\overtime-app\\local_db.py', 'w', encoding='utf-8') as f:
        f.write(content)
    import ast
    ast.parse(content)
    print('Syntax OK')
else:
    print('Pattern not found')
    # Show what's there
    idx = content.find('def get_all_reasons_for_month')
    block = content[idx:idx+300]
    print(block)
