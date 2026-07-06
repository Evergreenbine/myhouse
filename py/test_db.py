# -*- coding: utf-8 -*-
import pyodbc

conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=10.3.10.86,1433;'
    'DATABASE=G4PRO;'
    'UID=Oa13;'
    'PWD=Oa13sql788;'
)
c = conn.cursor()
c.execute("SELECT TOP 3 * FROM kq_workrecord WHERE empname = ? ORDER BY workdate DESC, worktime DESC", '吴钦腾')
cols = [col[0] for col in c.description]
print('Columns:', cols)
rows = c.fetchall()
print('Rows:', len(rows))
for r in rows:
    d = dict(zip(cols, r))
    print({k: str(v)[:40] for k, v in d.items()})
conn.close()
