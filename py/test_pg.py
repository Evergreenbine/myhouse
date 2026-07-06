# -*- coding: utf-8 -*-
import psycopg2

try:
    conn = psycopg2.connect(
        host='10.3.10.156', port=7092,
        database='pms_pmsdb',
        user='pms_pmsdb_user',
        password='tWjfoaNe75shFRax',
        connect_timeout=5
    )
    c = conn.cursor()
    c.execute("SELECT * FROM tb_crosshistory_202606 WHERE ch_plate=%s ORDER BY ch_crosstime desc LIMIT 3", ('粤S0Q780',))
    cols = [d[0] for d in c.description]
    print('Columns:', cols)
    for r in c.fetchall():
        print(dict(zip(cols, r)))
    conn.close()
    print('OK!')
except Exception as e:
    print('Error:', e)
