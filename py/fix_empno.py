import re
with open('api_server.py', 'r', encoding='utf-8') as f:
    c = f.read()
# Replace cfg.empno usage in query_work_records_range calls back to "1103141"
c = c.replace("cfg.empno,", '"1103141",')
c = c.replace('cfg.empno if cfg else "1103141"', '"1103141"')
with open('api_server.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('done')
