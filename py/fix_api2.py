f = open('api_server.py', 'r', encoding='utf-8').read()
# Fix SQL: revert empname to empname (was incorrectly changed)
f = f.replace('INSERT INTO kq_workrecord (empno, "1103141", deptno', 'INSERT INTO kq_workrecord (empno, empname, deptno')
# Fix VALUES too
f = f.replace("1103141, '吴钦腾', '41402'", "'1103141', '吴钦腾', '41402'")
open('api_server.py', 'w', encoding='utf-8').write(f)
print('Fixed SQL')
