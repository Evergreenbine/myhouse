# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\code\\overtime-app\\api_server.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Add method before do_GET
get_idx = c.find('    def do_GET(self):')
if get_idx > 0:
    method = chr(10) + '    def _handle_ot_reasons_bulk(self, qs):' + chr(10)
    method += '        month = qs.get("month", [date.today().strftime("%Y-%m")])[0]' + chr(10)
    method += '        reasons = {}' + chr(10)
    method += '        try:' + chr(10)
    method += '            from local_db import get_all_reasons_for_month' + chr(10)
    method += '            reasons = get_all_reasons_for_month(month)' + chr(10)
    method += '        except:' + chr(10)
    method += '            pass' + chr(10)
    method += '        return self._send_json(reasons)' + chr(10)
    method += chr(10)
    method += chr(10)
    
    c = c[:get_idx] + method + c[get_idx:]
    with open('D:\\code\\overtime-app\\api_server.py', 'w', encoding='utf-8') as f:
        f.write(c)
    import ast
    ast.parse(c)
    print('Syntax OK')
else:
    print('do_GET not found')
