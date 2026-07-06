# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\code\\overtime-app\\local_db.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_fn = '''
def get_all_reasons_for_month(month):
    """获取指定月份(YYYY-MM)的所有加班理由"""
    c = _conn()
    try:
        c.execute("SELECT date, reason FROM ot_reasons WHERE date LIKE ?", (month + '%',))
        rows = c.fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        c.close()
'''

idx = content.rfind('def migrate_json_to_sqlite')
if idx < 0:
    print('Pattern not found')
    sys.exit(1)

content = content[:idx] + new_fn + content[idx:]

with open('D:\\code\\overtime-app\\local_db.py', 'w', encoding='utf-8') as f:
    f.write(content)

import ast
try:
    ast.parse(content)
    print('Syntax OK')
except SyntaxError as e:
    print(f'Syntax Error: {e}')
