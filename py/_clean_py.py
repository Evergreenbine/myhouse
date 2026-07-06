# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\code\\overtime-app\\api_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find both occurrences of the method
first = content.find('def _handle_ot_reasons_bulk')
second = content.find('def _handle_ot_reasons_bulk', first + 10)

if second > 0:
    # Find end of second method (next def or EOF)
    end = content.find('\n    def ', second + 5)
    if end < 0:
        end = len(content)
    dup = content[second:end]
    content = content.replace(dup, '')
    print('Removed duplicate method')

# Add GET route before car/abnormal in do_GET
insert_marker = "            elif path == \"/api/car/update\":"
idx = content.find(insert_marker)
if idx > 0:
    route_blk = '\n            elif path == "/api/ot-reasons-bulk":\n                return self._handle_ot_reasons_bulk(qs)\n'
    content = content[:idx] + route_blk + content[idx:]
    print('Added GET route')
else:
    print('Insertion point not found')
    # Try alternative
    insert2 = content.find("elif path.startswith('/api/car/abnormal'):")
    if insert2 > 0:
        route_blk = '\n            elif path == "/api/ot-reasons-bulk":\n                return self._handle_ot_reasons_bulk(qs)\n'
        content = content[:insert2] + route_blk + content[insert2:]
        print('Added via alt insertion point')

print('Route refs:', content.count('ot-reasons-bulk'))
print('Method defs:', content.count('def _handle_ot_reasons_bulk'))

with open('D:\\code\\overtime-app\\api_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

import ast
ast.parse(content)
print('Syntax OK')
