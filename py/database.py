# -*- coding: utf-8 -*-
"""数据库连接模块 - 使用 pyodbc 连接 SQL Server"""
import pyodbc
from config import DB_CONFIG


def get_connection():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_CONFIG['server']},{DB_CONFIG['port']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['user']};"
        f"PWD={DB_CONFIG['password']};"
    )
    return pyodbc.connect(conn_str)


def row_to_dict(cursor, row):
    if row is None:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def query_work_records_range(empno, start_date, end_date):
    """
    按工号查询一段时间内的考勤记录
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT * FROM kq_workrecord
            WHERE empno = ?
              AND workdate >= ?
              AND workdate <= ?
            ORDER BY workdate ASC, worktime ASC
        """
        cursor.execute(sql, (str(empno), start_date + " 00:00:00", end_date + " 23:59:59"))
        rows = cursor.fetchall()

        from collections import defaultdict
        result = defaultdict(list)
        for row in rows:
            d = row_to_dict(cursor, row)
            workdate = d["workdate"]
            if hasattr(workdate, "strftime"):
                date_str = workdate.strftime("%Y-%m-%d")
            else:
                date_str = str(workdate)[:10]
            result[date_str].append(d)
        return dict(result)
    finally:
        conn.close()
