# -*- coding: utf-8 -*-
from user_auth import load_user_config
from database import query_work_records_range

c = load_user_config()
empno = c.empno.lstrip('Mm')
print('查询 empno:', repr(empno))

recs = query_work_records_range(empno, '2026-05-24', '2026-06-23')
print('查到天数:', len(recs))
total = sum(len(v) for v in recs.values())
print('总记录数:', total)

if total == 0:
    import pyodbc
    conn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=10.3.10.86,1433;DATABASE=G4PRO;UID=Oa13;PWD=Oa13sql788;")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM kq_workrecord WHERE empno=? AND workdate>=? AND workdate<=?", ('1103141', '2026-05-24', '2026-06-23'))
    print('empno=1103141 count:', cur.fetchone()[0])
    conn.close()
