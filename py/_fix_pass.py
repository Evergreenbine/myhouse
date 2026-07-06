# -*- coding: utf-8 -*-
with open('D:\\code\\overtime-app\\api_server.py', 'r', encoding='utf-8') as f:
    content = f.read()
# Fix the pass line
content = content.replace("                                pass''\n", "                                pass\n")
# Verify
import ast
try:
    ast.parse(content)
    print('Syntax OK')
    with open('D:\\code\\overtime-app\\api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
except SyntaxError as e:
    print(f'Still broken at line {e.lineno}')
    lines = content.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+3)):
        print(f'{i+1}: {repr(lines[i][:120])}')
